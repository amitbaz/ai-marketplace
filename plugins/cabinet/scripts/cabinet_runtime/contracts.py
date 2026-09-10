"""Canonical shapes, hashing and state machines for stored company records.

The digest is the freeze: a record's canonical JSON hash identifies exactly the
bytes that were agreed, independent of key order in the caller's dictionary.
"""

import datetime
import hashlib
import json
import re

from .errors import CabinetError

#: 2 adds the `addresses` projection and the handoff columns O2 needs; 3 adds
#: the consecutive-failure counter, which is a different number from the
#: attempt count and could not share it. An older database is upgraded in place
#: by `store.SCHEMA_UPGRADES`; a newer one still opens read-only with
#: SCHEMA_TOO_NEW.
SCHEMA_VERSION = 4

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


def _check_fields(value, required, label, optional=()):
    """Every required field present, and nothing outside required+optional.

    `optional` exists for a field a record may carry but need not, such as a
    setup scope's account mapping. It is still a closed set: an unknown name is
    refused either way, so an invented field cannot ride along.
    """

    _require_mapping(value, label)
    known = tuple(required) + tuple(optional)
    for key in required:
        if key not in value:
            raise CabinetError("FIELD_MISSING", "%s.%s is required" % (label, key))
    for key in value:
        if key not in known:
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


# --- handoffs ---------------------------------------------------------------

HANDOFF_FIELDS = (
    "handoff_id", "batch_id", "revision", "from_role", "to_role", "kind",
    "question", "evidence", "reply_to", "expected_response",
)

#: What a handoff is for. The distinction that matters is `correction`: it is
#: the only kind whose resolution needs a verdict from someone other than the
#: role that reported the work done.
HANDOFF_KINDS = ("clarification", "correction", "question", "request",
                 "report", "diagnosis")

#: States in which a handoff is still an open obligation somebody owes an
#: answer for. `resolved`, `failed` and `superseded` are finished.
DUE_HANDOFF_STATES = ("recorded", "sent", "acknowledged")

#: Envelopes are small on purpose. Anything larger is referenced by artifact
#: ID, and evidence that arrives inline anyway is cut with a visible marker.
MAX_HANDOFF_BYTES = 8192
TRUNCATION_MARKER = "[cabinet: content omitted"

#: Seconds after a delivery attempt at which the chief probes for an
#: acknowledgment. These are implementation defaults, not promised response
#: times, and they are what `next_retry_at` is computed from. The escalation is
#: driven by the *total* attempt count, so a second redelivery waits longer
#: than a first.
HANDOFF_RETRY_SCHEDULE = (30, 90, 210)

#: How many *consecutive* unsuccessful attempts mark the transport blocked.
#: Consecutive is the load-bearing word: a delivery that worked says the
#: channel works, so the count starts again from there. Counting every report
#: instead let one late failure after a good delivery condemn a handoff that
#: had already arrived.
MAX_CONSECUTIVE_FAILURES = len(HANDOFF_RETRY_SCHEDULE)

#: Recorded as the reason on a handoff whose transport never worked. It is a
#: state of the channel, never a statement about the work behind it.
TRANSPORT_BLOCKED = "TRANSPORT_BLOCKED"

#: Delivery results a sender may report. Only `sent` advances the state; the
#: rest count an attempt and leave the handoff where it was, because a send
#: that did not happen is not a send.
DELIVERY_RESULTS = ("sent", "failed", "blocked", "held", "unknown")

VERDICT_OUTCOMES = ("pass", "fail")

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_time(text, label="time"):
    """Read one stored UTC ISO reading, or raise FIELD_INVALID."""

    if not isinstance(text, str):
        raise CabinetError("FIELD_INVALID", "%s must be a UTC ISO reading" % label)
    try:
        return datetime.datetime.strptime(text, TIME_FORMAT).replace(
            tzinfo=datetime.timezone.utc)
    except ValueError as problem:
        raise CabinetError("FIELD_INVALID",
                           "%s is not %s: %r" % (label, TIME_FORMAT, text)
                           ) from problem


def format_time(moment):
    return moment.strftime(TIME_FORMAT)


