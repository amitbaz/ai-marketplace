"""Isolated workspaces and the workers that run in them.

Two providers implement one interface. `SupersetAdapter` is the design's
mechanism: a Superset workspace plus a terminal running the restricted worker.
`LocalWorktreeProvider` is the same interface over a git worktree and a
background Claude session, and it exists because the machine this runs on has
Superset installed and unauthenticated — an automatic path that cannot start
is not an automatic path.

Four properties are shared by both, and they are the reason this is an adapter
rather than two call sites:

* **Names are derived, never minted.** A workspace's name, branch and base ref
  come from the batch, revision and assignment. A retry after an ambiguous
  answer therefore asks for the same resource, which is what makes
  reconciliation by name possible. Fresh identifiers per attempt would turn a
  lost response into a second workspace and hide the error.
* **An ambiguous answer is `uncertain`, not a failure and not a retry.** A
  timeout after the request left this process may have created the thing. The
  caller reads back.
* **The launch flags are ours.** Superset can start an agent itself with
  `--agent`/`--prompt`, but that runs a preset whose permissions nobody here
  verified. Both providers build the restricted command line from a verified
  profile and start it themselves.
* **There is no follow-up channel through the terminal.** Neither provider
  exposes a `send`. A terminal whose Claude process exited is a shell, and
  text typed into it is a command; follow-ups go over native messaging, which
  is addressed to a session rather than to a pseudo-terminal.

Neither provider removes a worktree. Cleanup is the owner's, because a dirty
worktree is somebody's unsaved work until they say otherwise.
"""

import json
import os
import re
import shlex

from . import contracts
from .errors import CabinetError

#: How long after a launch a registration may still arrive.
STARTUP_WINDOW_SECONDS = contracts.STARTUP_WINDOW_SECONDS

WORKSPACE_TIMEOUT_SECONDS = 300
TERMINAL_TIMEOUT_SECONDS = 180
READ_TIMEOUT_SECONDS = 60

#: Environment a provider CLI and a launched worker may see. Nothing here is a
#: credential, and the list is an allowlist rather than a filter, so a token in
#: this process is not handed to a child.
#:
#: `USER` is load-bearing and was found the hard way: without it the Claude
#: binary starts, prints its banner and then reports `Not logged in`, so the
#: worker comes up as a session that can do nothing and says so only in its
#: own transcript. The credential itself is reached through the binary's own
#: trusted path — it is not in this environment and must not become readable
#: by the worker's file tools or its shell, which is what the containment
#: probes check separately.
PROVIDER_ENVIRONMENT = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL",
                        "TERM", "TMPDIR")

_SLUG = re.compile(r"[^a-z0-9]+")
_SHORT_ID = re.compile(r"\b([0-9a-f]{6,40})\b")


# --- stable names -----------------------------------------------------------

def _slug(text):
    return _SLUG.sub("-", str(text).lower()).strip("-")


def workspace_name(batch_id, revision, assignment_id):
    """The one name this assignment's workspace ever has."""

    return "cabinet-%s-r%d-%s" % (_slug(batch_id), int(revision),
                                  _slug(assignment_id))


def branch_name(batch_id, revision, assignment_id):
    return "cabinet/%s/r%d/%s" % (_slug(batch_id), int(revision),
                                  _slug(assignment_id))


def base_ref_name(batch_id, revision):
    """The local fixed ref an approved base SHA is pinned to."""

    return "refs/cabinet/%s/%d" % (_slug(batch_id), int(revision))


def work_key(issue_number, owned_paths):
    """The ownership unit: one work item together with the paths it owns.

    Two assignments with the same key are the same claim, and the store's
    unique index refuses the second while the first is live. The key is
    readable on purpose — it appears in a refusal, and `issue 12 / app/` tells
    an owner what collided in a way a digest does not.
    """

    paths = ",".join(sorted(str(path) for path in owned_paths))
    return "issue:%s|paths:%s" % (issue_number, paths)


def parse_work_key(key):
    """Split a work key back into its issue and its paths."""

    issue, _, paths = str(key).partition("|paths:")
    issue = issue[len("issue:"):] if issue.startswith("issue:") else issue
    return {"issue": issue,
            "paths": [part for part in paths.split(",") if part]}


