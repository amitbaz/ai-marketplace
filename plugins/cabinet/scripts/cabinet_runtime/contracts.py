"""Canonical shapes, hashing and state machines for stored company records.

The digest is the freeze: a record's canonical JSON hash identifies exactly the
bytes that were agreed, independent of key order in the caller's dictionary.
"""

import hashlib
import json
import re

from .errors import CabinetError

SCHEMA_VERSION = 1

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
ACTION_KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
DOCUMENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+\.md$")

RELEASE_POLICIES = ("owner_approval",)


def canonical_json(value):
    """Return the canonical serialization used for every stored digest."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(value):
    """Return the sha256 hex digest of a value's canonical JSON form."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_repo(text):
    """Split `owner/name` into its parts plus the legacy hyphenated slug."""

    if not isinstance(text, str) or not REPO_PATTERN.match(text):
        raise CabinetError("REPO_INVALID",
                           "expected owner/name, got %r" % (text,))
    owner, name = text.split("/", 1)
    return {"repo": text, "owner": owner, "name": name,
            "slug": "%s-%s" % (owner, name)}


# --- field checking ---------------------------------------------------------

def _require_mapping(value, label):
    if not isinstance(value, dict):
        raise CabinetError("FIELD_INVALID", "%s must be an object" % label)


def _check_fields(value, required, label):
    _require_mapping(value, label)
    for key in required:
        if key not in value:
            raise CabinetError("FIELD_MISSING", "%s.%s is required" % (label, key))
    for key in value:
        if key not in required:
            raise CabinetError("FIELD_UNKNOWN", "%s.%s is not a known field"
                               % (label, key))


def _text(value, label, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise CabinetError("FIELD_INVALID", "%s must be non-empty text" % label)
    return value


def _text_list(value, label):
    if not isinstance(value, list):
        raise CabinetError("FIELD_INVALID", "%s must be a list" % label)
    for index, item in enumerate(value):
        _text(item, "%s[%d]" % (label, index))
    return list(value)


def _int_list(value, label):
    if not isinstance(value, list):
        raise CabinetError("FIELD_INVALID", "%s must be a list" % label)
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int):
            raise CabinetError("FIELD_INVALID",
                               "%s[%d] must be a whole number" % (label, index))
    return list(value)


def check_relative_path(value, label):
    """Refuse absolute paths, parent traversal and empty path segments.

    This is the textual half of the scope-path rule. Resolving a scope path
    against a repository checkout and refusing a symlink that leaves it needs a
    checkout to resolve against, which F2 does not have; O4 owns that check at
    the point where it creates the workspace.
    """

    _text(value, label)
    if value.startswith("/") or value.startswith("~"):
        raise CabinetError("UNSAFE_PATH", "%s must be repository-relative" % label)
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    if not parts or any(part == ".." for part in parts):
        raise CabinetError("UNSAFE_PATH", "%s escapes the repository" % label)
    return value


BATCH_FIELDS = (
    "batch_id", "revision", "repo", "goal", "outcome", "in_scope",
    "out_of_scope", "acceptance", "issues", "base_sha", "owned_paths",
    "check_profile_ids", "risks", "capacity", "release_policy",
    "external_publication",
)

ACTION_FIELDS = (
    "action_id", "idempotency_key", "kind", "batch_id", "revision",
    "expected_before", "payload",
)


