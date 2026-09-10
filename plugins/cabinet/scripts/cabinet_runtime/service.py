"""The bounded set of operations the model may ask this company to perform.

Every tool here is a named operation with a closed schema. There is no shell,
no HTTP, no SQL, no file write and no token retrieval reachable through this
surface, and an argument the schema does not name is refused rather than
ignored. What the model supplies is data; what it may cause is fixed by this
module.

Three gates run before any method body, in this order:

1. **The schema.** Unknown, missing and wrongly typed arguments are refused
   with the F2 field codes, so a forged extra field is a failure rather than
   an input.
2. **The launch context.** Reads work on the ordinary plugin connection.
   Everything that writes needs the verified restricted launch, and says so
   with `RESTRICTED_SESSION_REQUIRED` instead of failing somewhere deeper.
3. **The lease.** A connection that does not hold the current generation is
   read-only, because two leads writing the same company is the failure the
   lease exists to prevent.

`execute_action` adds a fourth, and its order is the point: `Policy.authorize`
runs before an executor is even looked up, so a forbidden kind fails with its
F3 code whether or not the adapter that would have run it exists yet.

Operations whose adapters land in later tasks refuse with a stable
`NOT_IMPLEMENTED_YET` naming the task that owns them. A caller can tell "not
allowed" from "not built" without reading this file.
"""

import time
import uuid

from . import contracts
from .approval import ApprovalService
from .errors import CabinetError
from .exports import VIEW_NAMES
from .policy import Policy
from .store import own_process_identity

#: Longest wait `wait_events` will hold a connection open, in seconds.
MAX_WAIT_SECONDS = 30.0
WAIT_POLL_SECONDS = 0.25

#: Bounds on a context read, in characters of document text.
DEFAULT_CONTEXT_BYTES = 8192
MAX_CONTEXT_BYTES = 65536

DEFAULT_EVENT_LIMIT = 25
MAX_EVENT_LIMIT = 200

CHECKPOINT_KINDS = ("session_open", "session_close", "batch_end")
HANDOFF_TRANSITIONS = ("sent", "acknowledged", "resolved", "failed",
                       "superseded")
DUE_HANDOFF_STATES = ("recorded", "sent", "acknowledged")

#: Fields of the launch record the entrypoint hands over. The capability is
#: verified before this point and is deliberately not one of them.
LAUNCH_FIELDS = ("kind", "launch_id", "company_dir", "repo", "role",
                 "profile_path", "profile_digest", "session_id")

#: Words that must never name a field in a launch context. A context is a set
#: of facts about the launch, never a secret the service could leak.
SECRET_WORDS = ("capability", "secret", "token", "password", "credential",
                "key")

_STRING = {"type": "string"}
_INTEGER = {"type": "integer"}
_NUMBER = {"type": "number"}
_OBJECT = {"type": "object"}
_ARRAY = {"type": "array"}


def _schema(properties=None, required=()):
    return {"type": "object", "properties": dict(properties or {}),
            "required": list(required), "additionalProperties": False}


def _enum(values):
    return {"type": "string", "enum": list(values)}


