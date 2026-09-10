"""Restricted launch profiles for the chief, the staff roles and the workers.

A profile is the whole description of one session's authority: the tool names
it may hold, the directories it may reach, the deny rules, hook registration
and sandbox block written into its settings, the environment the check hook
reads, and the argv that starts it. `build_profile` writes one;
`verify_profile` refuses one that would hand a role something it must not have;
`worker_launch` turns a worker profile into argv without running it.

Four properties are worth stating because they are what the refusals protect:

* the argv is derived from the profile's own fields, and `verify_profile`
  re-derives it and compares. A command line that says something the profile
  does not say is refused, because the command line is what actually runs.
* a profile's only hook is Cabinet's own dispatch check. An `Elicitation` or
  `ElicitationResult` hook can answer a dialog before the owner sees it, and
  any other hook is refused rather than inspected.
* every path is absolute and comes from the trusted worktree or toolchain. No
  path is assembled from a ticket, an issue title or any other text a model
  produced, and a path carrying shell syntax is refused rather than quoted.
* a session cannot read what authenticates the owner. The deny set names the
  credential stores, and `~/.cabinet/**/runtime` with them, while leaving the
  company's own public views readable.

Flag names follow the measured environment contract in
docs/cabinet/acceptance/environment.md: `--tools` is the flag that narrows the
tool set, and `crossSessionInbound` has no flag at all, so it is passed as
settings.
"""

import json
import os
import re
import uuid
from types import MappingProxyType

from . import contracts
from .errors import CabinetError

CHIEF_ROLE = "chief-of-staff"

#: Agent types the chief may dispatch, addressed as `cabinet:<type>`.
STAFF_AGENT_TYPES = (
    "chief-of-staff", "product", "delivery-lead", "engineering", "qa",
    "architect", "design", "marketing", "brand", "cfo", "counsel",
)

#: Isolated session types. These are launched as their own processes and are
#: never reachable through the chief's Agent tool.
WORKER_TYPES = ("implementer", "test-runner")

SERVICE_METHODS = (
    "snapshot", "doctor", "context", "acquire_lead", "setup", "propose_batch",
    "request_owner_approval", "record_handoff", "update_handoff",
    "prepare_action", "execute_action", "register_session", "register_staff",
    "record_verdict", "pause", "reconcile", "checkpoint", "export_company",
    "backup", "wait_events",
)
SERVICE_TOOLS = tuple("mcp__cabinet__cabinet_%s" % name
                      for name in SERVICE_METHODS)

#: The read-only slice of the service. An advisory role reads company state and
#: says what it thinks; it changes nothing, so it holds nothing that writes.
STAFF_SERVICE_TOOLS = ("mcp__cabinet__cabinet_snapshot",
                       "mcp__cabinet__cabinet_context",
                       "mcp__cabinet__cabinet_doctor")

CHIEF_TOOLS = ("Read", "Grep", "Glob", "Skill", "Agent", "SendMessage",
               "ListAgents")
STAFF_TOOLS = ("Read", "Grep", "Glob", "Skill", "SendMessage", "ListAgents")
IMPLEMENTER_TOOLS = ("Read", "Edit", "Write", "Grep", "Glob", "SendMessage",
                     "ListAgents")
TEST_RUNNER_TOOLS = ("Read", "Grep", "Glob", "Bash", "SendMessage",
                     "ListAgents")

#: Directories whose contents authenticate somebody.
CREDENTIAL_HOME_DIRS = (".ssh", ".aws", ".docker", ".config/gh",
                        ".config/gcloud")
CREDENTIAL_ABSOLUTE_DIRS = ("/var/run/docker.sock", "/run/docker.sock")

#: Cabinet's own private state. The company's public views sit beside this and
#: stay readable; `runtime/` holds the database, the generated profiles and the
#: backups, and nothing a role runs reads those.
RUNTIME_PATTERNS = (".cabinet/**/runtime",)

CLAUDE_HOME = ".claude"

#: Read denies used when the plugin itself is installed under `~/.claude`, so
#: the tree cannot be denied whole. These are the parts that carry credentials,
#: other sessions' transcripts, or settings that could widen this session.
#: Files are listed separately from directories because a deny rule written as
#: `Tool(<file>/**)` matches nothing at all — see `deny_forms`.
CLAUDE_PRIVATE_FILES = (
    ".claude/.credentials.json", ".claude/settings.json",
    ".claude/settings.local.json", ".claude/history.jsonl",
)
CLAUDE_PRIVATE_DIRS = (
    ".claude/projects", ".claude/sessions", ".claude/session-env",
    ".claude/shell-snapshots", ".claude/todos", ".claude/statsig",
    ".claude/ide", ".claude/daemon", ".claude/tasks", ".claude/teams",
    ".claude/backups", ".claude/file-history", ".claude/downloads",
    ".claude/cache",
)

