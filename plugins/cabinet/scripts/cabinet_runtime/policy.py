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
    CAPACITY_OPERATIONS,
    CHECK_PROFILE_OPERATIONS,
    LAUNCH_OPERATIONS,
    PUBLIC_PROSE_OPERATIONS,
    action_authority,
    validate_action_envelope,
)
from .errors import CabinetError

# Payload keys through which an action can name a repository. An action that
# names one other than this company's is refused whatever else authorizes it.
# This catches only top-level keys, and it is a second line rather than the
# first: an adapter takes the repository from the grant's scope or the bound
# identity, never from the payload it was handed.
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
        self._check_execution_limits(envelope, stored)
        self._check_not_paused()
        return grant

    # --- setup limits on approved execution ---------------------------------

    def _check_execution_limits(self, envelope, stored):
        """Apply the limits the owner set at setup to an approved batch.

        The setup dialog asks the owner which commands Cabinet may run and how
        many workers it may run at once. A limit that is shown, agreed and
        then not enforced is worse than one never asked about, so both are
        checked here rather than left to the adapter that would run them.
        """

        kind = envelope["kind"]
        needs_setup = kind in CHECK_PROFILE_OPERATIONS or kind in LAUNCH_OPERATIONS
        capped = kind in CAPACITY_OPERATIONS
        if not needs_setup and not capped:
            return
        setup = self.store.active_setup_grant(self._repo())
        if setup is None:
            if needs_setup:
                raise CabinetError(
                    "SETUP_NOT_APPROVED",
                    "%s runs something on %s; that needs the setup grant, "
                    "which names what may run" % (kind, self._repo()))
            # Reserving a workspace runs nothing, and the ceiling is a
            # property of the setup grant, so an unconfigured company has no
            # ceiling to exceed.
            return
        if kind in CHECK_PROFILE_OPERATIONS:
            self._check_profile(envelope, stored, setup)
        if capped:
            self._check_capacity(stored, setup)

    @staticmethod
    def _check_profile(envelope, stored, setup):
        named = envelope["payload"].get("check_profile_id")
        approved = [profile["profile_id"]
                    for profile in setup["scope"]["check_profiles"]]
        if named not in stored["body"]["check_profile_ids"]:
            raise CabinetError(
                "CHECK_PROFILE_NOT_APPROVED",
                "%r is not one of the check profiles in %s revision %d"
                % (named, stored["batch_id"], stored["revision"]))
        if named not in approved:
            raise CabinetError(
                "CHECK_PROFILE_NOT_APPROVED",
                "%r is not one of the check profiles the setup grant approved"
                % (named,))

    @staticmethod
    def _check_capacity(stored, setup):
        wanted = stored["body"]["capacity"].get("implementation_workers", 0)
        ceiling = setup["scope"]["capacity"]["implementation_workers"]
        if wanted > ceiling:
            raise CabinetError(
                "CAPACITY_EXCEEDED",
                "%s revision %d asks for %d workers; setup allows %d"
                % (stored["batch_id"], stored["revision"], wanted, ceiling))
