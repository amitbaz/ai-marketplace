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

import contextlib
import time
import uuid

from . import contracts, profiles
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
DUE_HANDOFF_STATES = contracts.DUE_HANDOFF_STATES

#: How often a running company re-reads the board, in seconds. An idle or
#: closed company is not a daemon: nothing polls between sessions, and the
#: next opening reconciles whatever changed while it was shut.
BOARD_INTERVAL_SECONDS = 300

#: Kinds a role may register itself under. A worker's address arrives through
#: `register_session` with its assignment; a teammate's through
#: `register_staff`, because a teammate has no assignment of its own.
ADDRESS_KINDS = ("staff", "worker")

#: Roles that may be given a native address at all.
REGISTERABLE_ROLES = (profiles.STAFF_AGENT_TYPES + profiles.WORKER_TYPES)

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
        # The evidence for a transition is a keyed record of what actually
        # happened — the transport and its result, or the session that
        # replied and the generation it replied at — so it is an object
        # rather than the list of artifact references an action carries.
        "write", _schema({"handoff_id": _STRING,
                          "transition": _enum(HANDOFF_TRANSITIONS),
                          "evidence": _OBJECT},
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
    "register_staff": (
        "write", _schema({"role": _STRING, "native_address": _STRING},
                         ("role", "native_address")),
        "Bind a staff role to the native address its messages come from, so "
        "a sender or recipient can be checked against something registered."),
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
                 sleeper=None, monotonic=None, launch_refusal=None,
                 launch_renewer=None, board_reader=None,
                 board_interval_seconds=BOARD_INTERVAL_SECONDS):
        self.store = store
        self.github = github
        self.superset = superset
        self.clock = clock or store.now
        self.elicitor = elicitor
        self.profile_builder = profile_builder
        self.launch = validate_launch(launch, store)
        #: Why a launch context that was offered was refused, if one was. The
        #: connection is read-only either way; this is what `doctor` reports
        #: so a broken launch is diagnosable instead of merely silent.
        self.launch_refusal = dict(launch_refusal) if launch_refusal else None
        #: Called with the generation this session acquires, so the launch
        #: record it was started from stays bound to the current lead.
        self._renew = launch_renewer
        self._sleep = sleeper or time.sleep
        self._monotonic = monotonic or time.monotonic
        #: Reads changed issues since a timestamp. O3 injects the real board
        #: adapter; with none configured the company simply does not poll.
        self.board_reader = board_reader
        self.board_interval_seconds = float(board_interval_seconds)
        self._board_last_read = None
        self._board_cursor = None

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
        run on worker threads while the protocol thread keeps reading.

        Anything that *waits* gives the lock back for the duration of the
        wait: an owner dialog, and `wait_events` between polls. Both would
        otherwise stop every other tool for as long as they sit there, and
        neither is holding the database open while it waits. F3 already treats
        state that moved during a dialog as a reason to refuse the grant
        rather than a race to prevent.
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
        if self.launch:
            note("launch", "restricted", "role %s" % self.launch["role"])
        elif self.launch_refusal:
            note("launch", "refused",
                 "%s: %s" % (self.launch_refusal.get("code"),
                             self.launch_refusal.get("message")))
        else:
            note("launch", "ordinary",
                 "reads only; mutation needs a verified launch")
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
        """Return what has actually changed, waiting briefly for the first thing.

        Three sources, and the difference between them is the point:

        * **Durable events** are facts this company recorded.
        * **Due handoffs** are obligations whose acknowledgment probe has come
          round. Reading them advances nothing.
        * **The board** is an outside observation, taken at most once every
          `board_interval_seconds` and recorded as its own event when it
          differs.

        What it does *not* return is any claim that a native session finished
        something. Liveness comes from the injected adapter and means a
        process is running, never that the work it was given is complete.
        """

        after_seq = max(0, int(after_seq or 0))
        timeout = min(max(float(timeout_seconds or 0), 0.0), MAX_WAIT_SECONDS)
        deadline = self._monotonic() + timeout
        board = self._poll_board()
        while True:
            events = self.store.get_events(after_seq=after_seq)
            due = self.store.pending_handoffs(self.clock())
            remaining = deadline - self._monotonic()
            if events or due or remaining <= 0:
                break
            # The lock is this connection's, not the database's. Holding it
            # across the sleep would make one parked wait serialize every
            # other tool call for up to thirty seconds.
            with released(self.store.lock):
                self._sleep(min(WAIT_POLL_SECONDS, remaining))
            board = self._poll_board() or board
        return {"after_seq": after_seq, "events": events, "handoffs_due": due,
                "board": board, "liveness": self._liveness(),
                "timeout_seconds": timeout, "observed": self.clock(),
                "max_event_seq": self.store.max_event_seq()}

    def _poll_board(self):
        """Read the board at most once per interval; record a real change.

        Nothing is recorded when nothing changed, because a poll is not an
        event and a company that narrates its own polling has recreated the
        volume problem the one-channel rule exists to prevent.
        """

        if self.board_reader is None:
            return None
        now = self._monotonic()
        if self._board_last_read is not None \
                and now - self._board_last_read < self.board_interval_seconds:
            return None
        self._board_last_read = now
        issues = list(self.board_reader.read_changed_issues(self._board_cursor))
        checked = self.clock()
        if not issues:
            return {"checked": checked, "changed": 0, "since": self._board_cursor}
        numbers = [item["number"] for item in issues]
        stamps = [item.get("updated_at") for item in issues
                  if item.get("updated_at")]
        event = self.store.append_event(
            "board.changed", self.store.identity["repo"] if self.store.identity
            else "board", None,
            {"issues": numbers, "since": self._board_cursor,
             "checked": checked, "changed": len(numbers)})
        if stamps:
            self._board_cursor = max(stamps)
        return {"checked": checked, "changed": len(numbers),
                "issues": numbers, "since": event["payload"]["since"],
                "event_id": event["event_id"]}

    def _liveness(self):
        """What the workspace adapter can see, and nothing more.

        A running process is not a finished task. This deliberately reports no
        completion field of any kind, so there is nothing here for a caller to
        misread as one.
        """

        observe = getattr(self.superset, "observe_liveness", None)
        if not callable(observe):
            return {"source": "none", "observations": []}
        return {"source": "adapter", "observations": list(observe())}

    # --- lease, approval and batches ---------------------------------------

    def acquire_lead(self, session_id=None):
        session = session_id or (self.launch or {}).get("session_id") \
            or uuid.uuid4().hex
        pid, marker = own_process_identity()
        lease = self.store.acquire_lease(session, pid, marker)
        if self._renew is not None:
            self._renew(lease["generation"])
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

    # --- handoffs -----------------------------------------------------------

    def record_handoff(self, envelope):
        """Make one obligation durable before anybody tries to deliver it.

        A crash between here and the send loses a delivery attempt, never the
        obligation, which is the whole reason the record comes first.
        """

        envelope = contracts.validate_handoff_envelope(envelope,
                                                       REGISTERABLE_ROLES)
        self.store.get_batch(envelope["batch_id"], envelope["revision"])
        bounded, truncated = contracts.bound_handoff(envelope)
        return self.store.record_handoff(bounded, truncated=truncated)

    def update_handoff(self, handoff_id, transition, evidence=None):
        """Move a handoff, on evidence about what actually happened.

        Each transition asks a different question, and each one refuses on a
        different code, so a caller can tell "you are not the recipient" from
        "the work behind this is not verified":

        * `sent` — did the transport succeed, and was the address the one this
          recipient is registered at? A result that is not `sent` counts a
          delivery attempt and leaves the handoff where it was.
        * `acknowledged` — is the replying session the registered recipient,
          at the current generation, naming this batch revision?
        * `resolved` — for a correction, is there a passing QA verdict at the
          revision the correction produced? Engineering reporting a fix is not
          one.
        """

        stored = self.store.get_handoff(handoff_id)
        evidence = self._handoff_evidence(evidence)
        handler = {"sent": self._handoff_sent,
                   "acknowledged": self._handoff_acknowledged,
                   "resolved": self._handoff_resolved,
                   "failed": self._handoff_failed,
                   "superseded": self._handoff_superseded}[transition]
        return handler(stored, evidence)

    @staticmethod
    def _handoff_evidence(evidence):
        if evidence is None:
            return {}
        if not isinstance(evidence, dict):
            raise CabinetError(
                "FIELD_INVALID",
                "handoff evidence is an object describing what happened")
        return dict(evidence)

    def _registered(self, role, code, note):
        address = self.store.get_address(role)
        if address is None:
            raise CabinetError(
                code,
                "%s (%s) has no registered native address, so nothing can be "
                "checked against it" % (role, note))
        return address["native_address"]

    def _handoff_sent(self, stored, evidence):
        for field in ("transport", "recipient", "result"):
            if field not in evidence:
                raise CabinetError("FIELD_MISSING",
                                   "a send result states its %r" % field)
        result = evidence["result"]
        if result not in contracts.DELIVERY_RESULTS:
            raise CabinetError("FIELD_INVALID",
                               "a delivery result is one of %s"
                               % (contracts.DELIVERY_RESULTS,))
        expected = self._registered(stored["to_role"], "UNKNOWN_RECIPIENT",
                                    "the recipient")
        if evidence["recipient"] != expected:
            raise CabinetError(
                "RECIPIENT_MISMATCH",
                "handoff %s is addressed to %s at %r, not to %r"
                % (stored["handoff_id"], stored["to_role"], expected,
                   evidence["recipient"]))
        if "native_sender" in evidence:
            sender = self._registered(stored["from_role"],
                                      "ADDRESS_NOT_REGISTERED", "the sender")
            if evidence["native_sender"] != sender:
                raise CabinetError(
                    "SENDER_MISMATCH",
                    "handoff %s was raised by %s at %r; %r cannot report its "
                    "send result" % (stored["handoff_id"], stored["from_role"],
                                     sender, evidence["native_sender"]))
        attempts = stored["attempts"] + 1
        now = self.clock()
        if result == "sent":
            return self.store.advance_handoff(
                stored["handoff_id"], "sent", evidence, attempts=attempts,
                next_retry_at=contracts.retry_at(now, attempts))
        if attempts >= contracts.MAX_DELIVERY_ATTEMPTS:
            failed = self.store.advance_handoff(
                stored["handoff_id"], "failed", evidence, attempts=attempts,
                next_retry_at=None, reason=contracts.TRANSPORT_BLOCKED)
            failed["delivery_diagnosis"] = self._delivery_diagnosis(stored,
                                                                    attempts)
            return failed
        # The delivery did not happen, so the state does not move. Only the
        # attempt count and the next probe do.
        return self.store.advance_handoff(
            stored["handoff_id"], stored["state"], evidence, attempts=attempts,
            next_retry_at=contracts.retry_at(now, attempts))

    def _delivery_diagnosis(self, stored, attempts):
        """A handoff for Delivery to diagnose a blocked channel. Not sent.

        The service proposes it and stops there. Recording and delivering it
        is the chief's call, because a company that silently creates its own
        obligations is one nobody is accountable for.
        """

        return {
            "handoff_id": "%s-delivery" % stored["handoff_id"],
            "batch_id": stored["batch_id"], "revision": stored["revision"],
            "from_role": "chief-of-staff", "to_role": "delivery-lead",
            "kind": "diagnosis",
            "question": "Handoff %s to %s failed %d delivery attempts; the "
                        "transport is blocked. Diagnose it and say whether "
                        "the recipient is offline or the channel is."
                        % (stored["handoff_id"], stored["to_role"], attempts),
            "evidence": [], "reply_to": stored["handoff_id"],
            "expected_response": "The cause of the blocked transport and the "
                                 "recovery it needs",
        }

    def _handoff_acknowledged(self, stored, evidence):
        recipient = self._registered(stored["to_role"], "UNKNOWN_RECIPIENT",
                                     "the recipient")
        sender = evidence.get("native_sender")
        if sender is None:
            raise CabinetError(
                "FIELD_MISSING",
                "an acknowledgment names the session that replied; the "
                "sender's guess is not one")
        if sender != recipient:
            raise CabinetError(
                "RECIPIENT_MISMATCH",
                "handoff %s is owed by %s at %r; %r cannot acknowledge it"
                % (stored["handoff_id"], stored["to_role"], recipient, sender))
        self._check_revision(stored, evidence)
        self._check_generation(stored, evidence)
        if stored["state"] == "acknowledged":
            # The same reply arriving twice is one obligation, not two.
            return stored
        return self.store.advance_handoff(stored["handoff_id"], "acknowledged",
                                          evidence,
                                          attempts=stored["attempts"],
                                          next_retry_at=None)

    def _check_generation(self, stored, evidence):
        """Refuse a reply from a session working off a superseded assignment.

        The generation compared against is the one the recipient's address was
        registered at, not the one this connection happens to hold. A role
        that was restarted re-registers, and everything it says afterwards
        carries the newer number; a reply still carrying the older one came
        from a session that has not been told the company moved.
        """

        claimed = evidence.get("assignment_generation")
        if claimed is None:
            return
        address = self.store.get_address(stored["to_role"])
        current = address["generation"] if address is not None \
            else (self.store.generation or 0)
        if claimed != current:
            raise CabinetError(
                "GENERATION_STALE",
                "the reply carries generation %r; %s is registered at "
                "generation %d, so the session that replied is working from a "
                "superseded assignment"
                % (claimed, stored["to_role"], current))

    @staticmethod
    def _check_revision(stored, evidence):
        claimed = evidence.get("revision")
        if claimed is not None and claimed != stored["revision"]:
            raise CabinetError(
                "REVISION_MISMATCH",
                "handoff %s belongs to revision %d; the reply names %r"
                % (stored["handoff_id"], stored["revision"], claimed))

    def _handoff_resolved(self, stored, evidence):
        self._check_revision(stored, evidence)
        sender = evidence.get("native_sender")
        if stored["kind"] == "correction":
            self._check_correction(stored, evidence, sender)
        elif sender is not None:
            allowed = {self._address_of(stored["from_role"]),
                       self._address_of(stored["to_role"])} - {None}
            if sender not in allowed:
                raise CabinetError(
                    "SENDER_MISMATCH",
                    "%r is neither party to handoff %s"
                    % (sender, stored["handoff_id"]))
        return self.store.advance_handoff(stored["handoff_id"], "resolved",
                                          evidence,
                                          attempts=stored["attempts"],
                                          next_retry_at=None)

    def _check_correction(self, stored, evidence, sender):
        """A correction is closed by QA accepting its evidence, or not at all.

        Two separate things are checked, because they fail for different
        reasons: who is reporting the resolution, and whether a verdict exists
        at the revision the correction actually produced.
        """

        reviewer = self._address_of("qa")
        if sender is not None and sender != reviewer:
            raise CabinetError(
                "SENDER_MISMATCH",
                "a correction is resolved by QA at %r accepting its evidence, "
                "not by %r reporting a fix" % (reviewer, sender))
        assignment_id = evidence.get("assignment_id")
        revision_sha = evidence.get("revision_sha")
        if not assignment_id or not revision_sha:
            raise CabinetError(
                "VERDICT_REQUIRED",
                "resolving correction %s needs the assignment and the exact "
                "revision its verdict was recorded at"
                % stored["handoff_id"])
        verdict = self.store.get_verdict(assignment_id, revision_sha, "qa")
        if verdict is None or verdict["outcome"] != "pass":
            raise CabinetError(
                "VERDICT_REQUIRED",
                "no passing QA verdict exists for %s at %s, so correction %s "
                "is still open however it was reported"
                % (assignment_id, revision_sha, stored["handoff_id"]))

    def _address_of(self, role):
        address = self.store.get_address(role)
        return address["native_address"] if address else None

    def _handoff_failed(self, stored, evidence):
        return self.store.advance_handoff(
            stored["handoff_id"], "failed", evidence,
            attempts=stored["attempts"], next_retry_at=None,
            reason=evidence.get("reason"))

    def _handoff_superseded(self, stored, evidence):
        return self.store.advance_handoff(
            stored["handoff_id"], "superseded", evidence,
            attempts=stored["attempts"], next_retry_at=None,
            reason=evidence.get("reason"))

    # --- registration and verdicts -----------------------------------------

    def register_staff(self, role, native_address):
        """Bind one teammate role to the address its messages come from."""

        return self._register(role, native_address, "staff")

    def register_session(self, assignment_id, registration):
        """Bind a launched worker's own session identity to its assignment.

        This is the minimal form O2 needs: it makes the worker's address
        checkable and writes it into the registry the dispatch hook reads. The
        assignment state machine is O4's, and nothing here touches it.
        """

        if not isinstance(registration, dict):
            raise CabinetError("FIELD_INVALID", "a registration is an object")
        allowed = ("role", "native_address", "native_session_id", "terminal_id")
        for field in registration:
            if field not in allowed:
                raise CabinetError("FIELD_UNKNOWN",
                                   "a registration has no %r field" % field)
        for field in ("role", "native_address"):
            if field not in registration:
                raise CabinetError("FIELD_MISSING",
                                   "a registration states its %r" % field)
        return self._register(registration["role"],
                              registration["native_address"], "worker",
                              assignment_id=assignment_id,
                              native_session_id=registration.get(
                                  "native_session_id"))

    def _register(self, role, native_address, kind, assignment_id=None,
                  native_session_id=None):
        if role not in REGISTERABLE_ROLES:
            raise CabinetError("ROLE_UNKNOWN",
                               "%r is not a packaged Cabinet role" % (role,))
        if not isinstance(native_address, str) or not native_address.strip():
            raise CabinetError("FIELD_INVALID",
                               "a native address is non-empty text")
        return self.store.register_address(
            role, native_address, kind, assignment_id=assignment_id,
            native_session_id=native_session_id)

    def record_verdict(self, assignment_id, revision_sha, reviewer_role,
                       outcome, evidence=None):
        """Record one reviewer's verdict at one exact revision.

        O5 adds the acceptance-criteria mapping. What lands here is the part
        O2 depends on: a correction cannot be resolved unless a verdict for
        its assignment and revision actually exists.
        """

        if not contracts.SHA_PATTERN.match(revision_sha or ""):
            raise CabinetError(
                "FIELD_INVALID",
                "a verdict names 40 lowercase hex characters of revision")
        if reviewer_role not in REGISTERABLE_ROLES:
            raise CabinetError("ROLE_UNKNOWN",
                               "%r is not a packaged Cabinet role"
                               % (reviewer_role,))
        return self.store.record_verdict(assignment_id, revision_sha,
                                         reviewer_role, outcome, evidence)

    # --- operations later tasks own ----------------------------------------

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


@contextlib.contextmanager
def released(lock):
    """Give a re-entrant lock back for the duration of a wait.

    Used wherever this module blocks on something that is not the database:
    an owner dialog, and the poll in `wait_events`. A caller that does not
    hold the lock is not an error, so a service method called directly in a
    test behaves the same as one called through `call`.
    """

    try:
        lock.release()
    except RuntimeError:
        holding = False
    else:
        holding = True
    try:
        yield
    finally:
        if holding:
            lock.acquire()


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
        with released(self._lock):
            return self._elicitor.request(message, schema)


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