SETTINGS_KEYS = ("crossSessionInbound", "permissions", "sandbox", "hooks")
PERMISSION_KEYS = ("allow", "defaultMode", "deny",
                   "disableBypassPermissionsMode")

#: The wildcard that covers this company's own MCP tools. It sits beside the
#: explicit names rather than replacing them, so the allowlist still works if
#: a client matches only literal tool names.
SERVICE_TOOL_PATTERN = "mcp__cabinet__*"
WIDENING_MODES = ("bypassPermissions", "auto", "dontAsk")
INBOUND_VALUES = ("accept", "refuse")
WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")

#: Flags that would hand a session more than its profile says, whatever else
#: the command line contains.
FORBIDDEN_ARGV_FLAGS = (
    "--dangerously-skip-permissions", "--dangerously-bypass-approvals-and-sandbox",
    "--permission-mode", "--allowedtools", "--allowed-tools",
    "--disallowedtools", "--disallowed-tools", "--setting-sources", "--agents",
)

HOOK_MATCHER = "Agent|SendMessage"
HOOK_TIMEOUT = 10
ENV_NAMES = ("CABINET_PROFILE_KIND", "CABINET_CHIEF_NAME",
             "CABINET_PEER_REGISTRY")

_SAFE_PATH = re.compile(r"^/[^\s;|&<>$`\"'\\!*?\n\r\x00]*$")
_SAFE_PATTERN = re.compile(r"^/[^\s;|&<>$`\"'\\!?\n\r\x00]*$")
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PROGRAM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ARGV_WORD = re.compile(r"^[^;|&<>$`\"'\\\n\r\x00]*$")

ALLOWED_WORKSPACE = {
    "chief": ("assignment", "path", "claude_path", "plugin_root", "mcp_config",
              "settings_path", "session_id", "peer_registry"),
    "staff": ("plugin_root",),
    "worker": ("assignment", "path", "claude_path", "plugin_root",
               "chief_name", "peer_registry"),
}
REQUIRED_WORKSPACE = {
    "chief": ("assignment", "claude_path", "plugin_root", "mcp_config",
              "settings_path", "session_id"),
    "staff": ("plugin_root",),
    "worker": ("assignment", "path", "claude_path", "plugin_root",
               "chief_name"),
}

PROMPT_LIMIT = 128 * 1024


# --- freezing ---------------------------------------------------------------

def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item)
                                 for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def plain(value):
    """Return a mutable deep copy of a frozen profile or any part of one."""

    if isinstance(value, (dict, MappingProxyType)):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def settings_json(profile):
    """Return the canonical JSON text to hand to `--settings`."""

    return contracts.canonical_json(plain(profile)["settings"])


def digest_of(profile):
    """Return the digest a profile's body should carry."""

    body = plain(profile)
    body.pop("digest", None)
    return contracts.digest(body)


# --- paths ------------------------------------------------------------------

def safe_path(value, label):
    """Return an absolute, non-traversing, shell-inert path, or raise."""

    if not isinstance(value, str) or not value:
        raise CabinetError("PROFILE_PATH_UNSAFE", "%s must be a path" % label)
    if not value.startswith("/"):
        raise CabinetError("PROFILE_PATH_UNSAFE",
                           "%s must be absolute: %r" % (label, value))
    if ".." in value.split("/"):
        raise CabinetError("PROFILE_PATH_UNSAFE",
                           "%s must not traverse: %r" % (label, value))
    if not _SAFE_PATH.match(value):
        raise CabinetError("PROFILE_PATH_UNSAFE",
                           "%s carries shell syntax: %r" % (label, value))
    return value.rstrip("/") or "/"


def safe_pattern(value, label):
    """Like `safe_path`, but `*` and `**` are allowed as path segments."""

    if not isinstance(value, str) or not value.startswith("/"):
        raise CabinetError("PROFILE_PATH_UNSAFE",
                           "%s must be an absolute pattern: %r" % (label, value))
    if ".." in value.split("/") or not _SAFE_PATTERN.match(value):
        raise CabinetError("PROFILE_PATH_UNSAFE",
                           "%s is not a safe pattern: %r" % (label, value))
    return value.rstrip("/") or "/"


def _segments(text):
    return [part for part in text.strip("/").split("/") if part]


def _match(pattern, parts):
    if not pattern:
        return True
    if pattern[0] == "**":
        if _match(pattern[1:], parts):
            return True
        return bool(parts) and _match(pattern, parts[1:])
    if not parts:
        return False
    if pattern[0] != "*" and pattern[0] != parts[0]:
        return False
    return _match(pattern[1:], parts[1:])


