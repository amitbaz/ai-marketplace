"""Transactional company store: an append-only event log plus projections.

Layout under the company directory `root`:

    root/runtime/identity.json      0600, the canonical owner/repo binding
    root/runtime/cabinet.sqlite3    0600, events and projected state
    root/runtime/backups/           snapshots written by `backup()`
    root/views/                     human-readable exports

Every mutation opens `BEGIN IMMEDIATE`, writes its event and its projection
row, and commits before returning. Triggers reject UPDATE and DELETE on the
events table, so a later fact supersedes an earlier one by adding an event.

`after_event_hook` is a test seam: when set to a callable it is invoked inside
the transaction with the freshly inserted event, between the event write and
the projection write. Production leaves it None.
"""

import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from pathlib import Path

from .contracts import (
    ASSIGNMENT_TRANSITIONS,
    ACTION_TRANSITIONS,
    BATCH_TRANSITIONS,
    DOCUMENT_NAME_PATTERN,
    LIVE_ASSIGNMENT_STATES,
    LIVE_BATCH_STATES,
    SCHEMA_VERSION,
    action_identity,
    canonical_json,
    check_transition,
    digest,
    is_owner_acceptance,
    parse_repo,
    validate_action_envelope,
    validate_batch_body,
    validate_setup_scope,
)
from .errors import CabinetError

RUNTIME_DIRECTORY = "runtime"
VIEWS_DIRECTORY = "views"
DATABASE_NAME = "cabinet.sqlite3"
IDENTITY_NAME = "identity.json"
BACKUPS_DIRECTORY = "backups"
PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700

# Batch states in which an owner answer still applies to the same agreement.
# Any other state means the batch moved while the dialog was open.
APPROVABLE_BATCH_STATES = ("proposed", "approved")

SCHEMA = """
CREATE TABLE events (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    revision      INTEGER,
    time          TEXT NOT NULL,
    generation    INTEGER NOT NULL DEFAULT 0,
    payload_json  TEXT NOT NULL,
    digest        TEXT NOT NULL
);
CREATE INDEX events_by_entity ON events(entity_id, seq);

CREATE TRIGGER events_reject_update BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER events_reject_delete BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TABLE batches (
    batch_id    TEXT NOT NULL,
    revision    INTEGER NOT NULL,
    body_json   TEXT NOT NULL,
    digest      TEXT NOT NULL,
    state       TEXT NOT NULL,
    created_seq INTEGER NOT NULL,
    updated_seq INTEGER NOT NULL,
    PRIMARY KEY (batch_id, revision)
);

CREATE TABLE grants (
    grant_id            TEXT PRIMARY KEY,
    batch_id            TEXT,
    revision            INTEGER,
    digest              TEXT,
    scope_json          TEXT NOT NULL,
    owner_response_json TEXT NOT NULL,
    approved_seq        INTEGER NOT NULL,
    revoked_seq         INTEGER,
    UNIQUE (batch_id, revision, digest)
);

CREATE TABLE handoffs (
    handoff_id    TEXT PRIMARY KEY,
    batch_id      TEXT NOT NULL,
    revision      INTEGER NOT NULL,
    from_role     TEXT NOT NULL,
    to_role       TEXT NOT NULL,
    body_json     TEXT NOT NULL,
    digest        TEXT NOT NULL,
    state         TEXT NOT NULL,
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    created_seq   INTEGER NOT NULL,
    updated_seq   INTEGER NOT NULL
);

CREATE TABLE actions (
    action_id         TEXT PRIMARY KEY,
    idempotency_key   TEXT NOT NULL UNIQUE,
    kind              TEXT NOT NULL,
    batch_id          TEXT,
    revision          INTEGER,
    payload_json      TEXT NOT NULL,
    digest            TEXT NOT NULL,
    state             TEXT NOT NULL,
    external_ref_json TEXT,
    evidence_json     TEXT,
    created_seq       INTEGER NOT NULL,
    updated_seq       INTEGER NOT NULL
);

CREATE TABLE assignments (
    assignment_id     TEXT PRIMARY KEY,
    batch_id          TEXT NOT NULL,
    revision          INTEGER NOT NULL,
    role              TEXT NOT NULL,
    issue_number      INTEGER,
    workspace_id      TEXT,
    terminal_id       TEXT,
    native_session_id TEXT,
    generation        INTEGER NOT NULL,
    state             TEXT NOT NULL,
    work_key          TEXT NOT NULL,
    created_seq       INTEGER NOT NULL,
    updated_seq       INTEGER NOT NULL
);

CREATE TABLE verdicts (
    assignment_id TEXT NOT NULL,
    revision_sha  TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    time          TEXT NOT NULL,
    recorded_seq  INTEGER NOT NULL,
    PRIMARY KEY (assignment_id, revision_sha, reviewer_role)
);

CREATE TABLE lease (
    key           INTEGER PRIMARY KEY CHECK (key = 1),
    session_id    TEXT NOT NULL,
    pid           INTEGER NOT NULL,
    process_start TEXT NOT NULL,
    generation    INTEGER NOT NULL,
    last_seen     TEXT NOT NULL,
    paused        INTEGER NOT NULL DEFAULT 0,
    paused_reason TEXT
);

CREATE TABLE documents (
    name        TEXT NOT NULL,
    revision    INTEGER NOT NULL,
    content     TEXT NOT NULL,
    digest      TEXT NOT NULL,
    source_json TEXT NOT NULL,
    supersedes  INTEGER,
    created_seq INTEGER NOT NULL,
    PRIMARY KEY (name, revision)
);
"""

LIVE_ASSIGNMENT_INDEX = (
    "CREATE UNIQUE INDEX assignments_live_work ON assignments(work_key) "
    "WHERE state IN (%s)"
    % ", ".join("'%s'" % state for state in LIVE_ASSIGNMENT_STATES)
)


# --- process identity -------------------------------------------------------

def process_start_marker(pid=None):
    """Return a marker distinguishing this run of a PID from a later reuse.

    Linux reads field 22 of /proc/<pid>/stat; elsewhere it reads the start time
    reported by `ps`. An empty string means the platform did not answer.
    """

    pid = os.getpid() if pid is None else pid
    stat_path = Path("/proc/%d/stat" % pid)
    try:
        raw = stat_path.read_bytes().decode("utf-8", "replace")
    except OSError:
        raw = ""
    if raw:
        tail = raw[raw.rfind(")") + 2:].split()
        if len(tail) > 19:
            return "starttime:%s" % tail[19]
    try:
        finished = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                                  capture_output=True, text=True, timeout=10,
                                  shell=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if finished.returncode != 0 or not finished.stdout.strip():
        return ""
    return "lstart:%s" % " ".join(finished.stdout.split())


_OWN_IDENTITY = {}


def own_process_identity():
    """Return this process's (pid, start marker), reading the marker once."""

    pid = os.getpid()
    if pid not in _OWN_IDENTITY:
        _OWN_IDENTITY.clear()
        _OWN_IDENTITY[pid] = (pid, process_start_marker(pid))
    return _OWN_IDENTITY[pid]