def quote_command(argv):
    """Join argv into one command string that splits back into the same argv.

    Superset takes a command as text, which is the one place in this runtime
    where a list becomes a string. The round-trip check is not decoration: it
    is the difference between quoting that works and quoting that is believed
    to work, and it fires on exactly the inputs — a quote, a newline, a
    backslash inside a prompt — that would otherwise become syntax.
    """

    for index, word in enumerate(argv):
        if not isinstance(word, str):
            raise CabinetError("ARGV_INVALID",
                               "argv[%d] is %s, not a string"
                               % (index, type(word).__name__))
        if "\x00" in word:
            raise CabinetError("ARGV_INVALID",
                               "argv[%d] contains a null byte" % index)
    command = " ".join(shlex.quote(word) for word in argv)
    if shlex.split(command) != list(argv):
        raise CabinetError(
            "ARGV_INVALID",
            "this command does not survive being written as text; it would "
            "reach the provider as something other than the argv that was "
            "verified")
    return command


def _payload(result, what):
    """Read a provider's `--json` answer, or say why it could not be read."""

    text = (result.get("stdout") or "").strip()
    if not text:
        raise CabinetError("PROVIDER_ERROR",
                           "%s returned no output to read" % what)
    try:
        return json.loads(text)
    except ValueError:
        for line in reversed(text.splitlines()):
            try:
                return json.loads(line)
            except ValueError:
                continue
    raise CabinetError("PROVIDER_ERROR",
                       "%s did not answer in JSON" % what)


def _first(payload, *names):
    if isinstance(payload, dict):
        for name in names:
            if payload.get(name):
                return payload[name]
        for container in ("workspace", "terminal", "data", "result"):
            nested = payload.get(container)
            if isinstance(nested, dict):
                found = _first(nested, *names)
                if found:
                    return found
    return None


class _Provider:
    """Behaviour both providers share: naming, caching and refusals."""

    name = "provider"

    def __init__(self, run, git=None):
        self.run = run
        self.git = git
        #: workspace_id -> {"name", "path"}. A cache, never the record: the
        #: durable copy lives on the assignment, and every method takes what it
        #: needs as an argument so a restarted process is not blind.
        self._known = {}

    def remember(self, workspace_id, name, path):
        self._known[workspace_id] = {"name": name, "path": path}
        return self._known[workspace_id]

    def _path_of(self, workspace_id, cwd=None):
        if cwd:
            return cwd
        known = self._known.get(workspace_id)
        if known and known.get("path"):
            return known["path"]
        raise CabinetError(
            "WORKSPACE_NOT_CREATED",
            "the working directory of workspace %s is not known to this "
            "process; pass the recorded path" % (workspace_id,))

    def pin_base(self, ref, base_sha):
        if self.git is None:
            raise CabinetError(
                "WORKSPACE_PROVIDER_UNAVAILABLE",
                "this provider has no git adapter, so an approved base "
                "revision cannot be pinned to a ref")
        return self.git.pin_base(ref, base_sha)


# --- Superset ---------------------------------------------------------------