#: name -> (access, schema, description). `access` is `read` (any session),
#: `launch` (restricted launch, no lease yet) or `write` (both).
TOOL_SPECS = {
    "snapshot": (
        "read", _schema({"limit": _INTEGER}),
        "Company identity, the current batch, recorded handoffs and the most "
        "recent events, each with the sequence number it was observed at."),
    "doctor": (
        "read", _schema(),
        "Read-only diagnosis of this connection: store, identity, lease, "
        "pause state, launch kind and dialog availability."),
    "context": (
        "read", _schema({"name": _STRING, "max_bytes": _INTEGER}),
        "Bounded read of the company's stored documents. Names one document, "
        "or returns the latest revision of each within a byte budget."),
    "wait_events": (
        "read", _schema({"after_seq": _INTEGER, "timeout_seconds": _NUMBER}),
        "Durable events recorded after a sequence number, plus handoffs that "
        "are still due. Waits up to 30 seconds for the first one."),
    "acquire_lead": (
        "launch", _schema({"session_id": _STRING}),
        "Take the company lease for this session and bump the fencing "
        "generation. Every writing tool requires it."),
    "setup": (
        "write", _schema({"scope": _OBJECT}, ("scope",)),
        "Ask the owner once for standing authority over this repository's "
        "board and the checks that may run."),
    "propose_batch": (
        "write", _schema({"body": _OBJECT}, ("body",)),
        "Freeze a batch body as a numbered revision with a content digest. "
        "This proposes work; it does not approve it."),
    "request_owner_approval": (
        "write", _schema({"batch_id": _STRING, "revision": _INTEGER},
                         ("batch_id", "revision")),
        "Show the owner the stored batch and record their answer. Only an "
        "accepted dialog creates a grant."),
    "record_handoff": (
        "write", _schema({"envelope": _OBJECT}, ("envelope",)),
        "Record a handoff envelope durably before anything is sent."),
    "update_handoff": (
        "write", _schema({"handoff_id": _STRING,
                          "transition": _enum(HANDOFF_TRANSITIONS),
                          "evidence": _ARRAY},
                         ("handoff_id", "transition")),
        "Move a recorded handoff through its state machine with evidence."),
    "prepare_action": (
        "write", _schema({"envelope": _OBJECT}, ("envelope",)),
        "Validate an action envelope and persist the intent to run it. "
        "Preparing an action is never permission to execute it."),
    "execute_action": (
        "write", _schema({"action_id": _STRING}, ("action_id",)),
        "Authorize a prepared action against the current grant, scope, lease "
        "and pause state, then run it through its scoped adapter."),
    "register_session": (
        "write", _schema({"assignment_id": _STRING, "registration": _OBJECT},
                         ("assignment_id", "registration")),
        "Bind a launched worker's own session identity to its assignment."),
    "record_verdict": (
        "write", _schema({"assignment_id": _STRING, "revision_sha": _STRING,
                          "reviewer_role": _STRING, "outcome": _STRING,
                          "evidence": _ARRAY},
                         ("assignment_id", "revision_sha", "reviewer_role",
                          "outcome")),
        "Record an independent verification verdict at an exact revision."),
    "pause": (
        "write", _schema({"reason": _STRING}, ("reason",)),
        "Fence new actions and assignments before messaging anyone. A pause "
        "survives a change of lead."),
    "reconcile": (
        "write", _schema({"observations": _OBJECT}, ("observations",)),
        "Compare adapter-collected observations with stored state and "
        "propose recovery. Only trusted observations are accepted."),
    "checkpoint": (
        "write", _schema({"kind": _enum(CHECKPOINT_KINDS), "summary": _STRING},
                         ("kind", "summary")),
        "Record a session_open, session_close or batch_end checkpoint."),
    "export_company": (
        "write", _schema(),
        "Rewrite the human-readable company views atomically."),
    "backup": (
        "write", _schema(),
        "Write a consistent copy of the database and documents with a "
        "manifest of digests."),
}

TOOL_NAMES = tuple("cabinet_%s" % name for name in TOOL_SPECS)
READ_TOOLS = tuple("cabinet_%s" % name for name, spec in TOOL_SPECS.items()
                   if spec[0] == "read")
MUTATION_TOOLS = tuple(name for name in TOOL_NAMES if name not in READ_TOOLS)


def validate_launch(launch, store=None):
    """Return the launch context, or raise `LAUNCH_CONTEXT_INVALID`."""

    if launch is None:
        return None
    if not isinstance(launch, dict):
        raise CabinetError("LAUNCH_CONTEXT_INVALID",
                           "a launch context must be an object")
    for field in launch:
        lowered = str(field).lower()
        if any(word in lowered for word in SECRET_WORDS):
            raise CabinetError(
                "LAUNCH_CONTEXT_INVALID",
                "a launch context must not carry %r: the capability is "
                "verified by the entrypoint and never held here" % field)
    missing = [field for field in LAUNCH_FIELDS if field not in launch]
    if missing:
        raise CabinetError("LAUNCH_CONTEXT_INVALID",
                           "launch context is missing %s" % ", ".join(missing))
    unknown = [field for field in launch if field not in LAUNCH_FIELDS]
    if unknown:
        raise CabinetError("LAUNCH_CONTEXT_INVALID",
                           "launch context has unknown %s"
                           % ", ".join(sorted(unknown)))
    if launch["kind"] != "restricted":
        raise CabinetError("LAUNCH_CONTEXT_INVALID",
                           "launch kind %r is not a restricted launch"
                           % (launch["kind"],))
    if store is not None:
        from pathlib import Path

        if Path(launch["company_dir"]).resolve() != store.root:
            raise CabinetError(
                "LAUNCH_CONTEXT_INVALID",
                "the launch context names another company directory")
        identity = store.identity
        if identity is not None and launch["repo"] != identity["repo"]:
            raise CabinetError("LAUNCH_CONTEXT_INVALID",
                               "the launch context names another repository")
    return dict(launch)