def validate_batch_body(body):
    """Return a validated copy of a batch body, or raise CabinetError."""

    _check_fields(body, BATCH_FIELDS, "batch")
    _text(body["batch_id"], "batch.batch_id")
    if isinstance(body["revision"], bool) or not isinstance(body["revision"], int) \
            or body["revision"] < 1:
        raise CabinetError("FIELD_INVALID", "batch.revision must be 1 or more")
    parse_repo(body["repo"])
    _text(body["goal"], "batch.goal")
    _text(body["outcome"], "batch.outcome")
    _text_list(body["in_scope"], "batch.in_scope")
    _text_list(body["out_of_scope"], "batch.out_of_scope")
    _text_list(body["check_profile_ids"], "batch.check_profile_ids")
    _text_list(body["risks"], "batch.risks")
    _int_list(body["issues"], "batch.issues")

    if not isinstance(body["acceptance"], list) or not body["acceptance"]:
        raise CabinetError("FIELD_INVALID", "batch.acceptance must be a non-empty list")
    seen = set()
    for index, item in enumerate(body["acceptance"]):
        _check_fields(item, ("id", "behavior"), "batch.acceptance[%d]" % index)
        _text(item["id"], "batch.acceptance[%d].id" % index)
        _text(item["behavior"], "batch.acceptance[%d].behavior" % index)
        if item["id"] in seen:
            raise CabinetError("FIELD_INVALID",
                               "batch.acceptance has a repeated id %r" % item["id"])
        seen.add(item["id"])

    if not isinstance(body["base_sha"], str) or not SHA_PATTERN.match(body["base_sha"]):
        raise CabinetError("FIELD_INVALID",
                           "batch.base_sha must be 40 lowercase hex characters")

    if not isinstance(body["owned_paths"], list) or not body["owned_paths"]:
        raise CabinetError("FIELD_INVALID", "batch.owned_paths must be a non-empty list")
    for index, item in enumerate(body["owned_paths"]):
        check_relative_path(item, "batch.owned_paths[%d]" % index)

    _require_mapping(body["capacity"], "batch.capacity")
    for key, value in body["capacity"].items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CabinetError("FIELD_INVALID",
                               "batch.capacity.%s must be a whole number" % key)

    if body["release_policy"] not in RELEASE_POLICIES:
        raise CabinetError("FIELD_INVALID", "batch.release_policy must be one of %s"
                           % (RELEASE_POLICIES,))
    if not isinstance(body["external_publication"], bool):
        raise CabinetError("FIELD_INVALID",
                           "batch.external_publication must be true or false")
    return json.loads(canonical_json(body))


def validate_action_envelope(envelope):
    """Return a validated copy of an action envelope, or raise CabinetError."""

    _check_fields(envelope, ACTION_FIELDS, "action")
    _text(envelope["action_id"], "action.action_id")
    _text(envelope["idempotency_key"], "action.idempotency_key")
    kind = _text(envelope["kind"], "action.kind")
    if not ACTION_KIND_PATTERN.match(kind):
        raise CabinetError("FIELD_INVALID",
                           "action.kind must look like `area.operation`")
    _text(envelope["batch_id"], "action.batch_id")
    if isinstance(envelope["revision"], bool) \
            or not isinstance(envelope["revision"], int) or envelope["revision"] < 1:
        raise CabinetError("FIELD_INVALID", "action.revision must be 1 or more")
    _require_mapping(envelope["expected_before"], "action.expected_before")
    _require_mapping(envelope["payload"], "action.payload")
    return json.loads(canonical_json(envelope))


def action_identity(envelope):
    """The part of an action envelope that an idempotency key stands for.

    `action_id` is excluded: a retry may mint a new identifier for the same
    intent, and that must resolve to the stored action rather than a conflict.
    """

    return {key: envelope[key] for key in ACTION_FIELDS if key != "action_id"}


# --- action authority -------------------------------------------------------
#
# Three closed sets decide what an action kind may do. Membership is the whole
# decision: a kind outside every set has no executor. Adding an operation here
# is the only way to make it runnable, which is what keeps the set reviewable.

# Board maintenance on the configured repository. Covered by the setup grant.
SETUP_BOARD_OPERATIONS = (
    "github.create_issue", "github.update_issue", "github.set_labels",
    "github.set_assignees", "github.set_parent", "github.remove_parent",
    "github.add_blocker", "github.remove_blocker", "github.set_state",
)

# Board operations that write prose a reader sees as the company speaking.
# On a public repository these stop being automatic.
PUBLIC_PROSE_OPERATIONS = ("github.create_issue", "github.update_issue")

# Local execution of an approved batch. Covered by that batch's grant.
BATCH_EXECUTION_OPERATIONS = (
    "workspace.create", "workspace.reserve", "worker.launch",
    "git.capture", "git.commit_candidate", "git.integrate_candidate",
    "check.collect",
)

# Execution operations that make something run rather than prepare a place for
# it. These need the repository's setup grant as well as the batch grant,
# because what runs is named in the setup grant and nowhere else.
CHECK_PROFILE_OPERATIONS = ("check.collect",)
LAUNCH_OPERATIONS = ("worker.launch",)