def covers(pattern, path):
    """True when `path` is `pattern` or sits inside it. `*`/`**` are segments."""

    return _match(_segments(pattern), _segments(path))


def safe_slug(value, label):
    if not isinstance(value, str) or not _SLUG.match(value):
        raise CabinetError("PROFILE_PATH_UNSAFE",
                           "%s must be a plain identifier: %r" % (label, value))
    return value


def safe_session_id(value):
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise CabinetError("FIELD_INVALID",
                           "a session id must be a UUID: %r" % (value,))
    return str(value)


def credential_paths(home=None, plugin_root=None):
    """Return every path pattern a Cabinet session must not read.

    `~/.claude` is denied whole unless the plugin itself is installed inside it,
    which is where an installed Claude Code plugin lives. In that case the parts
    that carry credentials, other sessions' transcripts and settings are denied
    individually, so the plugin stays readable and nothing else does.
    """

    home = safe_path(home or os.path.expanduser("~"), "home")
    paths = [safe_path("%s/%s" % (home, name), "credential path")
             for name in CREDENTIAL_HOME_DIRS]
    paths.extend(CREDENTIAL_ABSOLUTE_DIRS)
    paths.extend(safe_pattern("%s/%s" % (home, name), "runtime pattern")
                 for name in RUNTIME_PATTERNS)
    claude_home = "%s/%s" % (home, CLAUDE_HOME)
    if plugin_root and covers(claude_home, plugin_root):
        paths.extend(safe_path("%s/%s" % (home, name), "private path")
                     for name in CLAUDE_PRIVATE_FILES + CLAUDE_PRIVATE_DIRS)
    else:
        paths.append(safe_path(claude_home, "private path"))
    return tuple(paths)


def deny_forms(tool, path):
    """Both deny rules a path needs, because one form alone leaves a gap.

    `Tool(<path>/**)` matches what is *inside* a directory and matches nothing
    at all under a file, so on its own it leaves a credential file such as
    `~/.claude/.credentials.json` denied by no rule. `Tool(<path>)` matches the
    path itself. A path Cabinet has not created yet could be either, so both
    are emitted and the one that does not apply simply never matches.
    """

    return ("%s(%s)" % (tool, path), "%s(%s/**)" % (tool, path))


def required_deny(plugin_root, public_context, creds):
    """Deny rules every profile carries, whatever else it is allowed to do."""

    rules = []
    for base in (plugin_root, public_context):
        for tool in WRITE_TOOLS:
            rules.extend(deny_forms(tool, base))
    for path in creds:
        for tool in ("Read",) + WRITE_TOOLS:
            rules.extend(deny_forms(tool, path))
    return tuple(rules)


def hook_entries(plugin_root):
    """The one hook a profile registers: Cabinet's own dispatch check."""

    command = 'python3 "%s/scripts/cabinet-hook"' % plugin_root
    return {"PreToolUse": [{"matcher": HOOK_MATCHER,
                            "hooks": [{"type": "command", "command": command,
                                       "timeout": HOOK_TIMEOUT}]}]}


# --- role registry ----------------------------------------------------------

def role_kind(role):
    """Return `chief`, `staff` or `worker`, or raise ROLE_UNKNOWN."""

    if role == CHIEF_ROLE:
        return "chief"
    if role in STAFF_AGENT_TYPES:
        return "staff"
    if role in WORKER_TYPES:
        return "worker"
    raise CabinetError("ROLE_UNKNOWN",
                       "%r is not a packaged Cabinet role" % (role,))


def expected_tools(role):
    kind = role_kind(role)
    if kind == "chief":
        return CHIEF_TOOLS
    if kind == "staff":
        return STAFF_TOOLS
    return IMPLEMENTER_TOOLS if role == "implementer" else TEST_RUNNER_TOOLS


def expected_allow(role):
    """The permission rules a role's own tools need, and no others.

    `defaultMode: manual` prompts per tool call, which would stop the chief's
    loop on every read it makes. The answer is not a wider mode: owner
    authority lives in the approval dialog, and a prompt in front of a tool
    the profile already granted asks the owner to re-approve a decision the
    profile made. So the allowlist names exactly what the profile granted —
    nothing here can reach a tool the `--tools` flag did not hand over.
    """

    kind = role_kind(role)
    if kind != "chief":
        return ()
    return tuple(expected_tools(role)) + (SERVICE_TOOL_PATTERN,) \
        + tuple(expected_service_tools(role))


def expected_service_tools(role):
    kind = role_kind(role)
    if kind == "chief":
        return SERVICE_TOOLS
    return STAFF_SERVICE_TOOLS if kind == "staff" else ()