def default_process_alive(pid, process_start):
    """Report whether the recorded process is still the one running as `pid`.

    A PID alone is not enough: the number is reused. The recorded start marker
    has to match too. When the platform cannot report a marker the process is
    treated as alive, so an unreadable answer never authorizes a second lead.
    """

    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    except (OverflowError, ValueError, OSError):
        return False
    current = process_start_marker(pid)
    if not current or not process_start:
        return True
    return current == process_start


def _lock_error(problem, action):
    """Translate a SQLite lock timeout into a stable code, else pass it on."""

    text = str(problem).lower()
    if "locked" in text or "busy" in text:
        return CabinetError(
            "STORE_BUSY",
            "another writer holds the company database; could not %s (%s)"
            % (action, problem))
    return problem


def _rollback_quietly(conn):
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _within(parent, child):
    """Report whether `child` stays inside `parent` once both are resolved."""

    parent_parts = Path(parent).resolve().parts
    child_parts = Path(child).resolve().parts
    return child_parts[:len(parent_parts)] == parent_parts


# --- path safety ------------------------------------------------------------

def _reject_symlink(path, label):
    if path.is_symlink():
        raise CabinetError("UNSAFE_PATH", "%s must not be a symlink: %s"
                           % (label, path))


def _reject_outside(parent, child, label):
    if not child.exists():
        return
    resolved = child.resolve()
    if resolved.parent != parent.resolve():
        raise CabinetError("UNSAFE_PATH", "%s resolves outside %s" % (label, parent))