# Execution operations bounded by the setup grant's worker ceiling.
CAPACITY_OPERATIONS = ("worker.launch", "workspace.create", "workspace.reserve")

# Named operations that have no executor at any approval level.
FORBIDDEN_OPERATIONS = (
    "finance.purchase", "finance.pay", "finance.refund",
    "pricing.set", "pricing.publish",
    "billing.subscribe", "billing.upgrade",
    "account.upgrade", "account.subscribe",
    "publish.post", "publish.page", "social.announce",
    "github.add_comment", "github.create_repository", "github.create_branch",
    "github.dispatch_workflow", "github.graphql", "github.create_release",
    "git.push", "git.force_push", "git.merge_deployed",
    "release.create", "release.publish",
    "deploy.start", "deploy.rollback",
    "http.get", "http.post", "http.request",
    "shell.run", "shell.exec",
)

# Whole areas with no executor, whatever the operation is called.
FORBIDDEN_AREAS = (
    "finance", "pricing", "billing", "payment", "purchase", "subscription",
    "publish", "publication", "social", "release", "deploy", "deployment",
    "http", "https", "url", "web", "shell", "exec", "graphql", "sql",
)

# Operation words with no executor, whatever area names them. This catches an
# operation invented after this release under an otherwise allowed area.
FORBIDDEN_OPERATION_WORDS = (
    "purchase", "pay", "refund", "invoice", "subscribe", "upgrade", "buy",
    "publish", "announce", "comment", "post", "push", "merge", "release",
    "deploy", "dispatch", "graphql", "fetch", "run", "exec", "spawn", "eval",
)


def action_authority(kind):
    """Classify an action kind as setup, batch, forbidden or unknown.

    The allowed sets are consulted first, so an explicitly named operation
    keeps its executor even when a forbidden word appears inside its name.
    """

    if not isinstance(kind, str):
        return "unknown"
    if kind in SETUP_BOARD_OPERATIONS:
        return "setup"
    if kind in BATCH_EXECUTION_OPERATIONS:
        return "batch"
    if kind in FORBIDDEN_OPERATIONS:
        return "forbidden"
    area, _, operation = kind.partition(".")
    if area in FORBIDDEN_AREAS:
        return "forbidden"
    for word in FORBIDDEN_OPERATION_WORDS:
        if operation == word or operation.startswith(word + "_"):
            return "forbidden"
    return "unknown"


# --- setup scope ------------------------------------------------------------

SETUP_SCOPE_FIELDS = ("repo", "visibility", "board_operations",
                      "check_profiles", "capacity")
CHECK_PROFILE_FIELDS = ("profile_id", "argv", "env")
VISIBILITIES = ("private", "public")
SETUP_CAPACITY_FIELDS = ("implementation_workers",)


def validate_setup_scope(scope):
    """Return a validated copy of a setup grant's scope, or raise CabinetError."""

    _check_fields(scope, SETUP_SCOPE_FIELDS, "setup")
    parse_repo(scope["repo"])
    if scope["visibility"] not in VISIBILITIES:
        raise CabinetError("FIELD_INVALID", "setup.visibility must be one of %s"
                           % (VISIBILITIES,))

    operations = scope["board_operations"]
    if not isinstance(operations, list) or not operations:
        raise CabinetError("FIELD_INVALID",
                           "setup.board_operations must be a non-empty list")
    seen = set()
    for index, item in enumerate(operations):
        _text(item, "setup.board_operations[%d]" % index)
        if item not in SETUP_BOARD_OPERATIONS:
            raise CabinetError(
                "FIELD_INVALID",
                "setup.board_operations[%d] is %r, which is not a board "
                "operation the owner can delegate" % (index, item))
        if item in seen:
            raise CabinetError("FIELD_INVALID",
                               "setup.board_operations repeats %r" % item)
        seen.add(item)

    profiles = scope["check_profiles"]
    if not isinstance(profiles, list):
        raise CabinetError("FIELD_INVALID", "setup.check_profiles must be a list")
    profile_ids = set()
    for index, item in enumerate(profiles):
        label = "setup.check_profiles[%d]" % index
        _check_fields(item, CHECK_PROFILE_FIELDS, label)
        _text(item["profile_id"], "%s.profile_id" % label)
        if not isinstance(item["argv"], list) or not item["argv"]:
            raise CabinetError("FIELD_INVALID",
                               "%s.argv must be a non-empty list" % label)
        for position, word in enumerate(item["argv"]):
            _text(word, "%s.argv[%d]" % (label, position), allow_empty=True)
        _require_mapping(item["env"], "%s.env" % label)
        for name, value in item["env"].items():
            _text(name, "%s.env key" % label)
            _text(value, "%s.env[%s]" % (label, name), allow_empty=True)
        if item["profile_id"] in profile_ids:
            raise CabinetError("FIELD_INVALID",
                               "setup.check_profiles repeats %r" % item["profile_id"])
        profile_ids.add(item["profile_id"])

    _check_fields(scope["capacity"], SETUP_CAPACITY_FIELDS, "setup.capacity")
    workers = scope["capacity"]["implementation_workers"]
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 0:
        raise CabinetError(
            "FIELD_INVALID",
            "setup.capacity.implementation_workers must be a whole number")
    return json.loads(canonical_json(scope))