def tools_flag(body):
    """The value of `--tools` for this profile."""

    names = list(body.get("tools") or ())
    if body.get("tools_flag_includes_service"):
        names.extend(body.get("service_tools") or ())
    return ",".join(names)


# --- workspace and check profiles -------------------------------------------

def _validate_workspace(kind, workspace):
    if not isinstance(workspace, dict):
        raise CabinetError("FIELD_INVALID", "workspace must be an object")
    allowed = ALLOWED_WORKSPACE[kind]
    for key in workspace:
        if key not in allowed:
            raise CabinetError("FIELD_UNKNOWN",
                               "workspace.%s is not a %s launch field"
                               % (key, kind))
    for key in REQUIRED_WORKSPACE[kind]:
        if key not in workspace:
            raise CabinetError("FIELD_MISSING",
                               "workspace.%s is required for a %s profile"
                               % (key, kind))
    checked = {}
    for key in ("path", "claude_path", "plugin_root", "mcp_config",
                "settings_path", "peer_registry"):
        if key in workspace:
            checked[key] = safe_path(workspace[key], "workspace.%s" % key)
    if "assignment" in workspace:
        checked["assignment"] = safe_slug(workspace["assignment"],
                                          "workspace.assignment")
    if "chief_name" in workspace:
        checked["chief_name"] = safe_slug(workspace["chief_name"],
                                          "workspace.chief_name")
    if "session_id" in workspace:
        checked["session_id"] = safe_session_id(workspace["session_id"])
    return checked


def _validate_check_profiles(role, check_profiles):
    items = list(check_profiles or ())
    if items and role != "test-runner":
        raise CabinetError("FIELD_INVALID",
                           "only a test-runner profile carries check profiles")
    checked = []
    for item in items:
        if not isinstance(item, dict):
            raise CabinetError("FIELD_INVALID", "a check profile must be an object")
        for key in ("profile_id", "argv", "env"):
            if key not in item:
                raise CabinetError("FIELD_MISSING",
                                   "check profile.%s is required" % key)
        safe_slug(item["profile_id"], "check profile id")
        argv = item["argv"]
        if not isinstance(argv, list) or not argv:
            raise CabinetError("FIELD_INVALID", "check profile argv is empty")
        for position, word in enumerate(argv):
            if not isinstance(word, str) or not _ARGV_WORD.match(word):
                raise CabinetError("PROFILE_PATH_UNSAFE",
                                   "check profile argv[%d] carries shell "
                                   "syntax: %r" % (position, word))
        if not _PROGRAM.match(argv[0]):
            safe_path(argv[0], "check profile program")
        env = item["env"]
        if not isinstance(env, dict):
            raise CabinetError("FIELD_INVALID", "check profile env must be an object")
        for name, value in env.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise CabinetError("FIELD_INVALID",
                                   "check profile env must be strings")
        checked.append({"profile_id": item["profile_id"], "argv": list(argv),
                        "env": dict(env)})
    return checked


# --- sandbox ---------------------------------------------------------------

def worker_sandbox(plugin_root, public_context, creds):
    """The mandatory worker sandbox block.

    Key names are the ones this Claude Code build documents in its installed
    changelog: `sandbox.enabled`, `sandbox.failIfUnavailable`,
    `sandbox.allowUnsandboxedCommands`, `sandbox.excludedCommands`,
    `sandbox.filesystem.disabled`, `sandbox.network.strictAllowlist` and
    `sandbox.network.allowedDomains`. An empty allowlist with the strict flag
    set is the documented shape for denying every non-allowlisted host.
    """

    return {
        "enabled": True,
        "failIfUnavailable": True,
        "allowUnsandboxedCommands": False,
        "excludedCommands": [],
        "filesystem": {
            "disabled": False,
            "denyRead": list(creds),
            "denyWrite": [plugin_root, public_context] + list(creds),
        },
        "network": {
            "strictAllowlist": True,
            "allowedDomains": [],
            "allowMachLookup": False,
        },
    }


# --- argv -------------------------------------------------------------------

def build_argv(profile):
    """Derive the launch command line from the profile's own fields.

    This is the single source of truth for what runs. `verify_profile` calls it
    again and compares, so a command line that says something the profile does
    not say is refused.
    """

    body = plain(profile)
    kind = body.get("kind")
    if kind == "staff":
        return ()
    argv = [body["claude_path"], "--restricted", "--strict-mcp-config"]
    if kind == "chief":
        argv += ["--mcp-config", body["mcp_config"],
                 "--settings", body["settings_path"],
                 "--plugin-dir", body["plugin_root"],
                 "--agent", "cabinet:%s" % CHIEF_ROLE]
    else:
        argv += ["--settings", contracts.canonical_json(body["settings"])]
    for directory in body.get("add_dirs") or ():
        argv += ["--add-dir", directory]
    argv += ["--tools", tools_flag(body)]
    if kind == "chief":
        argv += ["--session-id", body["session_id"], "--name",
                 body["session_name"]]
    return tuple(argv)