def add_seconds(text, seconds, label="time"):
    """Return the stored reading `seconds` after `text`."""

    return format_time(parse_time(text, label)
                       + datetime.timedelta(seconds=seconds))


def not_after(first, second):
    """True when the first stored reading is at or before the second."""

    return parse_time(first) <= parse_time(second)


def validate_handoff_envelope(envelope, known_roles=()):
    """Return a validated copy of a handoff envelope, or raise CabinetError."""

    _check_fields(envelope, HANDOFF_FIELDS, "handoff")
    _text(envelope["handoff_id"], "handoff.handoff_id")
    _text(envelope["batch_id"], "handoff.batch_id")
    if isinstance(envelope["revision"], bool) \
            or not isinstance(envelope["revision"], int) \
            or envelope["revision"] < 1:
        raise CabinetError("FIELD_INVALID", "handoff.revision must be 1 or more")
    for field in ("from_role", "to_role"):
        role = _text(envelope[field], "handoff.%s" % field)
        if known_roles and role not in known_roles:
            raise CabinetError(
                "FIELD_INVALID",
                "handoff.%s is %r, which is not a packaged Cabinet role"
                % (field, role))
    if envelope["kind"] not in HANDOFF_KINDS:
        raise CabinetError("FIELD_INVALID",
                           "handoff.kind must be one of %s" % (HANDOFF_KINDS,))
    _text(envelope["question"], "handoff.question")
    _text(envelope["expected_response"], "handoff.expected_response")
    if envelope["reply_to"] is not None:
        _text(envelope["reply_to"], "handoff.reply_to")

    if not isinstance(envelope["evidence"], list):
        raise CabinetError("FIELD_INVALID", "handoff.evidence must be a list")
    for index, item in enumerate(envelope["evidence"]):
        label = "handoff.evidence[%d]" % index
        _check_fields(item, ("ref", "sha256"), label)
        _text(item["ref"], "%s.ref" % label)
        if not isinstance(item["sha256"], str) \
                or not re.match(r"^[0-9a-f]{64}$", item["sha256"]):
            raise CabinetError(
                "FIELD_INVALID",
                "%s.sha256 must be 64 lowercase hex characters" % label)
    return json.loads(canonical_json(envelope))


def handoff_bytes(envelope):
    return len(canonical_json(envelope).encode("utf-8"))


def bound_handoff(envelope):
    """Return the envelope cut to the size limit, plus whether it was cut.

    The two long free-text fields are the only ones cut. Evidence references
    are kept whole and named in the marker, because the reference *is* the
    retrieval path: dropping it would leave a reader with missing content and
    no way to ask for it.
    """

    if handoff_bytes(envelope) <= MAX_HANDOFF_BYTES:
        return envelope, False
    refs = [item["ref"] for item in envelope["evidence"]]
    retrieval = ("retrieve the full text from %s" % ", ".join(refs)) if refs \
        else ("no artifact reference was supplied; re-record this handoff "
              "with the evidence as an artifact reference")
    bounded = dict(envelope)
    for field in ("question", "expected_response"):
        text = bounded[field]
        marker = "%s from handoff.%s; %s]" % (TRUNCATION_MARKER, field, retrieval)
        room = MAX_HANDOFF_BYTES - (handoff_bytes(bounded) - len(text.encode("utf-8")))
        room -= len(marker.encode("utf-8")) + 1
        if room >= len(text.encode("utf-8")):
            continue
        keep = text.encode("utf-8")[:max(0, room)].decode("utf-8", "ignore")
        bounded[field] = "%s %s" % (keep.rstrip(), marker)
        if handoff_bytes(bounded) <= MAX_HANDOFF_BYTES:
            break
    if handoff_bytes(bounded) > MAX_HANDOFF_BYTES:
        raise CabinetError(
            "FIELD_INVALID",
            "a handoff envelope must fit in %d bytes once its free text is "
            "cut; this one does not, so its evidence list is the part to "
            "shorten" % MAX_HANDOFF_BYTES)
    return bounded, True