class CabinetService:
    """The typed writer for one company."""

    def __init__(self, store, github=None, superset=None, clock=None,
                 elicitor=None, profile_builder=None, launch=None,
                 sleeper=None, monotonic=None):
        self.store = store
        self.github = github
        self.superset = superset
        self.clock = clock or store.now
        self.elicitor = elicitor
        self.profile_builder = profile_builder
        self.launch = validate_launch(launch, store)
        self._sleep = sleeper or time.sleep
        self._monotonic = monotonic or time.monotonic

    # --- the exposed surface -----------------------------------------------

    def tool_names(self):
        return list(TOOL_NAMES)

    def has_tool(self, name):
        return name in TOOL_NAMES

    def tools(self):
        """Tool definitions for `tools/list`.

        An ordinary plugin-loaded connection lists only what it can do. The
        writing names stay callable so an attempt to use one is refused by a
        stable code rather than by a confusing unknown-tool error.
        """

        names = TOOL_NAMES if self.launch else READ_TOOLS
        return [self._definition(name) for name in names]

    def _definition(self, name):
        access, schema, description = TOOL_SPECS[name[len("cabinet_"):]]
        return {"name": name, "description": description,
                "inputSchema": schema,
                "annotations": {"readOnlyHint": access == "read",
                                "openWorldHint": False}}

    def call(self, name, arguments):
        """Validate, authorize and run one named operation.

        The store's lock is held for the whole operation, because tool calls
        run on worker threads while the protocol thread keeps reading. An
        owner dialog is the one thing that gives the lock back while it waits:
        a question the owner has not answered must not stop the company being
        read, and F3 already treats state that moved during a dialog as a
        reason to refuse the grant rather than a race to prevent.
        """

        if not self.has_tool(name):
            raise CabinetError("TOOL_UNKNOWN", "no Cabinet tool named %s" % name)
        method = name[len("cabinet_"):]
        access, schema, _description = TOOL_SPECS[method]
        values = _validate_arguments(arguments, schema, method)
        with self.store.lock:
            self._authorize(access, method)
            return getattr(self, method)(**values)

    def _authorize(self, access, method):
        if access == "read":
            return
        if self.launch is None:
            raise CabinetError(
                "RESTRICTED_SESSION_REQUIRED",
                "cabinet_%s needs the verified restricted launch; this "
                "connection may only read" % method)
        if access == "launch":
            return
        lease = self.store.get_lease()
        if lease is None or self.store.generation != lease["generation"]:
            raise CabinetError(
                "LEASE_REQUIRED",
                "cabinet_%s needs this session to hold the company lease; "
                "call cabinet_acquire_lead first" % method)

    # --- reads --------------------------------------------------------------

    def snapshot(self, limit=None):
        limit = DEFAULT_EVENT_LIMIT if limit is None \
            else max(0, min(int(limit), MAX_EVENT_LIMIT))
        events = self.store.get_events()
        current = self.store.current_batch()
        return {
            "company": self._company(),
            "batch": current,
            "batches": [{"batch_id": row["batch_id"], "revision": row["revision"],
                         "state": row["state"], "digest": row["digest"]}
                        for row in self.store.get_batches()],
            "handoffs": self.store.get_handoffs(),
            "events": events[-limit:] if limit else [],
            "freshness": {"observed": self.clock(),
                          "max_event_seq": self.store.max_event_seq(),
                          "events_returned": min(limit, len(events))},
        }

    def doctor(self):
        checks = []

        def note(check, status, detail):
            checks.append({"check": check, "status": status, "detail": detail})

        identity = self.store.identity
        note("store", "read_only" if self.store.read_only else "open",
             "schema %d at %s" % (contracts.SCHEMA_VERSION, self.store.root))
        note("identity", "bound" if identity else "unbound",
             identity["repo"] if identity else "no repository is bound yet")
        lease = self.store.get_lease()
        if lease is None:
            note("lease", "absent", "no lead holds this company")
        elif self.store.generation == lease["generation"]:
            note("lease", "held", "generation %d" % lease["generation"])
        else:
            note("lease", "elsewhere",
                 "another lead holds generation %d" % lease["generation"])
        note("pause", "paused" if self.store.is_paused() else "running",
             lease["paused_reason"] if lease and lease["paused"] else "")
        note("launch", "restricted" if self.launch else "ordinary",
             "role %s" % self.launch["role"] if self.launch
             else "reads only; mutation needs a verified launch")
        note("dialog", "wired" if self.elicitor is not None else "absent",
             "owner approval needs a client that can show a form")
        note("tools", "ok", "%d of %d operations exposed"
             % (len(self.tools()), len(TOOL_NAMES)))
        statuses = {check["check"]: check["status"] for check in checks}
        return {"ok": statuses["store"] == "open"
                and statuses["identity"] == "bound",
                "generated": self.clock(), "checks": checks}

    def context(self, name=None, max_bytes=None):
        budget = DEFAULT_CONTEXT_BYTES if max_bytes is None \
            else max(0, min(int(max_bytes), MAX_CONTEXT_BYTES))
        documents = [self.store.get_document(name)] if name \
            else self.store.get_documents()
        selected = []
        spent = 0
        for document in documents:
            text = document["content"]
            body = text[:max(0, budget - spent)]
            spent += len(body)
            selected.append({"name": document["name"],
                             "revision": document["revision"],
                             "digest": document["digest"],
                             "bytes": len(text),
                             "truncated": len(body) < len(text),
                             "content": body})
        return {"documents": selected, "max_bytes": budget,
                "views": list(VIEW_NAMES)}

    def wait_events(self, after_seq=0, timeout_seconds=0):
        """Return events after a cursor, waiting briefly for the first.

        This is the minimal form. O2 extends it with the handoff and message
        wake-ups the operating loop needs.
        """

        after_seq = max(0, int(after_seq or 0))
        timeout = min(max(float(timeout_seconds or 0), 0.0), MAX_WAIT_SECONDS)
        deadline = self._monotonic() + timeout
        while True:
            events = self.store.get_events(after_seq=after_seq)
            due = [row for row in self.store.get_handoffs()
                   if row["state"] in DUE_HANDOFF_STATES]
            remaining = deadline - self._monotonic()
            if events or due or remaining <= 0:
                break
            self._sleep(min(WAIT_POLL_SECONDS, remaining))
        return {"after_seq": after_seq, "events": events, "handoffs_due": due,
                "timeout_seconds": timeout,
                "max_event_seq": self.store.max_event_seq()}

    # --- lease, approval and batches ---------------------------------------

    def acquire_lead(self, session_id=None):
        session = session_id or (self.launch or {}).get("session_id") \
            or uuid.uuid4().hex
        pid, marker = own_process_identity()
        lease = self.store.acquire_lease(session, pid, marker)
        return {"acquired": True, "generation": lease["generation"],
                "paused": lease["paused"], "session_id": session}

    def setup(self, scope):
        self._check_dialog()
        return self._approvals().request_setup(scope)

    def _check_dialog(self):
        """Refuse before recording anything when no dialog can be shown.

        An approval request is written to the event log before the owner is
        asked, so that a later answer can be matched to it. A client that can
        never show the dialog would leave a pending request nothing can ever
        answer, so the refusal happens first.
        """

        available = getattr(self.elicitor, "available", None)
        if callable(available) and not available():
            raise CabinetError(
                "ELICITATION_UNSUPPORTED",
                "the connected client cannot show the owner a form dialog, so "
                "nothing can be approved from this session")

    def propose_batch(self, body):
        return self.store.propose_batch(body)

    def request_owner_approval(self, batch_id, revision):
        self._check_dialog()
        return self._approvals().request(batch_id, revision)

    def _approvals(self):
        if self.elicitor is None:
            raise CabinetError("ELICITATION_UNSUPPORTED",
                               "this connection has no owner dialog")
        return ApprovalService(self.store,
                               _WaitingElicitor(self.elicitor, self.store.lock))

    # --- actions ------------------------------------------------------------

    def prepare_action(self, envelope):
        return self.store.prepare_action(envelope)

    def execute_action(self, action_id):
        """Authorize first, then look for an executor.

        The order is the contract: a kind with no executor at any approval
        level must fail as forbidden, not as unfinished, so that adding an
        adapter later can never turn a refusal into an execution.
        """

        stored = self.store.get_action(action_id)
        envelope = {field: stored[field] for field in contracts.ACTION_FIELDS}
        grant = Policy(self.store).authorize(envelope)
        raise CabinetError(
            "NOT_IMPLEMENTED_YET",
            "%s is authorized under grant %s but has no executor in this "
            "release: O3 lands the board adapter and O4 the workspace adapter"
            % (stored["kind"], grant["grant_id"]))

    # --- operations later tasks own ----------------------------------------

    def record_handoff(self, envelope):
        raise _deferred("record_handoff", "O2")

    def update_handoff(self, handoff_id, transition, evidence=None):
        raise _deferred("update_handoff", "O2")

    def register_session(self, assignment_id, registration):
        raise _deferred("register_session", "O4")

    def record_verdict(self, assignment_id, revision_sha, reviewer_role,
                       outcome, evidence=None):
        raise _deferred("record_verdict", "O5")

    def reconcile(self, observations):
        raise _deferred("reconcile", "A1")

    # --- recovery and records ----------------------------------------------

    def pause(self, reason):
        lease = self.store.pause(reason)
        return {"paused": True, "reason": reason,
                "generation": lease["generation"]}

    def checkpoint(self, kind, summary):
        return self.store.append_event("checkpoint", kind, None,
                                       {"kind": kind, "summary": summary,
                                        "recorded": self.clock()})

    def export_company(self):
        return self.store.export_company()

    def backup(self):
        stamp = "".join(character for character in self.clock()
                        if character.isalnum())
        destination = self.store.backups_dir / ("backup-%s-%s"
                                                % (stamp, uuid.uuid4().hex[:8]))
        manifest = self.store.backup(destination)
        manifest.setdefault("destination", str(destination))
        return manifest

    # --- helpers ------------------------------------------------------------

    def _company(self):
        identity = self.store.identity or {}
        lease = self.store.get_lease()
        return {
            "repo": identity.get("repo"),
            "slug": identity.get("slug"),
            "company_dir": str(self.store.root),
            "paused": self.store.is_paused(),
            "read_only": self.store.read_only,
            "generation": lease["generation"] if lease else None,
            "holds_lease": bool(lease
                                and self.store.generation == lease["generation"]),
            "connection": "restricted" if self.launch else "ordinary",
        }