# --- building ---------------------------------------------------------------

def build_profile(role, workspace, public_context, check_profiles=(),
                  home=None, include_service_tools_in_tools_flag=False):
    """Return the immutable launch profile for one role."""

    kind = role_kind(role)
    space = _validate_workspace(kind, workspace)
    public = safe_path(public_context, "public_context")
    plugin_root = space["plugin_root"]
    creds = credential_paths(home, plugin_root)
    checks = _validate_check_profiles(role, check_profiles)
    tools = expected_tools(role)
    service_tools = expected_service_tools(role)
    deny = required_deny(plugin_root, public, creds)

    permissions = {"defaultMode": "acceptEdits" if kind == "worker" else "manual",
                   "disableBypassPermissionsMode": "disable",
                   "deny": list(deny)}
    allow = expected_allow(role)
    if allow:
        permissions["allow"] = list(allow)
    settings = {"permissions": permissions}
    if kind in ("chief", "worker"):
        settings["crossSessionInbound"] = "accept"
    sandbox = None
    if kind == "worker":
        sandbox = worker_sandbox(plugin_root, public, creds)
        settings["sandbox"] = sandbox
        # A worker has no --plugin-dir, and --restricted ignores the settings
        # files a plugin hook would otherwise be discovered through, so the
        # check is registered here or it does not run at all.
        settings["hooks"] = hook_entries(plugin_root)

    if kind == "chief":
        session_name = "cabinet-chief-%s" % space["assignment"]
        add_dirs = (public, plugin_root)
        chief_name = session_name
    elif kind == "staff":
        # Staff run as the chief's in-process subagents, so they have no argv
        # and no environment of their own; they inherit the chief's.
        session_name = "cabinet-staff-%s" % role
        add_dirs = (public, plugin_root)
        chief_name = None
    else:
        session_name = "cabinet-worker-%s" % space["assignment"]
        add_dirs = (space["path"],)
        chief_name = space["chief_name"]

    env = {}
    if kind != "staff":
        env["CABINET_PROFILE_KIND"] = kind
        env["CABINET_CHIEF_NAME"] = chief_name
        if "peer_registry" in space:
            env["CABINET_PEER_REGISTRY"] = space["peer_registry"]

    body = {
        "role": role,
        "kind": kind,
        "tools": list(tools),
        "service_tools": list(service_tools),
        "tools_flag_includes_service": bool(include_service_tools_in_tools_flag),
        "mcp_servers": ["cabinet"] if kind == "chief" else [],
        "add_dirs": list(add_dirs),
        "deny": list(deny),
        "credential_paths": list(creds),
        "plugin_root": plugin_root,
        "public_context": public,
        "workspace_path": space.get("path"),
        "claude_path": space.get("claude_path"),
        "mcp_config": space.get("mcp_config"),
        "settings_path": space.get("settings_path"),
        "session_id": space.get("session_id"),
        "check_profiles": checks,
        "sandbox": sandbox,
        "settings": settings,
        "env": env,
        "session_name": session_name,
    }
    body["argv"] = list(build_argv(body))
    body["digest"] = contracts.digest(body)
    verify_profile(body)
    return _freeze(body)


# --- verification -----------------------------------------------------------

def verify_profile(profile):
    """Raise CabinetError unless the profile is safe to launch.

    The checks run in the order a reviewer would ask them: what could answer a
    dialog for the owner, what tools does it hold, what can it talk to, what
    can it read, what does its command line actually say, and only then whether
    its settings and sandbox say what they are supposed to say.
    """

    body = plain(profile)
    role = body.get("role")
    kind = role_kind(role)
    if body.get("kind") != kind:
        raise CabinetError("ROLE_UNKNOWN",
                           "%r is a %s role, not %r" % (role, kind,
                                                        body.get("kind")))
    settings = body.get("settings") or {}
    _verify_hooks(kind, body, settings)
    _verify_tools(role, kind, body)
    _verify_mcp(kind, body)
    _verify_directories(body)
    _verify_env(kind, body)
    _verify_argv(kind, body)
    _verify_settings(kind, body, settings)
    _verify_sandbox(kind, body, settings)
    return True