class SupersetAdapter(_Provider):
    """One Superset project's workspaces and terminals, through its CLI."""

    name = "superset"

    def __init__(self, run, project_id, host_id=None, superset_path="superset",
                 git=None):
        super().__init__(run, git=git)
        self.project_id = project_id
        self.host_id = host_id
        self.superset_path = superset_path
        self._probe = None

    def _argv(self, *words):
        argv = [self.superset_path] + [str(word) for word in words]
        if self.host_id:
            argv += ["--host", str(self.host_id)]
        return argv

    def _call(self, argv, what, timeout):
        result = self.run(argv, cwd="/", timeout=timeout)
        if result.get("timed_out"):
            return None, result
        if result.get("returncode") != 0:
            raise CabinetError(
                "PROVIDER_ERROR",
                "%s failed with status %s: %s"
                % (what, result.get("returncode"),
                   (result.get("stderr") or "").strip()[:400]))
        return _payload(result, what), result

    # --- probe --------------------------------------------------------------

    def probe(self, refresh=False):
        """What this installation actually is, and whether it can be used.

        Authentication is asked as its own question rather than inferred from
        a later failure, because an unauthenticated CLI fails every call the
        same way and a caller that cannot tell "not logged in" from "the
        workspace is gone" will reconcile the wrong thing.
        """

        if self._probe is not None and not refresh:
            return self._probe
        version = self.run(self._argv("--version"), cwd="/",
                           timeout=READ_TIMEOUT_SECONDS)
        installed = (version.get("returncode") == 0)
        auth = self.run(self._argv("auth", "whoami", "--json"), cwd="/",
                        timeout=READ_TIMEOUT_SECONDS)
        authenticated = (auth.get("returncode") == 0
                         and not auth.get("timed_out"))
        reason = "ready"
        if not installed:
            reason = "the Superset CLI could not be run on this host"
        elif not authenticated:
            reason = ((auth.get("stderr") or auth.get("stdout") or "").strip()
                      or "the Superset CLI is not authenticated")
        self._probe = {
            "provider": self.name,
            "cli": self.superset_path,
            "version": (version.get("stdout") or "").strip() or None,
            "installed": installed,
            "authenticated": authenticated,
            "usable": bool(installed and authenticated),
            "reason": reason,
            "project": self.project_id,
            "host": self.host_id,
        }
        return self._probe

    def audit_setup_isolation(self, **unused):
        """Whether a Superset workspace's setup command is contained.

        A Superset project can carry a setup command that runs when a
        workspace is created — before the Claude sandbox exists. That command
        lives in the project's server-side configuration, so establishing that
        it is inert requires an authenticated read. There is no skip flag to
        assume, and an unread setup command is not a contained one.
        """

        probe = self.probe()
        if not probe["usable"]:
            return {
                "contained": False,
                "reason": "the project's setup commands cannot be read: %s"
                          % probe["reason"],
                "setup_commands": None,
                "hooks_path": None,
                "provider": self.name,
            }
        payload, _ = self._call(
            self._argv("projects", "get", "--project", self.project_id,
                       "--json"),
            "reading the Superset project", READ_TIMEOUT_SECONDS)
        commands = []
        if isinstance(payload, dict):
            for key in ("setupCommand", "setup_command", "setupScript"):
                if payload.get(key):
                    commands.append(str(payload[key]))
        return {
            "contained": not commands,
            "reason": ("no setup command is configured on this project"
                       if not commands else
                       "the project runs %s before any sandbox exists"
                       % "; ".join(commands)),
            "setup_commands": commands,
            "hooks_path": None,
            "provider": self.name,
        }

    # --- workspaces ---------------------------------------------------------

    def create_workspace(self, name, branch, base_ref):
        """Create one workspace by its stable name, at a verified ref."""

        argv = self._argv("workspaces", "create",
                          "--project", self.project_id,
                          "--name", name,
                          "--branch", branch,
                          "--base-branch", base_ref,
                          "--skip-branch-prefix", "--local", "--json")
        payload, result = self._call(argv, "creating workspace %s" % name,
                                     WORKSPACE_TIMEOUT_SECONDS)
        if payload is None:
            return {"provider": self.name, "outcome": "uncertain",
                    "workspace_id": None, "name": name, "branch": branch,
                    "base_ref": base_ref, "path": None,
                    "actual_base_sha": None,
                    "reason": "the create call timed out after it may already "
                              "have been dispatched"}
        return self._workspace_record(payload, name, branch, base_ref)

    def _workspace_record(self, payload, name, branch, base_ref,
                          outcome="created"):
        workspace_id = _first(payload, "workspaceId", "workspace_id", "id")
        path = _first(payload, "path", "worktreePath", "worktree_path", "cwd")
        head = _first(payload, "baseSha", "base_sha", "headSha", "sha")
        if not workspace_id:
            raise CabinetError(
                "PROVIDER_ERROR",
                "the provider did not name the workspace it created for %s"
                % name)
        if path:
            self.remember(workspace_id, name, path)
        return {"provider": self.name, "outcome": outcome,
                "workspace_id": str(workspace_id), "name": name,
                "branch": branch, "base_ref": base_ref,
                "path": str(path) if path else None,
                "actual_base_sha": str(head) if head else None}

    # --- terminals ----------------------------------------------------------

    def create_terminal(self, workspace_id, launch_argv, cwd=None):
        """Start the verified restricted launch inside an existing workspace."""

        command = quote_command(list(launch_argv))
        argv = self._argv("terminals", "create",
                          "--workspace", workspace_id,
                          "--cwd", self._path_of(workspace_id, cwd),
                          "--command", command, "--json")
        payload, _ = self._call(argv, "starting a terminal in %s" % workspace_id,
                                TERMINAL_TIMEOUT_SECONDS)
        if payload is None:
            return {"provider": self.name, "outcome": "uncertain",
                    "terminal_id": None,
                    "reason": "the terminal call timed out after it may "
                              "already have started a process"}
        terminal_id = _first(payload, "terminalId", "terminal_id", "id")
        if not terminal_id:
            raise CabinetError("PROVIDER_ERROR",
                               "the provider did not name the terminal it "
                               "started in %s" % workspace_id)
        return {"provider": self.name, "outcome": "created",
                "terminal_id": str(terminal_id)}

    def list_terminals(self, workspace_id):
        payload, _ = self._call(
            self._argv("terminals", "list", "--workspace", workspace_id,
                       "--json"),
            "listing terminals in %s" % workspace_id, READ_TIMEOUT_SECONDS)
        rows = payload if isinstance(payload, list) else \
            (payload.get("terminals") if isinstance(payload, dict) else [])
        return list(rows or [])

    def read_terminal(self, workspace_id, terminal_id, max_lines=200):
        payload, result = self._call(
            self._argv("terminals", "read", "--workspace", workspace_id,
                       "--terminal", terminal_id, "--max-lines", str(max_lines),
                       "--json"),
            "reading terminal %s" % terminal_id, READ_TIMEOUT_SECONDS)
        output = _first(payload or {}, "output", "text", "lines") or ""
        if isinstance(output, list):
            output = "\n".join(str(line) for line in output)
        return {"terminal_id": terminal_id, "output": output}

    def close_terminal(self, workspace_id, terminal_id):
        self._call(self._argv("terminals", "close", "--workspace", workspace_id,
                              "--terminal", terminal_id, "--json"),
                   "closing terminal %s" % terminal_id, READ_TIMEOUT_SECONDS)
        return {"provider": self.name, "terminal_id": terminal_id,
                "outcome": "closed"}

    # --- reconciliation -----------------------------------------------------

    def reconcile_assignment(self, assignment):
        """What the provider can see about one assignment, by stable name."""

        name = workspace_name(assignment["batch_id"], assignment["revision"],
                              assignment["assignment_id"])
        payload, _ = self._call(
            self._argv("workspaces", "list", "--project", self.project_id,
                       "--json"),
            "listing workspaces", READ_TIMEOUT_SECONDS)
        rows = payload if isinstance(payload, list) else \
            (payload.get("workspaces") if isinstance(payload, dict) else [])
        match = None
        for row in rows or []:
            if isinstance(row, dict) and row.get("name") == name:
                match = row
                break
        if match is None:
            return {"outcome": "not_created", "workspace_id": None,
                    "name": name, "path": None, "actual_base_sha": None,
                    "live": False, "terminal_id": None,
                    "native_session_id": None}
        record = self._workspace_record(
            match, name,
            branch_name(assignment["batch_id"], assignment["revision"],
                        assignment["assignment_id"]),
            base_ref_name(assignment["batch_id"], assignment["revision"]),
            outcome="adopted")
        terminals = self.list_terminals(record["workspace_id"])
        wanted = assignment.get("terminal_id")
        live = None
        for row in terminals:
            identifier = _first(row, "terminalId", "terminal_id", "id")
            if wanted is None or str(identifier) == str(wanted):
                if str(row.get("status", "running")).lower() in (
                        "running", "active", "live"):
                    live = row
                    break
        record.update({
            "live": live is not None,
            "terminal_id": str(_first(live, "terminalId", "terminal_id", "id"))
            if live else None,
            "native_session_id": _first(live, "sessionId", "session_id")
            if live else None,
        })
        return record


