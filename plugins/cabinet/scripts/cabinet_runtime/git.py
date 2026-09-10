"""A bounded git adapter: four operations, no remote, no hooks.

Git is the one tool in this runtime that will happily run somebody else's code
for you. `git worktree add` fires `post-checkout`; a `core.fsmonitor` setting
starts a daemon; an `[alias]` turns a subcommand into a shell command. All of
that is repository- or user-configurable, and all of it runs *before* the
Claude sandbox that is supposed to contain the work exists.

So this adapter is shaped by three rules rather than by convenience:

* **Enumerated operations.** There is no `run(subcommand)`. The methods below
  are the whole surface, and there is deliberately no `fetch`, `push`, `pull`,
  `clone` or `remote` — an operation that could reach the network does not
  exist to be called by mistake.
* **Hooks are disabled by argument, not by trust.** Every command carries
  `-c core.hooksPath=<empty trusted directory>`, and the directory is checked
  for emptiness before the command runs. A hooks directory somebody dropped a
  script into refuses the call rather than silently executing it.
* **Configuration cannot re-enable either.** `-c` settings on the command line
  beat the repository's `.git/config` and the user's global config, so the
  bounded values are the effective ones.

Nothing here interprets a diff or decides what a revision means. The caller
supplies the revision it was granted, and this module's job is to be certain
that the revision it got is the revision it asked for.
"""

import os

from . import processes
from .errors import CabinetError

#: Configuration forced on every invocation. `core.hooksPath` is the one that
#: matters; the rest close smaller doors that a repository can otherwise open
#: on checkout.
FORCED_CONFIG = (
    "core.fsmonitor=false",
    "core.symlinks=true",
    "protocol.ext.allow=never",
    "protocol.file.allow=never",
    "advice.detachedHead=false",
)

#: Environment a git child may see. Nothing carries a credential: this adapter
#: never contacts a remote, so an askpass or a token helper has no work to do.
GIT_ENVIRONMENT = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")

GIT_TIMEOUT_SECONDS = 120


def git_run(cwd="/", timeout=GIT_TIMEOUT_SECONDS, environ=None):
    """Build the `run` callable a production `GitAdapter` is constructed with."""

    env = processes.build_env(GIT_ENVIRONMENT, environ=environ,
                             extra={"GIT_TERMINAL_PROMPT": "0",
                                    "GIT_ASKPASS": "/usr/bin/false",
                                    "GIT_CONFIG_NOSYSTEM": "1"})

    def run(argv, cwd=cwd, timeout=timeout):
        return processes.run_argv(argv, cwd, env, timeout)

    return run


class GitAdapter:
    """The four git operations an isolated workspace needs, and nothing else."""

    def __init__(self, run, root, hooks_dir, git_path="git"):
        self.run = run
        self.root = str(root)
        self.hooks_dir = str(hooks_dir)
        self.git_path = git_path

    # --- transport ----------------------------------------------------------

    def _check_hooks_dir(self):
        """An empty trusted directory, or nothing runs.

        The point of pointing `core.hooksPath` somewhere is that the somewhere
        is empty. Checking it here rather than trusting that it was created
        empty means a file dropped into it later stops the next call instead of
        being executed by it.
        """

        if not os.path.isdir(self.hooks_dir):
            raise CabinetError(
                "SETUP_ISOLATION_UNAVAILABLE",
                "the trusted empty hooks directory %r does not exist, so git "
                "would fall back to the repository's own hooks"
                % (self.hooks_dir,))
        entries = sorted(os.listdir(self.hooks_dir))
        if entries:
            raise CabinetError(
                "SETUP_ISOLATION_UNAVAILABLE",
                "the hooks directory %r is not empty (%s); a hook there would "
                "run before any sandbox exists"
                % (self.hooks_dir, ", ".join(entries[:5])))

    def _argv(self, *words):
        argv = [self.git_path]
        for setting in ("core.hooksPath=%s" % self.hooks_dir,) + FORCED_CONFIG:
            argv += ["-c", setting]
        argv += ["--no-optional-locks", "-C", self.root]
        return argv + list(words)

    def _git(self, *words, cwd=None, what="a git command"):
        self._check_hooks_dir()
        result = self.run(self._argv(*words), cwd=cwd or self.root,
                          timeout=GIT_TIMEOUT_SECONDS)
        if result.get("timed_out"):
            raise CabinetError("PROVIDER_UNCERTAIN",
                               "%s timed out; the working tree may have "
                               "changed" % what)
        if result.get("returncode") != 0:
            raise CabinetError(
                "PROVIDER_ERROR",
                "%s failed with status %s: %s"
                % (what, result.get("returncode"),
                   (result.get("stderr") or result.get("stdout") or "").strip()))
        return result

    # --- operations ---------------------------------------------------------

    def rev_parse(self, ref, cwd=None):
        """The commit a ref names, as 40 hex characters, or an error."""

        result = self._git("rev-parse", "--verify", "%s^{commit}" % ref,
                           cwd=cwd, what="reading %s" % ref)
        return (result.get("stdout") or "").strip()

    def update_ref(self, ref, sha):
        """Point a local ref at a commit. Local only; no remote is named."""

        self._git("update-ref", ref, sha, what="pinning %s" % ref)
        return {"ref": ref, "sha": sha}

    def pin_base(self, ref, base_sha):
        """Create the fixed ref for an approved base, and prove it resolves.

        Superset takes a branch or ref, not a SHA. Handing it `main` would
        hand it whatever `main` means at the moment the workspace is built,
        which is not what the owner approved. This pins a ref Cabinet owns and
        then reads it back: the readback is the check, not the write.
        """

        self.update_ref(ref, base_sha)
        actual = self.rev_parse(ref)
        if actual != base_sha:
            raise CabinetError(
                "BASE_SHA_MISMATCH",
                "%s resolves to %s, not the approved base %s"
                % (ref, actual or "nothing", base_sha))
        return {"ref": ref, "sha": actual}

    def status_porcelain(self, cwd=None):
        """The uncommitted changes in a checkout, one per line."""

        result = self._git("status", "--porcelain", cwd=cwd,
                           what="reading the working tree")
        return [line for line in (result.get("stdout") or "").splitlines()
                if line.strip()]

    def worktree_add(self, path, branch, ref):
        """Create a worktree at `path` on a new `branch` starting at `ref`."""

        self._git("worktree", "add", "-b", branch, str(path), ref,
                  what="creating the worktree at %s" % path)
        return {"path": str(path), "branch": branch, "ref": ref}

    def worktree_list(self):
        """Every worktree this repository knows about, as porcelain records."""

        result = self._git("worktree", "list", "--porcelain",
                           what="listing worktrees")
        records, current = [], {}
        for line in (result.get("stdout") or "").splitlines():
            if not line.strip():
                if current:
                    records.append(current)
                current = {}
                continue
            key, _, value = line.partition(" ")
            current[key] = value
        if current:
            records.append(current)
        return records