def _verify_hooks(kind, body, settings):
    hooks = settings.get("hooks")
    if hooks is None:
        if kind == "worker":
            raise CabinetError(
                "PROFILE_HOOK_MISSING",
                "a worker loads no plugin, so its settings register the "
                "dispatch check or nothing checks its messages")
        return
    if not isinstance(hooks, dict):
        raise CabinetError("PROFILE_HOOKS_FORBIDDEN",
                           "a profile's hooks must be an object")
    for name in sorted(hooks):
        if name in ("Elicitation", "ElicitationResult"):
            raise CabinetError(
                "PROFILE_HOOKS_FORBIDDEN",
                "a %s hook can answer an owner dialog before the owner sees "
                "it; a profile that must obtain consent carries none" % name)
    expected = hook_entries(body.get("plugin_root"))
    if hooks != expected:
        raise CabinetError(
            "PROFILE_HOOKS_FORBIDDEN",
            "a profile registers Cabinet's PreToolUse check and nothing else; "
            "found %s" % ", ".join(sorted(hooks)))


def _verify_tools(role, kind, body):
    wanted = expected_tools(role)
    held = tuple(body.get("tools") or ())
    if held != wanted:
        extra = [name for name in held if name not in wanted]
        missing = [name for name in wanted if name not in held]
        raise CabinetError(
            "PROFILE_TOOLS_FORBIDDEN",
            "a %s profile holds exactly %s; extra %s, missing %s"
            % (role, ",".join(wanted), extra or "none", missing or "none"))
    service = tuple(body.get("service_tools") or ())
    allowed = expected_service_tools(role)
    if service != allowed:
        raise CabinetError(
            "PROFILE_TOOLS_FORBIDDEN",
            "a %s profile holds %s of the Cabinet service; it named %s"
            % (kind, ", ".join(allowed) or "none",
               ", ".join(service) or "none"))


def _verify_mcp(kind, body):
    servers = tuple(body.get("mcp_servers") or ())
    allowed = ("cabinet",) if kind == "chief" else ()
    if servers != allowed:
        raise CabinetError(
            "PROFILE_MCP_FORBIDDEN",
            "a %s profile may declare %s, not %s"
            % (kind, ", ".join(allowed) or "no MCP server",
               ", ".join(servers) or "none"))


def _verify_directories(body):
    creds = [safe_pattern(path, "credential path")
             for path in body.get("credential_paths") or ()]
    creds.extend(CREDENTIAL_ABSOLUTE_DIRS)
    for directory in body.get("add_dirs") or ():
        safe_path(directory, "add_dirs entry")
        for pattern in creds:
            if covers(pattern, directory):
                raise CabinetError(
                    "PROFILE_CREDENTIALS_EXPOSED",
                    "%s is inside %s, which is private to the owner or to the "
                    "company runtime" % (directory, pattern))


def _verify_env(kind, body):
    env = body.get("env") or {}
    if not isinstance(env, dict):
        raise CabinetError("ENV_INVALID", "a profile environment is an object")
    if kind == "staff":
        if env:
            raise CabinetError("ENV_INVALID",
                               "a staff subagent runs in the chief's process "
                               "and inherits its environment")
        return
    for name, value in env.items():
        if name not in ENV_NAMES:
            raise CabinetError("ENV_INVALID",
                               "%s is not a Cabinet profile variable" % name)
        if not isinstance(value, str) or not value:
            raise CabinetError("ENV_INVALID",
                               "%s must be a non-empty string" % name)
    if env.get("CABINET_PROFILE_KIND") != kind:
        raise CabinetError("ENV_INVALID",
                           "CABINET_PROFILE_KIND must be %r, or the dispatch "
                           "check does nothing" % kind)
    if not env.get("CABINET_CHIEF_NAME"):
        raise CabinetError("ENV_INVALID",
                           "CABINET_CHIEF_NAME names the one session a worker "
                           "may register with")
    if "CABINET_PEER_REGISTRY" in env:
        safe_path(env["CABINET_PEER_REGISTRY"], "CABINET_PEER_REGISTRY")