# --- local git worktrees ----------------------------------------------------

class LocalWorktreeProvider(_Provider):
    """A git worktree plus a background Claude session, same interface.

    This is the path that actually runs on a machine with no Superset session.
    It is not a simulation of the Superset path: it creates a real isolated
    checkout at the approved revision and starts a real restricted worker in
    it, and the records it produces are the same records, so the Superset path
    can be verified later without any of them changing shape.
    """

    name = "local"

    def __init__(self, run, root, workspaces_root, claude_path="claude",
                 git=None):
        super().__init__(run, git=git)
        self.root = str(root)
        self.workspaces_root = str(workspaces_root)
        self.claude_path = claude_path

    def probe(self, refresh=False):
        usable = self.git is not None and os.path.isdir(self.root)
        return {"provider": self.name, "cli": self.claude_path,
                "version": None, "installed": True,
                "authenticated": True, "usable": bool(usable),
                "reason": "ready" if usable else
                          "no git adapter or no repository at %r" % self.root,
                "root": self.root, "workspaces_root": self.workspaces_root}

    def audit_setup_isolation(self, **unused):
        """The containment argument for this path, stated rather than assumed.

        Nothing is executed between "create the worktree" and "start the
        sandboxed worker": git runs with hooks pointed at a verified-empty
        directory, and no setup command exists to run. A repository that *does*
        carry a Superset setup command is reported uncontained even here,
        because the same command would run on the Superset path and this audit
        is what stops both.
        """

        commands = []
        config = os.path.join(self.root, ".superset", "config.json")
        if os.path.isfile(config):
            try:
                with open(config, "r", encoding="utf-8") as handle:
                    body = json.load(handle)
            except (ValueError, OSError) as problem:
                return {"contained": False, "provider": self.name,
                        "reason": "the project's Superset configuration at %s "
                                  "could not be read (%s), so what it runs on "
                                  "checkout is unknown" % (config, problem),
                        "setup_commands": None,
                        "hooks_path": getattr(self.git, "hooks_dir", None)}
            for key in ("setupCommand", "setup_command", "setupScript"):
                if isinstance(body, dict) and body.get(key):
                    commands.append(str(body[key]))
        hooks_path = getattr(self.git, "hooks_dir", None)
        return {
            "contained": not commands,
            "provider": self.name,
            "reason": ("git runs with core.hooksPath pointed at the verified "
                       "empty directory %s and no setup command runs on this "
                       "path" % hooks_path) if not commands else
                      ("the repository configures %s to run on checkout"
                       % "; ".join(commands)),
            "setup_commands": commands,
            "hooks_path": str(hooks_path) if hooks_path else None,
        }

    # --- workspaces ---------------------------------------------------------

    def create_workspace(self, name, branch, base_ref):
        if self.git is None:
            raise CabinetError("WORKSPACE_PROVIDER_UNAVAILABLE",
                               "the local provider has no git adapter")
        dirty = self.git.status_porcelain()
        if dirty:
            raise CabinetError(
                "WORKTREE_DIRTY",
                "the base checkout has %d uncommitted change(s) (%s); a "
                "worktree taken from it would not be the approved revision"
                % (len(dirty), dirty[0].strip()))
        wanted = self.git.rev_parse(base_ref)
        if not contracts.SHA_PATTERN.match(wanted or ""):
            raise CabinetError(
                "BASE_SHA_MISMATCH",
                "%s does not resolve to a commit in this repository"
                % base_ref)
        path = os.path.join(self.workspaces_root, name)
        os.makedirs(self.workspaces_root, mode=0o700, exist_ok=True)
        self.git.worktree_add(path, branch, base_ref)
        actual = self.git.rev_parse("HEAD", cwd=path)
        if actual != wanted:
            raise CabinetError(
                "BASE_SHA_MISMATCH",
                "the new worktree is at %s, not at %s" % (actual, wanted))
        self.remember(path, name, path)
        return {"provider": self.name, "outcome": "created",
                "workspace_id": path, "name": name, "branch": branch,
                "base_ref": base_ref, "path": path, "actual_base_sha": actual}

    # --- terminals ----------------------------------------------------------

    def create_terminal(self, workspace_id, launch_argv, cwd=None):
        """Start the restricted worker detached, with argv and no shell.

        `--bg` goes before the trailing prompt because the prompt is a
        positional argument; the list is handed to the process adapter as a
        list, so nothing in it is ever parsed as syntax.
        """

        argv = list(launch_argv)
        if not argv:
            raise CabinetError("ARGV_INVALID", "a launch names a program")
        argv = argv[:-1] + ["--bg"] + argv[-1:]
        path = self._path_of(workspace_id, cwd)
        result = self.run(argv, cwd=path, timeout=TERMINAL_TIMEOUT_SECONDS)
        if result.get("timed_out"):
            return {"provider": self.name, "outcome": "uncertain",
                    "terminal_id": None,
                    "reason": "the launch timed out after it may already have "
                              "started a session"}
        if result.get("returncode") != 0:
            raise CabinetError(
                "PROVIDER_ERROR",
                "the worker launch failed with status %s: %s"
                % (result.get("returncode"),
                   (result.get("stderr") or "").strip()[:400]))
        terminal_id = _background_id(result.get("stdout") or "")
        if not terminal_id:
            raise CabinetError(
                "PROVIDER_ERROR",
                "the launch printed no background session id to control it by")
        return {"provider": self.name, "outcome": "created",
                "terminal_id": terminal_id}

    def list_terminals(self, workspace_id, cwd=None):
        path = self._path_of(workspace_id, cwd)
        result = self.run([self.claude_path, "agents", "--json", "--all",
                           "--cwd", path], cwd=path,
                          timeout=READ_TIMEOUT_SECONDS)
        if result.get("returncode") != 0 or result.get("timed_out"):
            raise CabinetError(
                "PROVIDER_ERROR",
                "listing background sessions under %s failed" % path)
        rows = _payload(result, "listing background sessions")
        if isinstance(rows, dict):
            rows = rows.get("agents") or rows.get("sessions") or []
        return [dict(row, terminal_id=_first(row, "id", "shortId", "sessionId"))
                for row in (rows or []) if isinstance(row, dict)]

    def read_terminal(self, workspace_id, terminal_id, max_lines=200,
                      cwd=None):
        result = self.run([self.claude_path, "logs", terminal_id],
                          cwd=self._path_of(workspace_id, cwd),
                          timeout=READ_TIMEOUT_SECONDS)
        return {"terminal_id": terminal_id,
                "output": (result.get("stdout") or "")}

    def close_terminal(self, workspace_id, terminal_id, cwd=None):
        """Stop the session and delete its record. The worktree stays."""

        path = self._path_of(workspace_id, cwd)
        self.run([self.claude_path, "stop", terminal_id], cwd=path,
                 timeout=READ_TIMEOUT_SECONDS)
        self.run([self.claude_path, "rm", terminal_id], cwd=path,
                 timeout=READ_TIMEOUT_SECONDS)
        return {"provider": self.name, "terminal_id": terminal_id,
                "outcome": "closed",
                "worktree": "preserved: %s" % path}

    # --- reconciliation -----------------------------------------------------

    def reconcile_assignment(self, assignment):
        name = workspace_name(assignment["batch_id"], assignment["revision"],
                              assignment["assignment_id"])
        path = os.path.join(self.workspaces_root, name)
        if not os.path.isdir(path):
            return {"outcome": "not_created", "workspace_id": None,
                    "name": name, "path": None, "actual_base_sha": None,
                    "live": False, "terminal_id": None,
                    "native_session_id": None}
        head = self.git.rev_parse("HEAD", cwd=path) if self.git else None
        self.remember(path, name, path)
        wanted = assignment.get("terminal_id")
        live = None
        for row in self.list_terminals(path, cwd=path):
            if wanted is None or str(row.get("terminal_id")) == str(wanted):
                if str(row.get("status", "")).lower() in ("running", "active",
                                                          "busy", "idle"):
                    live = row
                    break
        return {"outcome": "adopted", "workspace_id": path, "name": name,
                "path": path, "actual_base_sha": head,
                "live": live is not None,
                "terminal_id": str(live.get("terminal_id")) if live else None,
                "native_session_id": _first(live or {}, "sessionId",
                                            "session_id")}


