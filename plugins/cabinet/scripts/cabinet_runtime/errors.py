"""Error type and stable error codes for the Cabinet runtime.

`CabinetError.code` is the assertion surface: callers and tests branch on the
code string, never on the message text. Codes are additive; an existing code
keeps its meaning.
"""

ERROR_CODES = {
    # Identity and paths
    "IDENTITY_CONFLICT": "The stored identity names a different repository.",
    "REPO_INVALID": "A repository name is not `owner/name`.",
    "UNSAFE_PATH": "A path is a symlink, escapes its root, or is absolute.",
    # Schema and lifecycle
    "SCHEMA_TOO_NEW": "The database schema version is newer than this runtime.",
    "STORE_CLOSED": "The store connection is closed.",
    "STORE_BUSY": "Another writer holds the database past the busy timeout.",
    # Field validation
    "FIELD_MISSING": "A required field is absent.",
    "FIELD_UNKNOWN": "An unknown field was supplied.",
    "FIELD_INVALID": "A field has the wrong type, shape or value.",
    # Records
    "BATCH_NOT_FOUND": "No batch exists at that identifier and revision.",
    "REVISION_CONFLICT": "A different body already occupies that revision.",
    "REVISION_ORDER": "A batch revision must be the next one after the highest.",
    "GRANT_NOT_FOUND": "No grant exists with that identifier.",
    "ACTION_NOT_FOUND": "No action exists with that identifier.",
    "DOCUMENT_NOT_FOUND": "No document exists with that name and revision.",
    "IDEMPOTENCY_CONFLICT": "An idempotency key was reused with another body.",
    "ASSIGNMENT_CONFLICT": "Another live assignment already owns that work item.",
    "ASSIGNMENT_NOT_FOUND": "No assignment exists with that identifier.",
    "INVALID_TRANSITION": "That state change is not in the recorded machine.",
    # Lease and fencing
    "LEAD_ACTIVE": "Another lead process holds the company lease.",
    "LEASE_REQUIRED": "The operation needs an acquired lease.",
    "LEASE_FENCED": "The caller's fencing generation is no longer current.",
    "PAUSED": "The company is paused; new actions are fenced.",
    # Approval
    "APPROVAL_REQUEST_UNKNOWN": "No pending approval request has that identifier.",
    "APPROVAL_REQUEST_USED": "That pending approval request was already answered.",
    "SCOPE_CHANGED": "The batch changed while the approval dialog was open.",
    "LEASE_CHANGED": "The company lease changed while the dialog was open.",
    # Action authority
    "BATCH_NOT_APPROVED": "No live owner grant covers that batch revision.",
    "REVISION_SUPERSEDED": "That batch revision's grant was revoked by a newer one.",
    "OPERATION_FORBIDDEN": "That operation has no executor at any approval level.",
    "UNKNOWN_OPERATION": "That operation is not a named Cabinet operation.",
    "SETUP_NOT_APPROVED": "No setup grant covers this repository's board.",
    "OPERATION_NOT_AUTHORIZED": "The setup grant does not list that operation.",
    "PUBLIC_PROSE_FORBIDDEN": "Public repository prose is not automatic.",
    "CHECK_PROFILE_NOT_APPROVED": "That check profile is not in both the batch "
                                  "and the setup grant.",
    "CAPACITY_EXCEEDED": "The batch asks for more workers than setup allows.",
    "REPO_MISMATCH": "The action names a repository other than this company's.",
    # Subprocess adapter
    "ARGV_INVALID": "A command is not a list of plain strings.",
    "ENV_INVALID": "A child environment was not built from an allowlist.",
    # Launch profiles
    "ROLE_UNKNOWN": "That role is not a packaged staff or worker type.",
    "PROFILE_PATH_UNSAFE": "A profile path is relative, traversing, or quoted.",
    "PROFILE_TOOLS_FORBIDDEN": "A profile grants a tool that role must not hold.",
    "PROFILE_HOOKS_FORBIDDEN": "A profile carries a hook that could answer for "
                               "the owner.",
    "PROFILE_MCP_FORBIDDEN": "A profile declares an MCP server outside Cabinet.",
    "PROFILE_SANDBOX_REQUIRED": "A worker profile lacks the mandatory sandbox.",
    "PROFILE_SETTINGS_WIDENING": "A profile's settings widen permissions.",
    "PROFILE_CREDENTIALS_EXPOSED": "A profile exposes a credential directory.",
    "PROFILE_ARGV_MISMATCH": "A launch command line contradicts its profile.",
    "PROFILE_HOOK_MISSING": "A profile does not register the dispatch check.",
    # Service surface
    "TOOL_UNKNOWN": "That name is not an exposed Cabinet tool.",
    "RESTRICTED_SESSION_REQUIRED": "That operation needs the verified "
                                   "restricted launch context.",
    "LAUNCH_CONTEXT_INVALID": "A launch context is malformed, carries a "
                              "secret, or names another company.",
    "CAPABILITY_INVALID": "The per-launch capability does not match its "
                          "launch record.",
    "LAUNCH_PROFILE_MISMATCH": "The profile on disk is not the one the launch "
                               "record was written for.",
    "LAUNCH_HOST_MISMATCH": "This process was not started by the launcher that "
                            "wrote the launch record.",
    "LAUNCH_GENERATION_STALE": "Another lead has taken the company since this "
                               "launch record was bound.",
    "ELICITATION_UNSUPPORTED": "The connected client cannot show the owner a "
                               "form dialog.",
    "NOT_IMPLEMENTED_YET": "That operation has no executor in this release.",
    # Backup and restore
    "BACKUP_DESTINATION_EXISTS": "The backup destination already exists.",
    "RESTORE_DESTINATION_EXISTS": "The restore destination already exists.",
    "BACKUP_INVALID": "A backup directory is missing its manifest or files.",
}


class CabinetError(Exception):
    """An error carrying a stable machine-readable code."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message

    def to_dict(self):
        return {"error": {"code": self.code, "message": self.message}}