def _write_private(path, text):
    """Replace `path` atomically with 0600 permissions."""

    directory = path.parent
    handle, temporary = tempfile.mkstemp(dir=str(directory), prefix=".tmp-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temporary, PRIVATE_FILE_MODE)
        os.replace(temporary, str(path))
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return path


class Store:
    """Durable company state for one repository.

    `root` is the company directory. `clock` is a callable returning UTC ISO
    text. `repo` binds the canonical `owner/repo` on first open; when it is
    omitted the first proposed batch binds it instead. `process_alive` is the
    injectable liveness probe used by lease acquisition.
    """

    def __init__(self, root, clock, repo=None, process_alive=None,
                 busy_timeout=5000):
        self.root = Path(root).resolve()
        self._clock = clock
        self._requested_repo = repo
        self._busy_timeout = busy_timeout
        self._process_alive = process_alive or default_process_alive
        self._conn = None
        self._identity = None
        self._session_id = None
        self._generation = None
        self.read_only = False
        self.after_event_hook = None

    # --- lifecycle ----------------------------------------------------------

    @property
    def runtime_dir(self):
        return self.root / RUNTIME_DIRECTORY

    @property
    def views_dir(self):
        return self.root / VIEWS_DIRECTORY

    @property
    def database_path(self):
        return self.runtime_dir / DATABASE_NAME

    @property
    def identity_path(self):
        return self.runtime_dir / IDENTITY_NAME

    @property
    def backups_dir(self):
        return self.runtime_dir / BACKUPS_DIRECTORY

    @property
    def identity(self):
        return dict(self._identity) if self._identity else None

    @property
    def generation(self):
        return self._generation

    def open(self, repo=None):
        """Create or attach to the company directory and return self."""

        requested = repo or self._requested_repo
        self.root.mkdir(parents=True, exist_ok=True)
        _reject_symlink(self.runtime_dir, "runtime directory")
        _reject_outside(self.root, self.runtime_dir, "runtime directory")
        self.runtime_dir.mkdir(mode=PRIVATE_DIR_MODE, exist_ok=True)
        os.chmod(str(self.runtime_dir), PRIVATE_DIR_MODE)
        _reject_symlink(self.identity_path, "identity file")
        _reject_symlink(self.database_path, "database file")
        _reject_outside(self.runtime_dir, self.identity_path, "identity file")
        _reject_outside(self.runtime_dir, self.database_path, "database file")

        self._load_identity()
        if requested:
            self._bind_identity(requested)
        self._connect()
        return self

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
        return False

    # --- identity -----------------------------------------------------------

    def _load_identity(self):
        if not self.identity_path.exists():
            return
        try:
            recorded = json.loads(self.identity_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as problem:
            raise CabinetError("IDENTITY_CONFLICT",
                               "identity.json is unreadable: %s" % problem)
        if not isinstance(recorded, dict) or "repo" not in recorded:
            raise CabinetError("IDENTITY_CONFLICT", "identity.json has no repository")
        parsed = parse_repo(recorded["repo"])
        parsed["schema"] = recorded.get("schema", SCHEMA_VERSION)
        parsed["created"] = recorded.get("created")
        self._identity = parsed

    def bind_identity(self, repo):
        """Bind the canonical owner/repo, or confirm the existing binding."""

        return self._bind_identity(repo)

    def _bind_identity(self, repo):
        parsed = parse_repo(repo)
        if self._identity is not None:
            if self._identity["repo"] != parsed["repo"]:
                raise CabinetError(
                    "IDENTITY_CONFLICT",
                    "this directory holds %s, not %s (the hyphenated slug %s "
                    "is shared by both)"
                    % (self._identity["repo"], parsed["repo"], parsed["slug"]))
            return self._identity
        parsed["schema"] = SCHEMA_VERSION
        parsed["created"] = self._clock()
        _write_private(self.identity_path, canonical_json(parsed) + "\n")
        self._identity = parsed
        return parsed

    # --- connection ---------------------------------------------------------

    def _connect(self):
        fresh = not self.database_path.exists()
        conn = sqlite3.connect(str(self.database_path), isolation_level=None,
                               timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=%d" % self._busy_timeout)
        if fresh:
            os.chmod(str(self.database_path), PRIVATE_FILE_MODE)
        self._secure_sidecars()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            script = "BEGIN IMMEDIATE;\n%s\n%s;\nPRAGMA user_version = %d;\nCOMMIT;" % (
                SCHEMA, LIVE_ASSIGNMENT_INDEX, SCHEMA_VERSION)
            try:
                conn.executescript(script)
            except sqlite3.OperationalError:
                # Another process created the same schema first.
                conn.rollback()
                if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                    conn.close()
                    raise
            self._secure_sidecars()
        elif version > SCHEMA_VERSION:
            # Folding the write-ahead log into the main file is what makes the
            # read-only reopen below possible. The log format is fixed by
            # SQLite and does not depend on this schema, so checkpointing a
            # database whose schema is too new to interpret is still safe.
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            conn = sqlite3.connect("file:%s?mode=ro" % self.database_path,
                                   uri=True, isolation_level=None, timeout=5.0)
            conn.row_factory = sqlite3.Row
            self.read_only = True
        self._conn = conn
        return conn

    def _secure_sidecars(self):
        """Hold the write-ahead log files to the same mode as the database."""

        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.database_path) + suffix)
            try:
                if sidecar.exists():
                    os.chmod(str(sidecar), PRIVATE_FILE_MODE)
            except OSError:
                pass

    def _require_open(self):
        if self._conn is None:
            raise CabinetError("STORE_CLOSED", "the store connection is closed")
        return self._conn

    def _require_writable(self):
        conn = self._require_open()
        if self.read_only:
            raise CabinetError(
                "SCHEMA_TOO_NEW",
                "this database was written by a newer Cabinet runtime; it is "
                "open for reading only")
        return conn

    # --- lease fencing ------------------------------------------------------

    def _lease_row(self, conn=None):
        conn = conn or self._require_open()
        return conn.execute("SELECT * FROM lease WHERE key = 1").fetchone()

    def _check_fence(self, conn=None):
        """Confirm this caller may write, adopting its own process's lease.

        A caller holding no lease is not automatically a writer. When the
        recorded lease belongs to this very process it is adopted, so a second
        Store handle inside the lead process keeps working. Otherwise a live
        holder gives LEAD_ACTIVE and a dead one gives LEASE_REQUIRED, because
        taking over a dead lead is an explicit `acquire_lease` call.
        """

        row = self._lease_row(conn)
        if row is None:
            return None
        if self._generation is None:
            if own_process_identity() == (row["pid"], row["process_start"]):
                self._session_id = row["session_id"]
                self._generation = row["generation"]
                return row
            if self._process_alive(row["pid"], row["process_start"]):
                raise CabinetError(
                    "LEAD_ACTIVE",
                    "session %s (pid %d) holds generation %d; this caller holds "
                    "no lease" % (row["session_id"], row["pid"], row["generation"]))
            raise CabinetError(
                "LEASE_REQUIRED",
                "the recorded lead %s is gone; acquire the lease before writing"
                % row["session_id"])
        if self._generation != row["generation"] or self._session_id != row["session_id"]:
            raise CabinetError(
                "LEASE_FENCED",
                "generation %s is stale; the current lease is generation %d"
                % (self._generation, row["generation"]))
        return row

    def _check_not_paused(self, conn=None):
        row = self._lease_row(conn)
        if row is not None and row["paused"]:
            raise CabinetError("PAUSED", "the company is paused: %s"
                               % (row["paused_reason"] or "no reason recorded"))

    def _bind_implicit_lease(self, conn):
        """Take the lease for this process on the first write of a new company.

        A company whose lease table is empty has no lead yet. Rather than
        leaving it open to every process, the first mutation binds a lease to
        the writing process, so a second process gets LEAD_ACTIVE instead of a
        free write. The same process can still call `acquire_lease` later.
        """

        pid, marker = own_process_identity()
        session_id = "implicit-%s" % uuid.uuid4().hex[:12]
        self._session_id = session_id
        self._generation = 1
        self._append_event_locked(
            conn, "lease.acquired", session_id, 1,
            {"pid": pid, "generation": 1, "implicit": True, "superseded": None})
        conn.execute(
            "INSERT INTO lease (key, session_id, pid, process_start, generation, "
            "last_seen, paused, paused_reason) VALUES (1, ?, ?, ?, 1, ?, 0, NULL)",
            (session_id, pid, marker, self._clock()))
        return session_id

    @contextlib.contextmanager
    def _transaction(self, fence=True):
        conn = self._require_writable()
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as problem:
            raise _lock_error(problem, "start a transaction") from problem
        held = (self._session_id, self._generation)
        bound = False
        try:
            if fence and self._check_fence(conn) is None:
                self._bind_implicit_lease(conn)
                bound = True
            yield conn
        except sqlite3.OperationalError as problem:
            _rollback_quietly(conn)
            if bound:
                self._session_id, self._generation = held
            raise _lock_error(problem, "finish a transaction") from problem
        except BaseException:
            _rollback_quietly(conn)
            if bound:
                self._session_id, self._generation = held
            raise
        try:
            conn.execute("COMMIT")
        except BaseException:
            _rollback_quietly(conn)
            if bound:
                self._session_id, self._generation = held
            raise

    # --- events -------------------------------------------------------------

    def _append_event_locked(self, conn, kind, entity_id, revision, payload):
        recorded_at = self._clock()
        payload_json = canonical_json(payload)
        event_id = uuid.uuid4().hex
        cursor = conn.execute(
            "INSERT INTO events (event_id, kind, entity_id, revision, time, "
            "generation, payload_json, digest) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, kind, str(entity_id), revision, recorded_at,
             self._generation or 0, payload_json, digest(payload)))
        event = {"seq": cursor.lastrowid, "event_id": event_id, "kind": kind,
                 "entity_id": str(entity_id), "revision": revision,
                 "time": recorded_at, "generation": self._generation or 0,
                 "payload": json.loads(payload_json), "digest": digest(payload)}
        if self.after_event_hook is not None:
            self.after_event_hook(event)
        return event

    def append_event(self, kind, entity_id, revision, payload):
        """Append one event and commit it. Returns the stored event."""

        with self._transaction() as conn:
            event = self._append_event_locked(conn, kind, entity_id, revision, payload)
        return event

    def get_events(self, after_seq=0, limit=None):
        """Return events with `seq` greater than `after_seq`, ordered by seq."""

        conn = self._require_open()
        query = "SELECT * FROM events WHERE seq > ? ORDER BY seq"
        parameters = [after_seq]
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        return [self._event_row(row) for row in conn.execute(query, parameters)]

    def max_event_seq(self):
        conn = self._require_open()
        return conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]

    @staticmethod
    def _event_row(row):
        return {"seq": row["seq"], "event_id": row["event_id"], "kind": row["kind"],
                "entity_id": row["entity_id"], "revision": row["revision"],
                "time": row["time"], "generation": row["generation"],
                "payload": json.loads(row["payload_json"]), "digest": row["digest"]}

    # --- batches ------------------------------------------------------------

    def propose_batch(self, body):
        """Freeze a batch body at its revision and return the stored record."""

        self._require_writable()
        body = validate_batch_body(body)
        self._bind_identity(body["repo"])
        frozen = digest(body)
        batch_id = body["batch_id"]
        revision = body["revision"]

        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM batches WHERE batch_id = ? AND revision = ?",
                (batch_id, revision)).fetchone()
            if existing is not None:
                if existing["digest"] != frozen:
                    raise CabinetError(
                        "REVISION_CONFLICT",
                        "%s revision %d is already frozen at digest %s"
                        % (batch_id, revision, existing["digest"]))
                return self._batch_row(existing)
            self._check_revision_order(conn, batch_id, revision)
            event = self._append_event_locked(
                conn, "batch.proposed", batch_id, revision,
                {"digest": frozen, "body": body})
            conn.execute(
                "INSERT INTO batches (batch_id, revision, body_json, digest, "
                "state, created_seq, updated_seq) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (batch_id, revision, canonical_json(body), frozen, "proposed",
                 event["seq"], event["seq"]))
            self._supersede_other_revisions(conn, batch_id, revision)
        return self.get_batch(batch_id, revision)

    def _check_revision_order(self, conn, batch_id, revision):
        """A new revision must be the one after the highest already stored.

        Without this, a lower revision number proposed after a higher one
        inserts a fresh batch that supersedes nothing above it, and both can
        then be approved. Two live agreements for one batch is the state the
        whole supersede rule exists to prevent, and `revision` comes from the
        caller's body, so ordering cannot be left to the caller's good manners.
        """

        highest = conn.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM batches WHERE batch_id = ?",
            (batch_id,)).fetchone()[0]
        if revision != highest + 1:
            raise CabinetError(
                "REVISION_ORDER",
                "%s is at revision %d; the next revision is %d, not %d"
                % (batch_id, highest, highest + 1, revision))

    def _supersede_other_revisions(self, conn, batch_id, revision):
        """Retire every other revision of a batch and revoke its grants.

        A newer revision is a different agreement. Leaving the old revision's
        grant live would let work approved against retired wording keep
        running. The predicate is "every other revision" rather than "every
        lower one" so that the one-live-agreement invariant does not depend on
        the ordering check above still being there.
        """

        rows = conn.execute(
            "SELECT * FROM batches WHERE batch_id = ? AND revision != ? "
            "AND state != 'superseded' ORDER BY revision",
            (batch_id, revision)).fetchall()
        for row in rows:
            check_transition(BATCH_TRANSITIONS, row["state"], "superseded",
                             "batch %s" % batch_id)
            event = self._append_event_locked(
                conn, "batch.state_changed", batch_id, row["revision"],
                {"from": row["state"], "to": "superseded",
                 "reason": "revision %d was proposed" % revision})
            conn.execute(
                "UPDATE batches SET state = 'superseded', updated_seq = ? "
                "WHERE batch_id = ? AND revision = ?",
                (event["seq"], batch_id, row["revision"]))
            self._revoke_grants_for(conn, batch_id, row["revision"],
                                    "revision %d was proposed" % revision)

    def _revoke_grants_for(self, conn, batch_id, revision, reason):
        live = conn.execute(
            "SELECT grant_id FROM grants WHERE batch_id = ? AND revision = ? "
            "AND revoked_seq IS NULL", (batch_id, revision)).fetchall()
        for row in live:
            self._revoke_grant_locked(conn, row["grant_id"], reason)

    def _revoke_grant_locked(self, conn, grant_id, reason):
        event = self._append_event_locked(
            conn, "approval.revoked", grant_id, None,
            {"grant_id": grant_id, "reason": reason})
        conn.execute("UPDATE grants SET revoked_seq = ? WHERE grant_id = ?",
                     (event["seq"], grant_id))
        return event

    def get_batch(self, batch_id, revision=None):
        conn = self._require_open()
        if revision is None:
            row = conn.execute(
                "SELECT * FROM batches WHERE batch_id = ? "
                "ORDER BY revision DESC LIMIT 1", (batch_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM batches WHERE batch_id = ? AND revision = ?",
                (batch_id, revision)).fetchone()
        if row is None:
            raise CabinetError("BATCH_NOT_FOUND",
                               "no batch %s at revision %s" % (batch_id, revision))
        return self._batch_row(row)

    def get_batches(self):
        conn = self._require_open()
        return [self._batch_row(row) for row in conn.execute(
            "SELECT * FROM batches ORDER BY batch_id, revision")]

    def current_batch(self):
        """Return the batch the company is working on, or None.

        A live state wins over history, and among live batches the most
        recently created one wins. Ordering by identifier would publish
        whichever name sorts last, which is not the same question.
        """

        conn = self._require_open()
        placeholders = ", ".join("?" * len(LIVE_BATCH_STATES))
        row = conn.execute(
            "SELECT * FROM batches WHERE state IN (%s) "
            "ORDER BY created_seq DESC LIMIT 1" % placeholders,
            LIVE_BATCH_STATES).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM batches ORDER BY created_seq DESC LIMIT 1").fetchone()
        return self._batch_row(row) if row is not None else None

    def set_batch_state(self, batch_id, revision, state, reason=None):
        """Record a batch state change as a new event plus its projection."""

        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM batches WHERE batch_id = ? AND revision = ?",
                (batch_id, revision)).fetchone()
            if row is None:
                raise CabinetError("BATCH_NOT_FOUND",
                                   "no batch %s at revision %s" % (batch_id, revision))
            check_transition(BATCH_TRANSITIONS, row["state"], state,
                             "batch %s" % batch_id)
            event = self._append_event_locked(
                conn, "batch.state_changed", batch_id, revision,
                {"from": row["state"], "to": state, "reason": reason})
            conn.execute(
                "UPDATE batches SET state = ?, updated_seq = ? "
                "WHERE batch_id = ? AND revision = ?",
                (state, event["seq"], batch_id, revision))
        return self.get_batch(batch_id, revision)

    @staticmethod
    def _batch_row(row):
        return {"batch_id": row["batch_id"], "revision": row["revision"],
                "body": json.loads(row["body_json"]), "digest": row["digest"],
                "state": row["state"], "created_seq": row["created_seq"],
                "updated_seq": row["updated_seq"]}

    # --- grants -------------------------------------------------------------
    #
    # These are internal. None of them is exposed as an MCP tool, and none of
    # them takes a caller's assertion that the owner said yes: the only input
    # that creates a grant is a client elicitation response, checked by
    # `is_owner_acceptance`, against a request this process recorded first.

    def record_approval_request(self, pending_request_id, kind, batch_id=None,
                                revision=None, scope=None):
        """Record what is being asked, and the state it is being asked about.

        The recorded digest, lease and pause state are the comparison used when
        the response arrives. Capturing them before the dialog opens is what
        makes a change during the wait detectable rather than silently accepted.
        """

        if kind not in ("batch", "setup"):
            raise CabinetError("FIELD_INVALID",
                               "approval request kind %r is not batch or setup" % kind)
        if kind == "batch":
            stored = self.get_batch(batch_id, revision)
            request = {"kind": "batch", "batch_id": stored["batch_id"],
                       "revision": stored["revision"], "digest": stored["digest"],
                       "state": stored["state"], "scope": None}
        else:
            checked = validate_setup_scope(scope or {})
            if self._identity is None or self._identity["repo"] != checked["repo"]:
                raise CabinetError(
                    "REPO_MISMATCH",
                    "setup names %s; this company is %s"
                    % (checked["repo"],
                       self._identity["repo"] if self._identity else "unbound"))
            request = {"kind": "setup", "batch_id": None, "revision": None,
                       "digest": digest(checked), "state": None,
                       "scope": checked}

        with self._transaction() as conn:
            lease = self._lease_row(conn)
            if lease is None:
                raise CabinetError("LEASE_REQUIRED",
                                   "no lead holds the company lease")
            self._check_not_paused(conn)
            if conn.execute("SELECT 1 FROM events WHERE entity_id = ? AND "
                            "kind = 'approval.requested' LIMIT 1",
                            (pending_request_id,)).fetchone() is not None:
                raise CabinetError("APPROVAL_REQUEST_USED",
                                   "request %s was already opened" % pending_request_id)
            request["lease"] = {"session_id": lease["session_id"],
                                "generation": lease["generation"]}
            request["pending_request_id"] = pending_request_id
            self._append_event_locked(conn, "approval.requested",
                                      pending_request_id, revision, request)
        return request

    def save_grant(self, pending_request_id, response):
        """Turn one client response to a batch request into a grant, or nothing.

        Returns the grant when the response is an acceptance, otherwise None.
        Raises when the batch, lease or pause state moved while the dialog was
        open, because the owner then answered a question about something else.
        """

        return self._save_grant(pending_request_id, response, "batch")

    def save_setup_grant(self, pending_request_id, response):
        """Turn one client response to a setup request into a setup grant."""

        return self._save_grant(pending_request_id, response, "setup")

    def _save_grant(self, pending_request_id, response, expected_kind):
        with self._transaction(fence=False) as conn:
            request = self._pending_request(conn, pending_request_id)
            if request["kind"] != expected_kind:
                raise CabinetError(
                    "FIELD_INVALID",
                    "request %s is a %s request, not %s"
                    % (pending_request_id, request["kind"], expected_kind))
            self._recheck_request(conn, request)
            if not is_owner_acceptance(response):
                self._append_event_locked(
                    conn, "approval.declined", pending_request_id,
                    request["revision"],
                    {"pending_request_id": pending_request_id,
                     "kind": request["kind"], "response": response})
                return None
            if expected_kind == "batch":
                return self._grant_batch(conn, request, response)
            return self._grant_setup(conn, request, response)

    def close_approval_request(self, pending_request_id, reason, detail=None):
        """Close a request the owner never answered, so it cannot be replayed.

        No response is recorded, because there was none: storing Cabinet's own
        placeholder in an owner-response field would make a non-answer look
        like an answer in the log. Nothing here rechecks the batch or the
        lease either, so a company that moved during the wait still reports
        the non-answer rather than raising about the movement.
        """

        with self._transaction(fence=False) as conn:
            request = self._pending_request(conn, pending_request_id)
            self._append_event_locked(
                conn, "approval.unanswered", pending_request_id,
                request["revision"],
                {"pending_request_id": pending_request_id,
                 "kind": request["kind"], "reason": reason, "detail": detail})
        return {"pending_request_id": pending_request_id, "reason": reason,
                "detail": detail}

    def _pending_request(self, conn, pending_request_id):
        row = conn.execute(
            "SELECT payload_json FROM events WHERE entity_id = ? AND "
            "kind = 'approval.requested' ORDER BY seq DESC LIMIT 1",
            (pending_request_id,)).fetchone()
        if row is None:
            raise CabinetError("APPROVAL_REQUEST_UNKNOWN",
                               "no pending approval request %s" % pending_request_id)
        answered = conn.execute(
            "SELECT 1 FROM events WHERE entity_id = ? AND kind IN "
            "('approval.granted', 'approval.declined', 'approval.unanswered') "
            "LIMIT 1", (pending_request_id,)).fetchone()
        if answered is not None:
            raise CabinetError("APPROVAL_REQUEST_USED",
                               "request %s was already answered" % pending_request_id)
        return json.loads(row["payload_json"])

    def _recheck_request(self, conn, request):
        lease = self._lease_row(conn)
        recorded = request["lease"]
        if lease is None or lease["session_id"] != recorded["session_id"] \
                or lease["generation"] != recorded["generation"]:
            raise CabinetError(
                "LEASE_CHANGED",
                "the lease moved on from generation %s while the dialog was open"
                % recorded["generation"])
        if self._session_id != lease["session_id"] \
                or self._generation != lease["generation"]:
            raise CabinetError(
                "LEASE_CHANGED",
                "this caller no longer holds generation %d" % lease["generation"])
        if lease["paused"]:
            raise CabinetError("PAUSED", "the company is paused: %s"
                               % (lease["paused_reason"] or "no reason recorded"))
        if request["kind"] == "setup":
            if self._identity is None \
                    or self._identity["repo"] != request["scope"]["repo"]:
                raise CabinetError("REPO_MISMATCH",
                                   "setup names %s" % request["scope"]["repo"])
            return
        row = conn.execute(
            "SELECT * FROM batches WHERE batch_id = ? AND revision = ?",
            (request["batch_id"], request["revision"])).fetchone()
        if row is None or row["digest"] != request["digest"]:
            raise CabinetError(
                "SCOPE_CHANGED",
                "%s revision %s no longer reads as it did when the question "
                "was asked" % (request["batch_id"], request["revision"]))
        if row["state"] not in APPROVABLE_BATCH_STATES:
            raise CabinetError(
                "SCOPE_CHANGED",
                "%s revision %s moved to %s while the dialog was open"
                % (request["batch_id"], request["revision"], row["state"]))

    def _grant_batch(self, conn, request, response):
        batch_id = request["batch_id"]
        revision = request["revision"]
        frozen = request["digest"]
        existing = conn.execute(
            "SELECT * FROM grants WHERE batch_id = ? AND revision = ? AND digest = ?",
            (batch_id, revision, frozen)).fetchone()
        if existing is not None:
            if existing["revoked_seq"] is not None:
                raise CabinetError(
                    "REVISION_SUPERSEDED",
                    "the grant for %s revision %d was revoked" % (batch_id, revision))
            self._append_event_locked(
                conn, "approval.granted", request["pending_request_id"], revision,
                {"grant_id": existing["grant_id"], "batch_id": batch_id,
                 "revision": revision, "digest": frozen, "repeat": True,
                 "response": response})
            return self._grant_row(existing)

        grant_id = "G%s" % uuid.uuid4().hex[:12]
        scope = {"repo": self._identity["repo"], "batch_id": batch_id,
                 "revision": revision}
        event = self._append_event_locked(
            conn, "approval.granted", request["pending_request_id"], revision,
            {"grant_id": grant_id, "batch_id": batch_id, "revision": revision,
             "digest": frozen, "repeat": False, "response": response})
        conn.execute(
            "INSERT INTO grants (grant_id, batch_id, revision, digest, scope_json, "
            "owner_response_json, approved_seq, revoked_seq) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (grant_id, batch_id, revision, frozen, canonical_json(scope),
             canonical_json(response), event["seq"]))
        current = conn.execute(
            "SELECT state FROM batches WHERE batch_id = ? AND revision = ?",
            (batch_id, revision)).fetchone()["state"]
        if current == "proposed":
            moved = self._append_event_locked(
                conn, "batch.state_changed", batch_id, revision,
                {"from": current, "to": "approved", "reason": "owner approval"})
            conn.execute(
                "UPDATE batches SET state = 'approved', updated_seq = ? "
                "WHERE batch_id = ? AND revision = ?",
                (moved["seq"], batch_id, revision))
        return self._grant_row(conn.execute(
            "SELECT * FROM grants WHERE grant_id = ?", (grant_id,)).fetchone())

    def _grant_setup(self, conn, request, response):
        scope = request["scope"]
        for row in conn.execute(
                "SELECT grant_id, scope_json FROM grants WHERE batch_id IS NULL "
                "AND revoked_seq IS NULL").fetchall():
            if json.loads(row["scope_json"]).get("repo") == scope["repo"]:
                self._revoke_grant_locked(conn, row["grant_id"],
                                          "a newer setup grant replaced it")
        grant_id = "G%s" % uuid.uuid4().hex[:12]
        frozen = request["digest"]
        event = self._append_event_locked(
            conn, "setup.granted", request["pending_request_id"], None,
            {"grant_id": grant_id, "repo": scope["repo"], "digest": frozen,
             "response": response})
        conn.execute(
            "INSERT INTO grants (grant_id, batch_id, revision, digest, scope_json, "
            "owner_response_json, approved_seq, revoked_seq) "
            "VALUES (?, NULL, NULL, ?, ?, ?, ?, NULL)",
            (grant_id, frozen, canonical_json(scope), canonical_json(response),
             event["seq"]))
        return self._grant_row(conn.execute(
            "SELECT * FROM grants WHERE grant_id = ?", (grant_id,)).fetchone())

    def record_owner_decision(self, subject, question, response, detail=None):
        """Record an owner decision that grants no authority to act.

        Charter approval and company-direction amendments travel this way. The
        response is stored verbatim; nothing here writes to the grants table.
        """

        decided = is_owner_acceptance(response)
        with self._transaction() as conn:
            event = self._append_event_locked(
                conn, "owner.decision", subject, None,
                {"subject": subject, "question": question, "detail": detail,
                 "response": response, "decided": decided})
        return event

    def revoke_grant(self, grant_id, reason):
        """Withdraw a live grant. Internal; never an MCP tool.

        Proposing a newer revision revokes the old one automatically. This is
        the same operation for the cases that are not a new revision, such as
        the owner withdrawing an approval for a batch that is still current.
        """

        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM grants WHERE grant_id = ?",
                               (grant_id,)).fetchone()
            if row is None:
                raise CabinetError("GRANT_NOT_FOUND", "no grant %s" % grant_id)
            if row["revoked_seq"] is None:
                self._revoke_grant_locked(conn, grant_id, reason)
        return self.get_grant(grant_id)

    def get_grant(self, grant_id):
        conn = self._require_open()
        row = conn.execute("SELECT * FROM grants WHERE grant_id = ?",
                           (grant_id,)).fetchone()
        if row is None:
            raise CabinetError("GRANT_NOT_FOUND", "no grant %s" % grant_id)
        return self._grant_row(row)

    def get_grants(self):
        """Every grant ever recorded, oldest first, revoked ones included."""

        conn = self._require_open()
        return [self._grant_row(row) for row in conn.execute(
            "SELECT * FROM grants ORDER BY approved_seq")]

    def batch_grant(self, batch_id, revision, digest_value):
        """The grant for exactly this batch revision and digest, or None."""

        conn = self._require_open()
        row = conn.execute(
            "SELECT * FROM grants WHERE batch_id = ? AND revision = ? AND digest = ?",
            (batch_id, revision, digest_value)).fetchone()
        return self._grant_row(row) if row is not None else None

    def has_grant_for_batch(self, batch_id):
        conn = self._require_open()
        return conn.execute("SELECT 1 FROM grants WHERE batch_id = ? LIMIT 1",
                            (batch_id,)).fetchone() is not None

    def active_setup_grant(self, repo):
        """The live setup grant for a repository, or None."""

        conn = self._require_open()
        for row in conn.execute(
                "SELECT * FROM grants WHERE batch_id IS NULL AND "
                "revoked_seq IS NULL ORDER BY approved_seq DESC"):
            if json.loads(row["scope_json"]).get("repo") == repo:
                return self._grant_row(row)
        return None

    @staticmethod
    def _grant_row(row):
        return {"grant_id": row["grant_id"], "batch_id": row["batch_id"],
                "revision": row["revision"], "digest": row["digest"],
                "kind": "batch" if row["batch_id"] else "setup",
                "scope": json.loads(row["scope_json"]),
                "owner_response": json.loads(row["owner_response_json"]),
                "approved_seq": row["approved_seq"],
                "revoked_seq": row["revoked_seq"]}

    # --- actions ------------------------------------------------------------

    def prepare_action(self, envelope):
        """Validate an action envelope and persist the intent to run it."""

        self._require_writable()
        self._check_not_paused()
        envelope = validate_action_envelope(envelope)
        self.get_batch(envelope["batch_id"], envelope["revision"])
        intent = digest(action_identity(envelope))

        with self._transaction() as conn:
            by_key = conn.execute(
                "SELECT * FROM actions WHERE idempotency_key = ?",
                (envelope["idempotency_key"],)).fetchone()
            if by_key is not None:
                if by_key["digest"] != intent:
                    raise CabinetError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key %s was already used for a different "
                        "action body" % envelope["idempotency_key"])
                return self._action_row(by_key)
            by_id = conn.execute("SELECT * FROM actions WHERE action_id = ?",
                                 (envelope["action_id"],)).fetchone()
            if by_id is not None:
                raise CabinetError(
                    "IDEMPOTENCY_CONFLICT",
                    "action %s already exists under idempotency key %s"
                    % (envelope["action_id"], by_id["idempotency_key"]))
            event = self._append_event_locked(
                conn, "action.prepared", envelope["action_id"],
                envelope["revision"], {"digest": intent, "envelope": envelope})
            conn.execute(
                "INSERT INTO actions (action_id, idempotency_key, kind, batch_id, "
                "revision, payload_json, digest, state, external_ref_json, "
                "evidence_json, created_seq, updated_seq) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (envelope["action_id"], envelope["idempotency_key"],
                 envelope["kind"], envelope["batch_id"], envelope["revision"],
                 canonical_json(envelope), intent, "prepared", None, None,
                 event["seq"], event["seq"]))
        return self.get_action(envelope["action_id"])

    def get_action(self, action_id):
        conn = self._require_open()
        row = conn.execute("SELECT * FROM actions WHERE action_id = ?",
                           (action_id,)).fetchone()
        if row is None:
            raise CabinetError("ACTION_NOT_FOUND", "no action %s" % action_id)
        return self._action_row(row)

    def update_action(self, action_id, state, external_ref=None, evidence=None):
        """Move an action through its state machine and record the evidence.

        A None `external_ref` or `evidence` leaves the stored value alone; pass
        a value to replace it.
        """

        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM actions WHERE action_id = ?",
                               (action_id,)).fetchone()
            if row is None:
                raise CabinetError("ACTION_NOT_FOUND", "no action %s" % action_id)
            check_transition(ACTION_TRANSITIONS, row["state"], state,
                             "action %s" % action_id)
            event = self._append_event_locked(
                conn, "action.state_changed", action_id, row["revision"],
                {"from": row["state"], "to": state,
                 "external_ref": external_ref, "evidence": evidence})
            conn.execute(
                "UPDATE actions SET state = ?, updated_seq = ?, "
                "external_ref_json = COALESCE(?, external_ref_json), "
                "evidence_json = COALESCE(?, evidence_json) WHERE action_id = ?",
                (state, event["seq"],
                 canonical_json(external_ref) if external_ref is not None else None,
                 canonical_json(evidence) if evidence is not None else None,
                 action_id))
        return self.get_action(action_id)

    @staticmethod
    def _action_row(row):
        envelope = json.loads(row["payload_json"])
        return {"action_id": row["action_id"],
                "idempotency_key": row["idempotency_key"], "kind": row["kind"],
                "batch_id": row["batch_id"], "revision": row["revision"],
                "digest": row["digest"], "state": row["state"],
                "payload": envelope["payload"],
                "expected_before": envelope["expected_before"],
                "external_ref": json.loads(row["external_ref_json"])
                if row["external_ref_json"] else None,
                "evidence": json.loads(row["evidence_json"])
                if row["evidence_json"] else None,
                "created_seq": row["created_seq"], "updated_seq": row["updated_seq"]}

    # --- assignments --------------------------------------------------------

    def reserve_assignment(self, assignment_id, batch_id, revision, role,
                           work_key, issue_number=None):
        """Claim one work item. A second live claim on it is refused."""

        self._require_writable()
        self._check_not_paused()
        self.get_batch(batch_id, revision)
        with self._transaction() as conn:
            event = self._append_event_locked(
                conn, "assignment.reserved", assignment_id, revision,
                {"batch_id": batch_id, "role": role, "work_key": work_key,
                 "issue_number": issue_number})
            try:
                conn.execute(
                    "INSERT INTO assignments (assignment_id, batch_id, revision, "
                    "role, issue_number, workspace_id, terminal_id, "
                    "native_session_id, generation, state, work_key, created_seq, "
                    "updated_seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (assignment_id, batch_id, revision, role, issue_number,
                     None, None, None, self._generation or 0, "reserved",
                     work_key, event["seq"], event["seq"]))
            except sqlite3.IntegrityError as problem:
                raise CabinetError(
                    "ASSIGNMENT_CONFLICT",
                    "work item %s already has a live assignment (%s)"
                    % (work_key, problem))
            except sqlite3.OperationalError as problem:
                raise _lock_error(problem, "reserve %s" % work_key) from problem
        return self.get_assignment(assignment_id)

    def get_assignment(self, assignment_id):
        conn = self._require_open()
        row = conn.execute("SELECT * FROM assignments WHERE assignment_id = ?",
                           (assignment_id,)).fetchone()
        if row is None:
            raise CabinetError("ASSIGNMENT_NOT_FOUND",
                               "no assignment %s" % assignment_id)
        return self._assignment_row(row)

    def get_assignments(self, states=None):
        conn = self._require_open()
        rows = conn.execute("SELECT * FROM assignments ORDER BY created_seq")
        found = [self._assignment_row(row) for row in rows]
        if states is None:
            return found
        return [row for row in found if row["state"] in states]

    def set_assignment_state(self, assignment_id, state, **fields):
        """Move an assignment through its state machine."""

        allowed = ("workspace_id", "terminal_id", "native_session_id")
        for key in fields:
            if key not in allowed:
                raise CabinetError("FIELD_UNKNOWN",
                                   "assignment has no field %r" % key)
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM assignments WHERE assignment_id = ?",
                               (assignment_id,)).fetchone()
            if row is None:
                raise CabinetError("ASSIGNMENT_NOT_FOUND",
                                   "no assignment %s" % assignment_id)
            check_transition(ASSIGNMENT_TRANSITIONS, row["state"], state,
                             "assignment %s" % assignment_id)
            event = self._append_event_locked(
                conn, "assignment.state_changed", assignment_id, row["revision"],
                dict({"from": row["state"], "to": state}, **fields))
            assignments = ["state = ?", "updated_seq = ?"]
            values = [state, event["seq"]]
            for key in allowed:
                if key in fields:
                    assignments.append("%s = ?" % key)
                    values.append(fields[key])
            values.append(assignment_id)
            conn.execute("UPDATE assignments SET %s WHERE assignment_id = ?"
                         % ", ".join(assignments), values)
        return self.get_assignment(assignment_id)

    @staticmethod
    def _assignment_row(row):
        return {"assignment_id": row["assignment_id"], "batch_id": row["batch_id"],
                "revision": row["revision"], "role": row["role"],
                "issue_number": row["issue_number"],
                "workspace_id": row["workspace_id"],
                "terminal_id": row["terminal_id"],
                "native_session_id": row["native_session_id"],
                "generation": row["generation"], "state": row["state"],
                "work_key": row["work_key"], "created_seq": row["created_seq"],
                "updated_seq": row["updated_seq"]}

    # --- lease --------------------------------------------------------------

    def acquire_lease(self, session_id, pid, process_start):
        """Take the company lease and bump the fencing generation."""

        with self._transaction(fence=False) as conn:
            row = self._lease_row(conn)
            generation = 1
            paused = 0
            paused_reason = None
            if row is not None:
                same_process = (row["pid"], row["process_start"]) == \
                    (pid, process_start)
                if row["session_id"] != session_id and not same_process and \
                        self._process_alive(row["pid"], row["process_start"]):
                    raise CabinetError(
                        "LEAD_ACTIVE",
                        "session %s (pid %d) still holds generation %d"
                        % (row["session_id"], row["pid"], row["generation"]))
                generation = row["generation"] + 1
                paused = row["paused"]
                paused_reason = row["paused_reason"]
            now = self._clock()
            self._generation = generation
            self._session_id = session_id
            self._append_event_locked(
                conn, "lease.acquired", session_id, generation,
                {"pid": pid, "generation": generation,
                 "superseded": row["session_id"] if row is not None else None})
            conn.execute("DELETE FROM lease WHERE key = 1")
            conn.execute(
                "INSERT INTO lease (key, session_id, pid, process_start, "
                "generation, last_seen, paused, paused_reason) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, pid, process_start, generation, now, paused,
                 paused_reason))
        return self.get_lease()

    def now(self):
        """Return the clock's current UTC ISO reading."""

        return self._clock()

    def get_handoffs(self):
        """Return every recorded handoff, oldest first, without its body."""

        conn = self._require_open()
        rows = conn.execute(
            "SELECT handoff_id, batch_id, revision, from_role, to_role, state, "
            "attempts FROM handoffs ORDER BY created_seq")
        return [dict(row) for row in rows]

    def get_lease(self):
        row = self._lease_row()
        if row is None:
            return None
        return {"session_id": row["session_id"], "pid": row["pid"],
                "process_start": row["process_start"],
                "generation": row["generation"], "last_seen": row["last_seen"],
                "paused": bool(row["paused"]),
                "paused_reason": row["paused_reason"]}

    def set_lease_last_seen(self, time=None):
        """Record a heartbeat. A stale heartbeat alone never releases a lease."""

        with self._transaction() as conn:
            conn.execute("UPDATE lease SET last_seen = ? WHERE key = 1",
                         (time or self._clock(),))
        return self.get_lease()

    def _require_lease(self, conn):
        row = self._lease_row(conn)
        if row is None:
            raise CabinetError("LEASE_REQUIRED",
                               "no lead holds the company lease")
        return row

    def pause(self, reason):
        """Fence new actions and assignments until `resume()`."""

        with self._transaction(fence=False) as conn:
            self._require_lease(conn)
            self._check_fence(conn)
            self._append_event_locked(conn, "company.paused", "company", None,
                                      {"reason": reason})
            conn.execute("UPDATE lease SET paused = 1, paused_reason = ? "
                         "WHERE key = 1", (reason,))
        return self.get_lease()

    def resume(self, reason=None):
        with self._transaction(fence=False) as conn:
            self._require_lease(conn)
            self._check_fence(conn)
            self._append_event_locked(conn, "company.resumed", "company", None,
                                      {"reason": reason})
            conn.execute("UPDATE lease SET paused = 0, paused_reason = NULL "
                         "WHERE key = 1")
        return self.get_lease()

    def is_paused(self):
        row = self._lease_row()
        return bool(row["paused"]) if row is not None else False

    # --- documents ----------------------------------------------------------

    def put_document(self, name, content, source):
        """Store a document revision. Identical content adds no revision."""

        if not DOCUMENT_NAME_PATTERN.match(name or ""):
            raise CabinetError("FIELD_INVALID",
                               "document name %r must be a plain .md filename" % name)
        content_digest = digest({"name": name, "content": content})
        with self._transaction() as conn:
            latest = conn.execute(
                "SELECT * FROM documents WHERE name = ? "
                "ORDER BY revision DESC LIMIT 1", (name,)).fetchone()
            if latest is not None and latest["digest"] == content_digest:
                stored = self._document_row(latest)
                stored["created"] = False
                return stored
            revision = (latest["revision"] + 1) if latest is not None else 1
            supersedes = latest["revision"] if latest is not None else None
            event = self._append_event_locked(
                conn, "document.imported", name, revision,
                {"digest": content_digest, "source": source,
                 "supersedes": supersedes})
            conn.execute(
                "INSERT INTO documents (name, revision, content, digest, "
                "source_json, supersedes, created_seq) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, revision, content, content_digest, canonical_json(source),
                 supersedes, event["seq"]))
        stored = self.get_document(name, revision)
        stored["created"] = True
        return stored

    def get_document(self, name, revision=None):
        conn = self._require_open()
        if revision is None:
            row = conn.execute(
                "SELECT * FROM documents WHERE name = ? "
                "ORDER BY revision DESC LIMIT 1", (name,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM documents WHERE name = ? AND revision = ?",
                (name, revision)).fetchone()
        if row is None:
            raise CabinetError("DOCUMENT_NOT_FOUND",
                               "no document %s at revision %s" % (name, revision))
        return self._document_row(row)

    def get_documents(self):
        """Return the latest revision of every stored document, by name."""

        conn = self._require_open()
        rows = conn.execute(
            "SELECT d.* FROM documents d JOIN (SELECT name, MAX(revision) AS top "
            "FROM documents GROUP BY name) latest ON d.name = latest.name "
            "AND d.revision = latest.top ORDER BY d.name")
        return [self._document_row(row) for row in rows]

    @staticmethod
    def _document_row(row):
        return {"name": row["name"], "revision": row["revision"],
                "content": row["content"], "digest": row["digest"],
                "source": json.loads(row["source_json"]),
                "supersedes": row["supersedes"], "created_seq": row["created_seq"]}

    # --- backup and restore -------------------------------------------------

    def backup(self, destination, progress=None):
        """Copy the database and company documents into a new directory."""

        conn = self._require_open()
        destination = Path(destination)
        if destination.exists():
            raise CabinetError("BACKUP_DESTINATION_EXISTS",
                               "%s already exists" % destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(mode=PRIVATE_DIR_MODE)
        (destination / RUNTIME_DIRECTORY).mkdir(mode=PRIVATE_DIR_MODE)
        (destination / "documents").mkdir(mode=PRIVATE_DIR_MODE)

        copy_path = destination / RUNTIME_DIRECTORY / DATABASE_NAME
        target = sqlite3.connect(str(copy_path), isolation_level=None)
        try:
            conn.backup(target, pages=1 if progress else -1,
                        progress=progress, sleep=0)
            highest = target.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CabinetError("BACKUP_INVALID",
                                   "the copied database failed integrity_check")
        finally:
            target.close()
        os.chmod(str(copy_path), PRIVATE_FILE_MODE)

        if self.identity_path.exists():
            shutil.copy2(str(self.identity_path),
                         str(destination / RUNTIME_DIRECTORY / IDENTITY_NAME))
        for document in sorted(self.root.glob("*.md")):
            if document.is_symlink() or not document.is_file():
                continue
            shutil.copy2(str(document), str(destination / "documents" / document.name))

        files = []
        for path in sorted(destination.rglob("*")):
            if not path.is_file():
                continue
            files.append({"path": str(path.relative_to(destination)),
                          "bytes": path.stat().st_size,
                          "sha256": _hash_file(path)})
        manifest = {"created": self._clock(),
                    "repo": self._identity["repo"] if self._identity else None,
                    "schema_version": SCHEMA_VERSION,
                    "max_event_seq": highest,
                    "files": files}
        _write_private(destination / "manifest.json", canonical_json(manifest) + "\n")
        return manifest

    @classmethod
    def restore(cls, backup_dir, destination):
        """Rebuild a company directory from a backup, into a new directory."""

        backup_dir = Path(backup_dir)
        destination = Path(destination)
        manifest_path = backup_dir / "manifest.json"
        if not manifest_path.exists():
            raise CabinetError("BACKUP_INVALID", "%s has no manifest" % backup_dir)
        if destination.exists():
            raise CabinetError("RESTORE_DESTINATION_EXISTS",
                               "%s already exists; restore into a new directory"
                               % destination)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            # The manifest supplies both the path and its hash, so hashing
            # proves nothing about where a file is allowed to land. Check
            # containment first, on both ends of the copy.
            relative = Path(entry["path"])
            if relative.is_absolute() or ".." in relative.parts \
                    or not relative.parts:
                raise CabinetError("UNSAFE_PATH",
                                   "manifest entry %r escapes the backup"
                                   % entry["path"])
            source = backup_dir / relative
            if not _within(backup_dir, source):
                raise CabinetError("UNSAFE_PATH",
                                   "manifest entry %r resolves outside %s"
                                   % (entry["path"], backup_dir))
            if not source.exists():
                raise CabinetError("BACKUP_INVALID", "missing %s" % entry["path"])
            if _hash_file(source) != entry["sha256"]:
                raise CabinetError("BACKUP_INVALID",
                                   "%s does not match its recorded hash"
                                   % entry["path"])
        destination.mkdir(mode=PRIVATE_DIR_MODE, parents=True)
        (destination / RUNTIME_DIRECTORY).mkdir(mode=PRIVATE_DIR_MODE)
        restored = []
        for entry in manifest["files"]:
            relative = Path(entry["path"])
            if relative.parts[0] == RUNTIME_DIRECTORY:
                target = destination / relative
            elif relative.parts[0] == "documents":
                target = destination / relative.name
            else:
                continue
            if not _within(destination, target):
                raise CabinetError("UNSAFE_PATH",
                                   "manifest entry %r would write outside %s"
                                   % (entry["path"], destination))
            target.parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
            shutil.copy2(str(backup_dir / relative), str(target))
            restored.append(str(target.relative_to(destination)))
        database = destination / RUNTIME_DIRECTORY / DATABASE_NAME
        conn = sqlite3.connect(str(database))
        try:
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            highest = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]
        finally:
            conn.close()
        if check != "ok":
            raise CabinetError("BACKUP_INVALID",
                               "the restored database failed integrity_check")
        return {"destination": str(destination), "repo": manifest.get("repo"),
                "max_event_seq": highest, "integrity_check": check,
                "files": restored}

    # --- exports ------------------------------------------------------------

    def export_company(self):
        """Write the human-readable views. See exports.export_company."""

        from .exports import export_company

        return export_company(self)


def _hash_file(path):
    engine = hashlib.sha256()
    with open(str(path), "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            engine.update(block)
    return engine.hexdigest()