def _background_id(text):
    """The short id `claude --bg` prints, which `stop`, `logs` and `rm` take."""

    for line in text.splitlines():
        for candidate in _SHORT_ID.findall(line):
            if not contracts.SHA_PATTERN.match(candidate):
                return candidate
    return None


# --- selection --------------------------------------------------------------

def select_provider(providers, scope):
    """Return the provider a setup grant names, or say why there is none.

    The default is Superset, and an unusable Superset does *not* fall through
    to the local provider. Falling through would mean the mechanism that runs
    the owner's code changed because something failed, which is exactly the
    kind of silent substitution this design refuses. Running locally is a
    setting the owner turned on.
    """

    configured = (scope or {}).get("workspace_provider",
                                   contracts.DEFAULT_WORKSPACE_PROVIDER)
    adapter = (providers or {}).get(configured)
    if adapter is None:
        raise CabinetError(
            "WORKSPACE_PROVIDER_UNAVAILABLE",
            "the setup grant names the %r workspace provider, which this host "
            "has not configured; the configured ones are %s"
            % (configured, ", ".join(sorted(providers or {})) or "none"))
    report = adapter.probe()
    if not report.get("usable"):
        raise CabinetError(
            "WORKSPACE_PROVIDER_UNAVAILABLE",
            "the %r workspace provider cannot create an isolated workspace "
            "here: %s" % (configured, report.get("reason") or "no reason given"))
    return adapter, report
