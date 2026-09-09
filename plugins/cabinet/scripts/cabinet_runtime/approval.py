"""Owner approval through a client elicitation dialog.

The dialog is the only thing that creates a grant. This module builds the
question from the stored batch body, records what is being asked before it
asks, and hands the client's response to the store unchanged.

Three properties are structural rather than advisory:

- `request` takes an identifier and a revision, never text. There is no
  parameter through which a caller can supply its own approval copy.
- The response is passed through verbatim; `Store.save_grant` decides what
  counts as an acceptance, so bypassing this module changes nothing.
- Every reason a dialog can fail to produce an answer returns an outcome with
  `granted` false. A missing capability, a raised timeout and a closed session
  are the same non-answer.
"""

import uuid

from .contracts import SETUP_BOARD_OPERATIONS, is_owner_acceptance
from .errors import CabinetError

# The exact schema the contract pins for a batch approval dialog.
BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean",
                    "title": "Approve this exact work batch"}
    },
    "required": ["approve"],
}

SETUP_SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean",
                    "title": "Grant Cabinet authority to manage this board"}
    },
    "required": ["approve"],
}

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean",
                    "title": "Record this decision as the owner's"}
    },
    "required": ["approve"],
}

# Repeated at the end of every dialog, because the answer is a yes to one
# named thing and to nothing adjacent to it.
LIMITS = ("Approving covers this work only. It does not authorize a purchase, "
          "a public communication, or a release.")


def _bullets(items, empty="(none recorded)"):
    if not items:
        return "  %s" % empty
    return "\n".join("  - %s" % item for item in items)


class ApprovalService:
    """Ask the owner one question and record the answer."""

    SCHEMA = BATCH_SCHEMA

    def __init__(self, store, elicitor):
        self.store = store
        self.elicitor = elicitor

    # --- batch approval -----------------------------------------------------

    def request(self, batch_id, revision):
        """Ask the owner to approve one frozen batch revision.

        Returns an outcome dictionary: `granted`, `reason`, `grant`,
        `pending_request_id`, `batch_id`, `revision`, `digest`.
        """

        stored = self.store.get_batch(batch_id, revision)
        pending_request_id = self._new_request_id()
        self.store.record_approval_request(
            pending_request_id, "batch", batch_id=stored["batch_id"],
            revision=stored["revision"])
        message = self.batch_message(stored)
        response, reason = self._ask(message, BATCH_SCHEMA)
        outcome = {"pending_request_id": pending_request_id,
                   "batch_id": stored["batch_id"], "revision": stored["revision"],
                   "digest": stored["digest"], "granted": False,
                   "reason": reason, "grant": None}
        if reason is not None:
            self.store.save_grant(pending_request_id, {"action": reason})
            return outcome
        grant = self.store.save_grant(pending_request_id, response)
        if grant is None:
            outcome["reason"] = self._refusal_reason(response)
            return outcome
        outcome.update(granted=True, reason="approved", grant=grant)
        return outcome

    @staticmethod
    def batch_message(stored):
        """The question, built only from the stored batch body."""

        body = stored["body"]
        acceptance = ["%s: %s" % (item["id"], item["behavior"])
                      for item in body["acceptance"]]
        issues = ", ".join("#%d" % number for number in body["issues"])
        return "\n".join([
            "Approve work batch %s revision %d for %s."
            % (stored["batch_id"], stored["revision"], body["repo"]),
            "",
            "Outcome: %s" % body["outcome"],
            "",
            "In scope:",
            _bullets(body["in_scope"]),
            "",
            "Not in scope:",
            _bullets(body["out_of_scope"]),
            "",
            "Acceptance:",
            _bullets(acceptance),
            "",
            "Issues: %s" % (issues or "(none)"),
            "",
            "Risks:",
            _bullets(body["risks"]),
            "",
            "Frozen content digest: %s" % stored["digest"][:12],
            "",
            LIMITS,
        ])

    # --- setup approval -----------------------------------------------------

    def request_setup(self, scope):
        """Ask the owner once for authority over this repository's board."""

        pending_request_id = self._new_request_id()
        request = self.store.record_approval_request(
            pending_request_id, "setup", scope=scope)
        message = self.setup_message(request["scope"])
        response, reason = self._ask(message, SETUP_SCHEMA)
        outcome = {"pending_request_id": pending_request_id,
                   "repo": request["scope"]["repo"], "granted": False,
                   "reason": reason, "grant": None}
        if reason is not None:
            self.store.save_setup_grant(pending_request_id, {"action": reason})
            return outcome
        grant = self.store.save_setup_grant(pending_request_id, response)
        if grant is None:
            outcome["reason"] = self._refusal_reason(response)
            return outcome
        outcome.update(granted=True, reason="approved", grant=grant)
        return outcome

    @staticmethod
    def setup_message(scope):
        """The setup question. Signing in and delegating are not the same act."""

        profiles = ["%s: %s" % (profile["profile_id"], " ".join(profile["argv"]))
                    for profile in scope["check_profiles"]]
        unlisted = [name for name in SETUP_BOARD_OPERATIONS
                    if name not in scope["board_operations"]]
        return "\n".join([
            "Cabinet setup for %s." % scope["repo"],
            "",
            "This is not a sign-in question. Signing in to GitHub proves who "
            "you are.",
            "This question grants Cabinet standing authority to change this "
            "repository's board on your behalf, without asking again for each "
            "change.",
            "",
            "Repository visibility: %s" % scope["visibility"],
            "",
            "Board operations Cabinet may perform without a further question:",
            _bullets(scope["board_operations"]),
            "",
            "Board operations it may not perform:",
            _bullets(unlisted, empty="(none withheld)"),
            "",
            "Checks it may run, at this fixed command and environment:",
            _bullets(profiles),
            "",
            "Implementation workers at once: %d"
            % scope["capacity"]["implementation_workers"],
            "",
            LIMITS,
        ])

    # --- owner decisions ----------------------------------------------------

    def record_owner_decision(self, subject, question, detail=None):
        """Record a company-direction decision. This creates no grant.

        Charter approval and amendments come through here. A role may propose
        the wording; only this dialog records it as the owner's.
        """

        message = "\n".join([
            "Owner decision: %s" % subject,
            "",
            question,
            "",
            detail or "",
            LIMITS,
        ])
        response, reason = self._ask(message, DECISION_SCHEMA)
        if reason is not None:
            response = {"action": reason}
        event = self.store.record_owner_decision(subject, question, response,
                                                 detail=detail)
        return {"subject": subject, "decided": is_owner_acceptance(response),
                "response": response, "event": event}

    # --- dialog transport ---------------------------------------------------

    @staticmethod
    def _new_request_id():
        return "AR%s" % uuid.uuid4().hex[:12]

    def _ask(self, message, schema):
        """Return (response, None), or (None, reason) when there is no answer."""

        request = getattr(self.elicitor, "request", None)
        if not callable(request):
            return None, "unavailable"
        try:
            response = request(message, schema)
        except CabinetError:
            raise
        except Exception:
            # A timeout, a closed session and a refused capability all arrive
            # as an exception from the client. None of them is an answer.
            return None, "unavailable"
        return response, None

    @staticmethod
    def _refusal_reason(response):
        if isinstance(response, dict):
            action = response.get("action")
            if action == "decline":
                return "declined"
            if action == "cancel":
                return "cancelled"
            if action == "accept":
                return "not_approved"
        return "invalid_response"