def _verify_argv(kind, body):
    argv = list(body.get("argv") or ())
    for index, word in enumerate(argv):
        if not isinstance(word, str):
            raise CabinetError("PROFILE_ARGV_MISMATCH",
                               "argv[%d] is not a string" % index)
        lowered = word.lower()
        for flag in FORBIDDEN_ARGV_FLAGS:
            if lowered == flag or lowered.startswith(flag + "="):
                raise CabinetError(
                    "PROFILE_SETTINGS_WIDENING",
                    "%s on the command line would widen this session past its "
                    "profile" % word)
        if word.startswith("/"):
            safe_path(word, "argv path")

    if "--settings" in argv:
        carried = argv[argv.index("--settings") + 1]
        if carried.startswith("{"):
            try:
                decoded = json.loads(carried)
            except ValueError:
                raise CabinetError("PROFILE_ARGV_MISMATCH",
                                   "the settings on the command line are not "
                                   "readable JSON")
            if decoded != body.get("settings"):
                raise CabinetError(
                    "PROFILE_ARGV_MISMATCH",
                    "the settings on the command line are not the settings "
                    "this profile was verified against")
        elif carried != body.get("settings_path"):
            raise CabinetError("PROFILE_ARGV_MISMATCH",
                               "--settings names %r, not the profile's "
                               "settings file" % carried)
    if "--tools" in argv:
        carried = argv[argv.index("--tools") + 1]
        if carried != tools_flag(body):
            raise CabinetError("PROFILE_ARGV_MISMATCH",
                               "--tools names %r, not the profile's tool set"
                               % carried)

    expected = list(build_argv(body))
    if argv != expected:
        difference = [word for word in argv if word not in expected]
        raise CabinetError(
            "PROFILE_ARGV_MISMATCH",
            "the command line does not match the profile it came from; "
            "unexpected %s" % (difference[:4] or "ordering"))
    if kind != "staff":
        for flag in ("--restricted", "--strict-mcp-config"):
            if flag not in argv:
                raise CabinetError("PROFILE_ARGV_MISMATCH",
                                   "%s is missing from the command line" % flag)


def _verify_settings(kind, body, settings):
    for key in settings:
        if key not in SETTINGS_KEYS:
            raise CabinetError("PROFILE_SETTINGS_WIDENING",
                               "%r is not a Cabinet profile setting" % key)
    inbound = settings.get("crossSessionInbound")
    if kind in ("chief", "worker"):
        if inbound != "accept":
            raise CabinetError(
                "PROFILE_SETTINGS_WIDENING",
                "a %s session must state crossSessionInbound=accept; it is the "
                "consent that lets it receive company messages, and %r is not "
                "a value it may hold" % (kind, inbound))
    elif inbound is not None and inbound not in INBOUND_VALUES:
        raise CabinetError("PROFILE_SETTINGS_WIDENING",
                           "crossSessionInbound=%r is not a valid value"
                           % (inbound,))

    permissions = settings.get("permissions")
    if not isinstance(permissions, dict):
        raise CabinetError("PROFILE_SETTINGS_WIDENING",
                           "a profile states its permissions explicitly")
    for key in permissions:
        if key not in PERMISSION_KEYS:
            raise CabinetError("PROFILE_SETTINGS_WIDENING",
                               "permissions.%s widens a profile" % key)
    mode = permissions.get("defaultMode")
    if mode in WIDENING_MODES:
        raise CabinetError("PROFILE_SETTINGS_WIDENING",
                           "defaultMode=%r approves work nobody looked at"
                           % (mode,))
    if mode == "acceptEdits" and kind != "worker":
        raise CabinetError("PROFILE_SETTINGS_WIDENING",
                           "only an isolated worker runs in acceptEdits")
    if mode not in ("manual", "acceptEdits", "plan"):
        raise CabinetError("PROFILE_SETTINGS_WIDENING",
                           "defaultMode=%r is not a mode Cabinet sets" % (mode,))
    wanted_allow = set(expected_allow(body.get("role")))
    declared_allow = set(permissions.get("allow") or ())
    wider = sorted(declared_allow - wanted_allow)
    if wider:
        raise CabinetError(
            "PROFILE_SETTINGS_WIDENING",
            "a permission allowlist may only name tools the profile already "
            "granted; these are not among them: %s" % ", ".join(wider[:3]))
    if wanted_allow and not wanted_allow.issubset(declared_allow):
        missing = sorted(wanted_allow - declared_allow)[:3]
        raise CabinetError(
            "PROFILE_SETTINGS_WIDENING",
            "a chief running in manual mode stops on a prompt for every tool "
            "its allowlist omits: %s" % ", ".join(missing))

    if permissions.get("disableBypassPermissionsMode") != "disable":
        raise CabinetError(
            "PROFILE_SETTINGS_WIDENING",
            "a profile locks bypassPermissions off with "
            "disableBypassPermissionsMode=disable")

    wanted = set(required_deny(body.get("plugin_root"),
                               body.get("public_context"),
                               body.get("credential_paths") or ()))
    declared = set(permissions.get("deny") or ())
    if not wanted.issubset(declared):
        missing = sorted(wanted - declared)[:3]
        raise CabinetError(
            "PROFILE_SETTINGS_WIDENING",
            "a readable directory is not a writable one; these deny rules are "
            "missing: %s" % ", ".join(missing))
    if set(body.get("deny") or ()) != declared:
        raise CabinetError("PROFILE_SETTINGS_WIDENING",
                           "the profile's deny rules and its settings disagree")