class _WaitingElicitor:
    """Hands the store's lock back while the owner is being asked.

    The dialog is the longest thing this process ever waits on. Holding a
    database lock across it would make one open question freeze every read on
    the company, so the lock is released for exactly the duration of the wait
    and retaken before the answer is recorded.
    """

    def __init__(self, elicitor, lock):
        self._elicitor = elicitor
        self._lock = lock

    def request(self, message, schema):
        try:
            self._lock.release()
        except RuntimeError:
            released = False
        else:
            released = True
        try:
            return self._elicitor.request(message, schema)
        finally:
            if released:
                self._lock.acquire()


def _deferred(method, task):
    return CabinetError(
        "NOT_IMPLEMENTED_YET",
        "cabinet_%s is recorded in the contract and lands in task %s; it has "
        "no implementation in this release" % (method, task))


# --- argument validation ----------------------------------------------------

_TYPE_CHECKS = {
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int)
    and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float))
    and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
}


def _validate_arguments(arguments, schema, method):
    """Check tool arguments against a closed schema.

    The schema is the tool's whole input contract, so a field it does not name
    is refused rather than dropped: an extra `approved: true` beside a real
    argument must fail, not be ignored.
    """

    if not isinstance(arguments, dict):
        raise CabinetError("FIELD_INVALID",
                           "cabinet_%s arguments must be an object" % method)
    properties = schema["properties"]
    for field in arguments:
        if field not in properties:
            raise CabinetError("FIELD_UNKNOWN",
                               "cabinet_%s has no argument %r" % (method, field))
    for field in schema["required"]:
        if field not in arguments:
            raise CabinetError("FIELD_MISSING",
                               "cabinet_%s requires %r" % (method, field))
    values = {}
    for field, value in arguments.items():
        rule = properties[field]
        if not _TYPE_CHECKS[rule["type"]](value):
            raise CabinetError("FIELD_INVALID",
                               "cabinet_%s.%s must be a %s"
                               % (method, field, rule["type"]))
        if "enum" in rule and value not in rule["enum"]:
            raise CabinetError("FIELD_INVALID",
                               "cabinet_%s.%s must be one of %s"
                               % (method, field, ", ".join(rule["enum"])))
        values[field] = value
    return values
