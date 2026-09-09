"""Named action authority: which grant, if any, covers an action.

`Policy.authorize` is the gate an executor calls immediately before it would
touch anything outside this process. It returns the grant that covers the
action, or raises. There is no path through it that returns a partial yes.

The order of the checks is part of the guarantee. The kind is classified
first, from a closed enumeration, so an operation with no executor is refused
before its envelope is parsed, before any record is read, and therefore before
an adapter could be selected for it. Money, publication and release are in
that first refusal, not behind a later approval check.
"""

from .contracts import (
    PUBLIC_PROSE_OPERATIONS,
    action_authority,
    validate_action_envelope,
)
from .errors import CabinetError

# Payload keys through which an action can name a repository. An action that
# names one other than this company's is refused whatever else authorizes it.
REPO_KEYS = ("repo", "repository", "owner_repo")


class Policy:
    """Decides which grant covers an action, for one company store."""

    def __init__(self, store):
        self.store = store

    def authorize(self, action):
        """Return the grant covering `action`, or raise CabinetError."""

        kind = action.get("kind") if isinstance(action, dict) else None
        authority = action_authority(kind)
        if authority == "forbidden":
            raise CabinetError(
                "OPERATION_FORBIDDEN",
                "%s has no executor in Cabinet at any approval level; the "
                "owner performs it" % kind)
        if authority == "unknown":
            raise CabinetError(
                "UNKNOWN_OPERATION",
                "%r is not a named Cabinet operation" % (kind,))

        envelope = validate_action_envelope(action)
        self._check_repo(envelope)
        self._check_lease()
        if authority == "setup":
            return self._authorize_board(envelope)
        return self._authorize_execution(envelope)

    # --- shared checks ------------------------------------------------------

    def _repo(self):
        identity = self.store.identity
        if identity is None:
            raise CabinetError("REPO_MISMATCH",
                               "this company directory is not bound to a repository")
        return identity["repo"]

    def _check_repo(self, envelope):
        expected = self._repo()
        payload = envelope["payload"]
        for key in REPO_KEYS:
            named = payload.get(key)
            if named is not None and named != expected:
                raise CabinetError(
                    "REPO_MISMATCH",
                    "the action names %r; this company is %s" % (named, expected))

    def _check_lease(self):
        lease = self.store.get_lease()
        held = self.store.generation
        if lease is None or held is None:
            raise CabinetError(
                "LEASE_REQUIRED",
                "acting on the company needs the lead's lease")
        if lease["generation"] != held:
            raise CabinetError(
                "LEASE_FENCED",
                "generation %s is stale; the current lease is generation %d"
                % (held, lease["generation"]))

    def _check_not_paused(self):
        if self.store.is_paused():
            lease = self.store.get_lease() or {}
            raise CabinetError(
                "PAUSED", "the company is paused: %s"
                % (lease.get("paused_reason") or "no reason recorded"))

    # --- board maintenance --------------------------------------------------

    def _authorize_board(self, envelope):
        repo = self._repo()
        grant = self.store.active_setup_grant(repo)
        if grant is None:
            raise CabinetError(
                "SETUP_NOT_APPROVED",
                "no setup grant covers %s; run the setup dialog once" % repo)
        kind = envelope["kind"]
        if kind not in grant["scope"]["board_operations"]:
            raise CabinetError(
                "OPERATION_NOT_AUTHORIZED",
                "the setup grant for %s does not list %s" % (repo, kind))
        if grant["scope"]["visibility"] == "public" \
                and kind in PUBLIC_PROSE_OPERATIONS:
            raise CabinetError(
                "PUBLIC_PROSE_FORBIDDEN",
                "%s writes public prose on %s; prepare it for exact-content "
                "owner approval instead" % (kind, repo))
        self._check_not_paused()
        return grant

    # --- approved execution -------------------------------------------------

    def _authorize_execution(self, envelope):
        batch_id = envelope["batch_id"]
        revision = envelope["revision"]
        stored = self.store.get_batch(batch_id, revision)
        if stored["body"]["repo"] != self._repo():
            raise CabinetError(
                "REPO_MISMATCH",
                "%s revision %d belongs to %s" % (batch_id, revision,
                                                  stored["body"]["repo"]))
        # Two layers agree today: superseding a revision also revokes its
        # grant, so either check alone catches that case. The state check is
        # the deliberate second layer, guarding against a future writer that
        # retires a batch without going through the grants table.
        if stored["state"] == "superseded":
            raise CabinetError(
                "REVISION_SUPERSEDED",
                "%s revision %d was superseded by a newer revision"
                % (batch_id, revision))

        grant = self.store.batch_grant(batch_id, revision, stored["digest"])
        if grant is None:
            raise CabinetError(
                "BATCH_NOT_APPROVED",
                "no owner grant covers %s revision %d" % (batch_id, revision))
        if grant["revoked_seq"] is not None:
            raise CabinetError(
                "REVISION_SUPERSEDED",
                "the grant for %s revision %d was revoked" % (batch_id, revision))
        self._check_not_paused()
        return grant