def _verify_sandbox(kind, body, settings):
    if kind != "worker":
        return
    block = settings.get("sandbox")
    if not isinstance(block, dict):
        raise CabinetError(
            "PROFILE_SANDBOX_REQUIRED",
            "a worker runs under the mandatory sandbox or it does not run")
    if body.get("sandbox") != block:
        raise CabinetError("PROFILE_SANDBOX_REQUIRED",
                           "the profile's sandbox and its settings disagree")
    required = (("enabled", True), ("failIfUnavailable", True),
                ("allowUnsandboxedCommands", False))
    for key, value in required:
        if block.get(key) is not value:
            raise CabinetError("PROFILE_SANDBOX_REQUIRED",
                               "sandbox.%s must be %s" % (key, value))
    if block.get("excludedCommands"):
        raise CabinetError("PROFILE_SANDBOX_REQUIRED",
                           "sandbox.excludedCommands names commands that would "
                           "run outside the sandbox")
    filesystem = block.get("filesystem")
    if not isinstance(filesystem, dict) or filesystem.get("disabled") is not False:
        raise CabinetError("PROFILE_SANDBOX_REQUIRED",
                           "sandbox.filesystem.disabled must be false")
    network = block.get("network")
    if not isinstance(network, dict):
        raise CabinetError("PROFILE_SANDBOX_REQUIRED",
                           "a worker sandbox states its network policy")
    if network.get("strictAllowlist") is not True:
        raise CabinetError("PROFILE_SANDBOX_REQUIRED",
                           "sandbox.network.strictAllowlist must be true")
    if network.get("allowedDomains"):
        raise CabinetError("PROFILE_SANDBOX_REQUIRED",
                           "a worker has no external egress; "
                           "sandbox.network.allowedDomains must be empty")
    denied = set(filesystem.get("denyRead") or ())
    for path in body.get("credential_paths") or ():
        if path not in denied:
            raise CabinetError("PROFILE_SANDBOX_REQUIRED",
                               "sandbox.filesystem.denyRead must cover %s"
                               % path)


# --- launching --------------------------------------------------------------

def chief_launch(profile, prompt_file=None, background=False):
    """Return the argv for one chief session. Runs nothing.

    The profile's own argv is the whole command line; this adds only the two
    things that describe *this* start rather than the profile: whether it runs
    detached, and the instruction it opens with. A background chief needs an
    opening instruction because nobody is at the keyboard to give it one.
    """

    body = plain(profile)
    if body.get("kind") != "chief":
        raise CabinetError("ROLE_UNKNOWN",
                           "only the chief profile launches a company session; "
                           "%r is a %s profile"
                           % (body.get("role"), body.get("kind")))
    verify_profile(body)
    argv = list(build_argv(body))
    if background:
        argv.append("--bg")
    prompt = None
    if prompt_file is not None:
        prompt = _read_prompt(prompt_file)
        argv.append(prompt)
    return {"argv": argv, "env": body["env"],
            "session_name": body["session_name"], "background": bool(background),
            "prompt_bytes": len(prompt.encode("utf-8")) if prompt else 0}


def worker_launch(profile, prompt_file, session_id):
    """Return the argv, settings and environment for one worker. Runs nothing."""

    body = plain(profile)
    if body.get("kind") != "worker":
        raise CabinetError("ROLE_UNKNOWN",
                           "only a worker profile is launched as its own "
                           "session; %r is a %s profile"
                           % (body.get("role"), body.get("kind")))
    verify_profile(body)
    session_id = safe_session_id(session_id)
    prompt = _read_prompt(prompt_file)
    argv = list(build_argv(body)) + ["--session-id", session_id,
                                     "--name", body["session_name"], prompt]
    return {"argv": argv, "settings": body["settings"], "env": body["env"],
            "session_name": body["session_name"]}


def _read_prompt(prompt_file):
    path = safe_path(prompt_file, "prompt_file")
    if os.path.islink(path):
        raise CabinetError("PROFILE_PATH_UNSAFE",
                           "a prompt file is not followed through a symlink: %r"
                           % (path,))
    if not os.path.isfile(path):
        raise CabinetError("PROFILE_PATH_UNSAFE",
                           "no prompt file at %r" % (path,))
    if os.path.getsize(path) > PROMPT_LIMIT:
        raise CabinetError("FIELD_INVALID",
                           "a worker prompt is at most %d bytes" % PROMPT_LIMIT)
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    if "\x00" in text:
        raise CabinetError("FIELD_INVALID", "a worker prompt is text")
    return text