# --- owner responses --------------------------------------------------------

def is_owner_acceptance(response):
    """True only for the client response shape that means yes.

    The check is positive and exact. A response carrying `approved`, a string
    `"true"`, the number 1, or an owner-sounding message is not an acceptance,
    because none of them is the boolean the dialog asked for.
    """

    if not isinstance(response, dict):
        return False
    if response.get("action") != "accept":
        return False
    content = response.get("content")
    if not isinstance(content, dict):
        return False
    return content.get("approve") is True


# --- state machines ---------------------------------------------------------

BATCH_TRANSITIONS = {
    "proposed": ("approved", "superseded", "blocked", "paused"),
    "approved": ("running", "paused", "blocked", "superseded"),
    "running": ("verifying", "paused", "blocked", "superseded"),
    "verifying": ("running", "ready_for_release", "paused", "blocked", "superseded"),
    "ready_for_release": ("completed", "paused", "blocked", "superseded"),
    "completed": ("superseded",),
    "paused": ("approved", "running", "verifying", "ready_for_release",
               "blocked", "superseded"),
    "blocked": ("approved", "running", "verifying", "ready_for_release",
                "paused", "superseded"),
    "superseded": (),
}

ACTION_TRANSITIONS = {
    "prepared": ("running", "blocked", "failed"),
    "running": ("verified", "uncertain", "blocked", "failed"),
    "uncertain": ("running", "verified", "blocked", "failed"),
    "verified": (),
    "blocked": ("prepared", "running", "failed"),
    "failed": (),
}

HANDOFF_TRANSITIONS = {
    "recorded": ("sent", "failed", "superseded"),
    "sent": ("acknowledged", "failed", "superseded"),
    "acknowledged": ("resolved", "failed", "superseded"),
    "resolved": (),
    "failed": ("recorded", "superseded"),
    "superseded": (),
}

ASSIGNMENT_TRANSITIONS = {
    "reserved": ("starting", "cancelled", "blocked", "lost"),
    "starting": ("running", "blocked", "lost", "cancel_requested", "cancelled"),
    "running": ("reported", "blocked", "lost", "cancel_requested"),
    "reported": ("verified", "running", "blocked", "lost"),
    "verified": (),
    "blocked": ("running", "cancel_requested", "cancelled", "lost"),
    "cancel_requested": ("cancelled", "lost"),
    "cancelled": (),
    "lost": (),
}

LIVE_ASSIGNMENT_STATES = ("reserved", "starting", "running", "reported",
                          "blocked", "cancel_requested")

# States in which a batch is the one the company is currently working on.
# `completed` and `superseded` are history, and must never be published as the
# current batch.
LIVE_BATCH_STATES = ("proposed", "approved", "running", "verifying",
                     "ready_for_release", "paused", "blocked")


def check_transition(machine, current, target, label):
    """Raise unless `target` follows `current` in the named machine."""

    if current not in machine:
        raise CabinetError("INVALID_TRANSITION",
                           "%s has unknown state %r" % (label, current))
    if target not in machine:
        raise CabinetError("INVALID_TRANSITION",
                           "%s has no state %r" % (label, target))
    if target not in machine[current]:
        raise CabinetError("INVALID_TRANSITION",
                           "%s cannot move from %r to %r" % (label, current, target))
    return target