def retry_at(now, attempts):
    """When the next acknowledgment probe for this attempt comes due."""

    if attempts < 1:
        return None
    index = min(attempts, len(HANDOFF_RETRY_SCHEDULE)) - 1
    return add_seconds(now, HANDOFF_RETRY_SCHEDULE[index], "clock reading")


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

# Fields a setup scope may carry but need not.
#
# `github_accounts` maps a Cabinet role to a GitHub account the owner has
# confirmed is real. It is optional because the honest default is to have none:
# with no mapping, work ownership stays in Cabinet's assignment record and no
# issue is assigned to anybody. A role name is not an account, and Cabinet
# never invents one to fill the field.
#
# `visibility_source` says where the recorded visibility came from, and
# `visibility_confirmed` records the last value a live read actually returned.
# The three sources lead to different answers, so they are not merged:
#
#   live      — read from the repository just now.
#   unknown   — a live read was attempted and failed.
#   declared  — no adapter could be asked at all.
#
# Only `live` makes prose automatic. A repository whose visibility could not be
# read might be public, and the public-repository rule exists precisely for the
# case where nobody checked.
OPTIONAL_SETUP_FIELDS = ("github_accounts", "visibility_source",
                         "visibility_confirmed")
VISIBILITY_SOURCES = ("live", "declared", "unknown")
CHECK_PROFILE_FIELDS = ("profile_id", "argv", "env")
VISIBILITIES = ("private", "public")
SETUP_CAPACITY_FIELDS = ("implementation_workers",)

# GitHub's own account-name rule: alphanumerics and single inner hyphens, at
# most 39 characters. It rejects obvious nonsense; only a live assignability
# check proves an account exists, and the adapter runs one before every assign.
GITHUB_LOGIN_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


def validate_setup_scope(scope):
    """Return a validated copy of a setup grant's scope, or raise CabinetError."""

    _check_fields(scope, SETUP_SCOPE_FIELDS, "setup", OPTIONAL_SETUP_FIELDS)
    parse_repo(scope["repo"])
    if scope["visibility"] not in VISIBILITIES:
        raise CabinetError("FIELD_INVALID", "setup.visibility must be one of %s"
                           % (VISIBILITIES,))
    source = scope.get("visibility_source", "declared")
    if source not in VISIBILITY_SOURCES:
        raise CabinetError("FIELD_INVALID",
                           "setup.visibility_source must be one of %s"
                           % (VISIBILITY_SOURCES,))
    confirmed = scope.get("visibility_confirmed")
    if confirmed is not None and confirmed not in VISIBILITIES:
        raise CabinetError("FIELD_INVALID",
                           "setup.visibility_confirmed must be one of %s"
                           % (VISIBILITIES,))
    accounts = scope.get("github_accounts", {})
    _require_mapping(accounts, "setup.github_accounts")
    for role, login in accounts.items():
        _text(role, "setup.github_accounts key")
        _text(login, "setup.github_accounts[%s]" % role)
        if not GITHUB_LOGIN_PATTERN.match(login):
            raise CabinetError(
                "FIELD_INVALID",
                "setup.github_accounts[%s] is %r, which is not a GitHub "
                "account name" % (role, login))

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

# The two self-transitions are declared rather than inferred. A delivery
# attempt that did not deliver leaves the handoff where it was and moves only
# the attempt count, so it is a write at the same state; a redelivery of an
# already-sent obligation is the same under the same ID. Everything else must
# name a different state, which is what stops a stale transport report writing
# over an acknowledgment.
HANDOFF_TRANSITIONS = {
    "recorded": ("recorded", "sent", "failed", "superseded"),
    "sent": ("sent", "acknowledged", "failed", "superseded"),
    "acknowledged": ("resolved", "failed", "superseded"),
    "resolved": (),
    "failed": ("recorded", "superseded"),
    "superseded": (),
}

#: States in which a handoff is still waiting to be delivered. A transport
#: report about anything past these is refused: the recipient has already
#: replied, or the obligation is closed, and a sender's stale receipt must not
#: be able to unmake either.
DELIVERABLE_HANDOFF_STATES = ("recorded", "sent")

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
