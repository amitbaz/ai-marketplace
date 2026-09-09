# Cabinet: actionable standup brief and local session detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/cabinet:standup` end in one ranked list of moves that each carry a command to type, and stop it recommending tickets that a local session already has open.

**Architecture:** A new `local-sessions` script enumerates this machine's git worktrees for the repository and attributes each to a ticket from evidence on disk, the same way `board-snapshot` collects the board — the command has a shell, roles do not, so the command collects and passes `sessions=<path>` into the role's prompt. `board-snapshot` gains merged pull request data so the brief can state what changed instead of inferring it. The brief's specification is then rewritten so the six groupings collapse into a position block plus one ranked move list, and a new read-only `/cabinet:now` covers the gap between standups.

**Tech Stack:** bash + `gh` + `jq` (board-snapshot, matching what is there), python3 (local-sessions), markdown command and agent definitions, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-cabinet-standup-brief-and-local-sessions-design.md`

## Global Constraints

- **Roles hold no shell.** Every path a role needs is resolved by the command and passed into the role's prompt as `memory=`, `board=`, `epics=`, `sessions=`. Never make a role derive a path.
- **Cabinet writes nothing to the board.** No label, assignee or comment is used to claim a ticket.
- **No external service.** Detection is git and the filesystem only.
- **Plugin scripts carry mechanism, not workflow prose.** `scripts/check-adapter-boundary.py` scans every file under `plugins/*/scripts/` and `plugins/*/hooks/` and fails on these phrases: `phase 2 —`, `phase 2 -`, `phase 3 —`, `phase 3 -`, `engineering discipline`, `make uncertainty visible`, `smallest complete solution`, `change boundary tight`, `observable outcomes`, `who you are writing for`, `hand off, don't execute`. Keep them out of comments and docstrings in the new script.
- **No file path, function or line number reaches the brief.** That rule is in `commands/standup.md` today and survives the rewrite.
- **Attribution is verified, never guessed.** A ticket number derived from a branch name or commit message is only accepted when it appears as an open issue in the board snapshot.
- **Soft failure is exit 0 with an empty result and a stated reason.** A missing signal must never abort a standup.

### Two deviations from the spec, decided here

1. **`local-sessions` is python3, not bash.** The spec said bash to match `board-snapshot`. The work is worktree parsing, regex attribution, mtime arithmetic and JSON assembly — `board-snapshot` is bash because it is `gh` and `jq` glue, and the repo already ships python3 plugin scripts with `--self-test` (`plugins/groundwork/scripts/harvest-transcripts`, `collect-metrics`). python3 also makes the fixture-based self-test tractable.
2. **`local-sessions` takes no `--since`.** The spec's usage line listed it and nothing in the spec consumes it. Dropped.

---

## File Structure

| File | Responsibility |
|---|---|
| `plugins/cabinet/scripts/local-sessions` | new — enumerate this machine's worktrees for the repo, attribute each to a ticket from evidence, write one JSON snapshot |
| `plugins/cabinet/scripts/board-snapshot` | modified — `--since`, `recently_merged`, `--self-test` |
| `plugins/cabinet/agents/delivery-lead.md` | modified — consume `sessions=` when working out what is taken |
| `plugins/cabinet/commands/standup.md` | modified — dispatch the scan; rewrite the brief contract |
| `plugins/cabinet/commands/now.md` | new — read-only state check between standups |
| `.github/workflows/validate.yml` | modified — two self-test steps |
| `plugins/cabinet/FILES.md`, `plugins/cabinet/README.md`, both `plugin.json` | modified — document the script, the command, the brief shape; version bump |

---

### Task 1: `local-sessions` — enumerate worktrees and report git facts

**Files:**
- Create: `plugins/cabinet/scripts/local-sessions`
- Test: same file, `--self-test`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - CLI: `local-sessions <owner/repo> [--board <path>] [--cwd <path>]`
  - stdout: `sessions=<absolute path>`
  - stderr: `Local: <n> worktrees · <n> in flight (<summary>) · <n> stalled`
  - JSON at `${TMPDIR:-/tmp}/cabinet-sessions-<owner>-<repo>.json`:
    ```json
    {"repo": "o/r", "taken_at": "...Z", "stall_hours": 24,
     "counts": {"worktrees": 2, "in_flight": 1, "attributed": 1, "stalled": 0},
     "worktrees": [
       {"path": "/abs/path", "branch": "feat/x", "is_current": false,
        "kind": "workspace", "in_flight": true,
        "ticket": 179, "ticket_source": "attachment", "rejected_ticket": null,
        "commits_ahead": 1, "unpushed": 1, "dirty": 5,
        "last_activity": "2026-09-09T12:00:00Z", "idle_hours": 3.0,
        "stalled": false}]}
    ```
  - Python functions later tasks extend: `parse_worktrees(text)`, `collect(repo, cwd, board_numbers, stall_hours, now)`, `self_test()`
- `--cwd` exists so the self-test can point the collector at a fixture repository. The commands never pass it.

- [ ] **Step 1: Write the failing self-test**

Create `plugins/cabinet/scripts/local-sessions` containing only the self-test and its fixture builder, plus a `main` that dispatches `--self-test`:

```python
#!/usr/bin/env python3
"""Find the work already open on this machine, and write it where a role can read it.

A Cabinet role holds no shell, by design: its tool grant is what makes the money
invariant structural rather than a promise. So a role cannot look at the disk,
and work started in another worktree is invisible to it. GitHub cannot see that
work either: a workspace opened from a ticket is a local branch with nothing
pushed, so the board shows the ticket as free while somebody is a commit deep in
it.

This script is how the dispatching command closes that gap. It enumerates every
worktree of the repository on this machine, attributes each to a ticket from
evidence on disk, and writes one snapshot file that is handed to the roles the
same way the board snapshot is. Nothing is registered when a workspace opens:
the worktree existing is the claim.

Usage:   local-sessions <owner/repo> [--board <path>] [--cwd <path>]
         local-sessions --self-test
Prints:  sessions=/…/cabinet-sessions-owner-repo.json   on stdout
         a one-line count summary                       on stderr

Read-only. Exits 0 with an empty result when there is no signal to collect, so
that a missing local picture never aborts the run that asked for it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_STALL_HOURS = 24.0


# ----------------------------------------------------------------- self-test


def run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def build_fixture(base: Path) -> Path:
    """A repository with a main checkout and two worktrees."""
    origin = base / "origin.git"
    run(["git", "init", "--bare", "-b", "main", str(origin)], base)

    main = base / "main"
    run(["git", "clone", str(origin), str(main)], base)
    run(["git", "config", "user.email", "t@example.com"], main)
    run(["git", "config", "user.name", "T"], main)
    # A clone of an empty bare repository leaves HEAD on whatever
    # init.defaultBranch happens to be locally. Pin it.
    run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], main)
    (main / "README.md").write_text("x\n", encoding="utf-8")
    run(["git", "add", "-A"], main)
    run(["git", "commit", "-m", "init"], main)
    # Push while origin is still the path, so refs/remotes/origin/main exists,
    # and only then make the remote look like the real thing.
    run(["git", "push", "-u", "origin", "main"], main)
    run(["git", "remote", "set-url", "origin", "git@github.com:acme/widget.git"], main)

    # A worktree with committed and uncommitted work.
    busy = base / "busy"
    run(["git", "worktree", "add", "-b", "feat/shared-writers", str(busy)], main)
    (busy / "a.txt").write_text("one\n", encoding="utf-8")
    run(["git", "add", "-A"], busy)
    run(["git", "commit", "-m", "work"], busy)
    (busy / "a.txt").write_text("two\n", encoding="utf-8")

    # The main checkout itself is the clean-default-branch case.
    return main


def self_test() -> int:
    problems: list[str] = []

    def expect(condition: bool, description: str) -> None:
        if not condition:
            problems.append(description)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        main = build_fixture(base)

        result = collect("acme/widget", main, None, DEFAULT_STALL_HOURS, now())
        by_branch = {w["branch"]: w for w in result["worktrees"]}

        expect(result["counts"]["worktrees"] == 2,
               f"expected 2 worktrees, got {result['counts']['worktrees']}")
        expect("feat/shared-writers" in by_branch,
               f"branches found: {sorted(by_branch)}")

        busy = by_branch.get("feat/shared-writers", {})
        expect(busy.get("commits_ahead") == 1,
               f"expected 1 commit ahead, got {busy.get('commits_ahead')}")
        expect(busy.get("unpushed") == 1,
               f"expected 1 unpushed commit, got {busy.get('unpushed')}")
        expect(busy.get("dirty") == 1,
               f"expected 1 dirty file, got {busy.get('dirty')}")
        expect(busy.get("in_flight") is True, "a worktree with work is in flight")
        expect(busy.get("kind") == "workspace",
               f"expected kind workspace, got {busy.get('kind')}")

        checkout = by_branch.get("main", {})
        expect(checkout.get("kind") == "checkout",
               "a clean worktree on the default branch is a checkout, not a session")
        expect(checkout.get("in_flight") is False,
               "a clean default-branch checkout is not work in flight")

        outside = base / "not-a-repo"
        outside.mkdir()
        empty = collect("acme/widget", outside, None, DEFAULT_STALL_HOURS, now())
        expect(empty["counts"]["worktrees"] == 0,
               "outside a git repository the result must be empty")
        expect("reason" in empty, "an empty result must say why it is empty")

        wrong = collect("acme/other", main, None, DEFAULT_STALL_HOURS, now())
        expect(wrong["counts"]["worktrees"] == 0,
               "a repository whose origin does not match must produce an empty result")

    if problems:
        print("local-sessions self-test FAILED:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("local-sessions self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("repo", nargs="?")
    parser.add_argument("--board")
    parser.add_argument("--cwd")
    parser.add_argument("--self-test", action="store_true", dest="self_test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    parser.error("not implemented")
    return 70


if __name__ == "__main__":
    sys.exit(main())
```

Make it executable: `chmod +x plugins/cabinet/scripts/local-sessions`

- [ ] **Step 2: Run the self-test and watch it fail**

Run: `python3 plugins/cabinet/scripts/local-sessions --self-test`
Expected: `NameError: name 'collect' is not defined`

- [ ] **Step 3: Implement enumeration and the git facts**

Insert above the self-test section:

```python
def now() -> datetime:
    return datetime.now(timezone.utc)


def git(args: list[str], cwd: Path) -> str | None:
    """Run a read-only git command. None means it did not work, which is data."""
    try:
        done = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def normalize_remote(url: str) -> str:
    """git@github.com:acme/widget.git and https://…/acme/widget both give acme/widget."""
    trimmed = url.strip().removesuffix(".git")
    trimmed = trimmed.split(":")[-1] if trimmed.startswith("git@") else trimmed
    parts = [p for p in trimmed.replace(":", "/").split("/") if p]
    return "/".join(parts[-2:]).lower() if len(parts) >= 2 else ""


def parse_worktrees(text: str) -> list[dict]:
    """`git worktree list --porcelain` into records. Bare worktrees are skipped."""
    records: list[dict] = []
    current: dict = {}
    for line in text.splitlines():
        if line.startswith("worktree "):
            if current:
                records.append(current)
            current = {"path": line[len("worktree "):], "branch": None, "bare": False}
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):].removeprefix("refs/heads/")
        elif line.strip() == "bare":
            current["bare"] = True
        elif line.strip() == "detached":
            current["branch"] = None
    if current:
        records.append(current)
    return [r for r in records if not r["bare"]]


def default_branch(cwd: Path) -> str:
    head = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd)
    if head:
        return head.split("/", 1)[-1]
    for candidate in ("main", "master"):
        if git(["rev-parse", "--verify", f"refs/remotes/origin/{candidate}"], cwd):
            return candidate
    return "main"


def dirty_paths(worktree: Path) -> tuple[int, list[str]]:
    """Total dirty entries, and the tracked-modified paths among them."""
    porcelain = git(["status", "--porcelain"], worktree)
    if not porcelain:
        return 0, []
    lines = [line for line in porcelain.splitlines() if line.strip()]
    tracked: list[str] = []
    for line in lines:
        code, path = line[:2], line[3:]
        if code == "??":
            continue
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        tracked.append(path.strip('"'))
    return len(lines), tracked


def last_activity(worktree: Path, tracked: list[str]) -> datetime | None:
    stamps: list[datetime] = []
    committed = git(["log", "-1", "--format=%cI"], worktree)
    if committed:
        stamps.append(datetime.fromisoformat(committed).astimezone(timezone.utc))
    for relative in tracked:
        try:
            mtime = (worktree / relative).stat().st_mtime
        except OSError:
            continue
        stamps.append(datetime.fromtimestamp(mtime, timezone.utc))
    return max(stamps) if stamps else None


def collect(
    repo: str,
    cwd: Path,
    board_numbers: set[int] | None,
    stall_hours: float,
    moment: datetime,
) -> dict:
    taken_at = moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    def empty(reason: str) -> dict:
        return {
            "repo": repo,
            "taken_at": taken_at,
            "stall_hours": stall_hours,
            "reason": reason,
            "counts": {"worktrees": 0, "in_flight": 0, "attributed": 0, "stalled": 0},
            "worktrees": [],
        }

    toplevel = git(["rev-parse", "--show-toplevel"], cwd)
    if not toplevel:
        return empty("not inside a git repository, so no local work could be seen")

    origin = git(["remote", "get-url", "origin"], cwd)
    if not origin or normalize_remote(origin) != repo.lower():
        return empty(f"this checkout's origin is not {repo}, so no local work was collected")

    listing = git(["worktree", "list", "--porcelain"], cwd)
    if listing is None:
        return empty("git could not list worktrees, so no local work was collected")

    base = default_branch(cwd)
    here = Path(toplevel).resolve()
    worktrees: list[dict] = []

    for record in parse_worktrees(listing):
        path = Path(record["path"])
        branch = record["branch"]
        ahead_raw = git(["rev-list", "--count", f"origin/{base}..HEAD"], path)
        ahead = int(ahead_raw) if ahead_raw and ahead_raw.isdigit() else 0
        unpushed_raw = git(["rev-list", "--count", "--not", "--remotes", "HEAD"], path)
        unpushed = int(unpushed_raw) if unpushed_raw and unpushed_raw.isdigit() else 0
        dirty, tracked = dirty_paths(path)
        activity = last_activity(path, tracked)
        idle_hours = (
            round((moment - activity).total_seconds() / 3600.0, 1) if activity else None
        )

        is_checkout = branch == base and dirty == 0 and ahead == 0
        worktrees.append(
            {
                "path": str(path),
                "branch": branch,
                "is_current": path.resolve() == here,
                "kind": "checkout" if is_checkout else "workspace",
                "in_flight": not is_checkout,
                "ticket": None,
                "ticket_source": "none",
                "rejected_ticket": None,
                "commits_ahead": ahead,
                "unpushed": unpushed,
                "dirty": dirty,
                "last_activity": activity.strftime("%Y-%m-%dT%H:%M:%SZ") if activity else None,
                "idle_hours": idle_hours,
                "stalled": bool(
                    (not is_checkout) and idle_hours is not None and idle_hours >= stall_hours
                ),
            }
        )

    in_flight = [w for w in worktrees if w["in_flight"]]
    return {
        "repo": repo,
        "taken_at": taken_at,
        "stall_hours": stall_hours,
        "counts": {
            "worktrees": len(worktrees),
            "in_flight": len(in_flight),
            "attributed": len([w for w in in_flight if w["ticket"] is not None]),
            "stalled": len([w for w in worktrees if w["stalled"]]),
        },
        "worktrees": worktrees,
    }
```

- [ ] **Step 4: Run the self-test and watch it pass**

Run: `python3 plugins/cabinet/scripts/local-sessions --self-test`
Expected: `local-sessions self-test passed.`

- [ ] **Step 5: Implement the CLI so the script is usable**

Replace `parser.error("not implemented")` and the `return 70` beneath it with:

```python
    if not args.repo or "/" not in args.repo:
        print("usage: local-sessions <owner/repo> [--board <path>]", file=sys.stderr)
        return 64

    stall_hours = DEFAULT_STALL_HOURS
    override = os.environ.get("CABINET_STALL_HOURS")
    if override:
        try:
            stall_hours = float(override)
        except ValueError:
            print(
                f"local-sessions: CABINET_STALL_HOURS is not a number ('{override}'); "
                f"using {DEFAULT_STALL_HOURS}",
                file=sys.stderr,
            )

    cwd = Path(args.cwd) if args.cwd else Path.cwd()
    result = collect(args.repo, cwd, None, stall_hours, now())

    slug = args.repo.replace("/", "-")
    out = Path(os.environ.get("TMPDIR", "/tmp")) / f"cabinet-sessions-{slug}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(summary_line(result), file=sys.stderr)
    print(f"sessions={out}")
    return 0
```

And add above `main`:

```python
def summary_line(result: dict) -> str:
    counts = result["counts"]
    if "reason" in result:
        return f"Local: no signal — {result['reason']}"
    detail = ""
    named = [w for w in result["worktrees"] if w["in_flight"] and w["ticket"]]
    if named:
        parts = [
            f"#{w['ticket']}"
            + (f", {w['idle_hours']:.0f}h" if w["idle_hours"] is not None else "")
            for w in named
        ]
        detail = f" ({'; '.join(parts)})"
    return (
        f"Local: {counts['worktrees']} worktrees · "
        f"{counts['in_flight']} in flight{detail} · {counts['stalled']} stalled"
    )
```

- [ ] **Step 6: Verify the CLI against this repository**

Run: `python3 plugins/cabinet/scripts/local-sessions amitbaz/ai-marketplace`
Expected: a `Local: …` line on stderr, `sessions=/…/cabinet-sessions-amitbaz-ai-marketplace.json` on stdout, exit 0. Then:

Run: `python3 plugins/cabinet/scripts/local-sessions amitbaz/wrong-repo`
Expected: `Local: no signal — this checkout's origin is not amitbaz/wrong-repo…`, still exit 0.

- [ ] **Step 7: Verify the script boundary check still passes**

Run: `python3 scripts/check-adapter-boundary.py`
Expected: exit 0. If it fails on a phrase, reword the docstring — do not weaken the check.

- [ ] **Step 8: Commit**

```bash
git add plugins/cabinet/scripts/local-sessions
git commit -m "feat(cabinet): see the work already open on this machine

A workspace opened from a ticket is a local branch with nothing pushed, so
the board shows the ticket as free while somebody is a commit deep in it.
Enumerate the repository's worktrees, record what each one has done, and
write a snapshot the dispatching command can hand to a role."
```

---

### Task 2: `local-sessions` — attribute worktrees to tickets

**Files:**
- Modify: `plugins/cabinet/scripts/local-sessions`
- Modify: `.github/workflows/validate.yml`

**Interfaces:**
- Consumes: `collect(repo, cwd, board_numbers, stall_hours, moment)` and the fixture builder from Task 1.
- Produces: `ticket_for(worktree, branch, base, board_numbers)` returning `(ticket, source, rejected)` where `source` is one of `attachment`, `branch`, `commit`, `none`. Populates `ticket`, `ticket_source`, `rejected_ticket` on every worktree record, and `counts.attributed`.

- [ ] **Step 1: Extend the fixture, then write the failing assertions**

In `build_fixture`, after the `busy` worktree's uncommitted change, add:

```python
    attach = busy / ".superset" / "attachments"
    attach.mkdir(parents=True)
    (attach / "github-issue-179.md").write_text("body\n", encoding="utf-8")

    # A branch whose name carries a version, not a ticket.
    trap = base / "trap"
    run(["git", "worktree", "add", "-b", "fix/v2-parser", str(trap)], main)
    (trap / "b.txt").write_text("x\n", encoding="utf-8")
    run(["git", "add", "-A"], trap)
    run(["git", "commit", "-m", "parser fix"], trap)

    # A branch whose name does carry a ticket, for the board cross-check.
    named = base / "named"
    run(["git", "worktree", "add", "-b", "issue-4242-cleanup", str(named)], main)
    (named / "c.txt").write_text("x\n", encoding="utf-8")
    run(["git", "add", "-A"], named)
    run(["git", "commit", "-m", "cleanup"], named)
```

In `self_test`, change the worktree count expectation from 2 to 4, and add before the `outside` block:

```python
        expect(busy.get("ticket") == 179,
               f"attachment must win attribution, got {busy.get('ticket')}")
        expect(busy.get("ticket_source") == "attachment",
               f"expected source attachment, got {busy.get('ticket_source')}")

        trap = by_branch.get("fix/v2-parser", {})
        expect(trap.get("ticket") is None,
               f"a version in a branch name is not a ticket, got {trap.get('ticket')}")
        expect(trap.get("ticket_source") == "none",
               f"expected source none, got {trap.get('ticket_source')}")

        named = by_branch.get("issue-4242-cleanup", {})
        expect(named.get("ticket") == 4242,
               f"issue-<n> in a branch name is a ticket, got {named.get('ticket')}")

        checked = collect("acme/widget", main, {179}, DEFAULT_STALL_HOURS, now())
        checked_by_branch = {w["branch"]: w for w in checked["worktrees"]}
        rejected = checked_by_branch.get("issue-4242-cleanup", {})
        expect(rejected.get("ticket") is None,
               "a branch-derived number absent from the board must be rejected")
        expect(rejected.get("rejected_ticket") == 4242,
               f"the rejected candidate must be recorded, got {rejected.get('rejected_ticket')}")
        expect(checked["counts"]["attributed"] == 1,
               f"expected 1 attributed worktree, got {checked['counts']['attributed']}")

        stale = collect("acme/widget", main, None, 0.0, now())
        expect(all(w["stalled"] for w in stale["worktrees"] if w["in_flight"]),
               "a zero-hour threshold must mark every in-flight worktree stalled")
```

- [ ] **Step 2: Run the self-test and watch it fail**

Run: `python3 plugins/cabinet/scripts/local-sessions --self-test`
Expected: FAIL, listing `attachment must win attribution, got None` among others.

- [ ] **Step 3: Implement attribution**

Add above `collect`:

```python
ATTACHMENT = re.compile(r"^github-issue-(\d+)\.md$")

# Only unambiguous shapes. A bare number anywhere in a branch name is not a
# ticket: fix/v2-parser is a parser, not ticket 2.
BRANCH_TICKET = [
    re.compile(r"#(\d+)"),
    re.compile(r"(?:^|[/_-])issues?[/_-]?(\d+)(?=$|[/_-])"),
    re.compile(r"(?:^|[/_-])gh[/_-](\d+)(?=$|[/_-])"),
    re.compile(r"^(\d+)-"),
]

COMMIT_TICKET = re.compile(r"#(\d+)")


def ticket_for(
    worktree: Path, branch: str | None, base: str, board_numbers: set[int] | None
) -> tuple[int | None, str, int | None]:
    """(ticket, source, rejected candidate). Evidence on disk beats a name."""
    attachments = worktree / ".superset" / "attachments"
    if attachments.is_dir():
        for entry in sorted(attachments.iterdir()):
            found = ATTACHMENT.match(entry.name)
            if found:
                # An attachment is the ticket the workspace was opened from.
                # It is not cross-checked: a ticket can close while its
                # workspace is still open, and that is exactly the state the
                # brief needs to report.
                return int(found.group(1)), "attachment", None

    def accept(candidate: int, source: str) -> tuple[int | None, str, int | None]:
        if board_numbers is not None and candidate not in board_numbers:
            return None, "none", candidate
        return candidate, source, None

    if branch:
        for pattern in BRANCH_TICKET:
            found = pattern.search(branch)
            if found:
                return accept(int(found.group(1)), "branch")

    log = git(["log", "--format=%s%n%b", f"origin/{base}..HEAD"], worktree)
    if log:
        found = COMMIT_TICKET.search(log)
        if found:
            return accept(int(found.group(1)), "commit")

    return None, "none", None
```

In `collect`, replace the three placeholder lines in the record with a call made just before the record is appended:

```python
        ticket, ticket_source, rejected = ticket_for(path, branch, base, board_numbers)
```

and set `"ticket": ticket, "ticket_source": ticket_source, "rejected_ticket": rejected`.

- [ ] **Step 4: Run the self-test and watch it pass**

Run: `python3 plugins/cabinet/scripts/local-sessions --self-test`
Expected: `local-sessions self-test passed.`

- [ ] **Step 5: Wire `--board` into the CLI**

In `main`, replace `result = collect(args.repo, cwd, None, stall_hours, now())` with:

```python
    board_numbers: set[int] | None = None
    if args.board:
        try:
            board = json.loads(Path(args.board).read_text(encoding="utf-8"))
            board_numbers = {int(issue["number"]) for issue in board.get("open_issues", [])}
        except (OSError, ValueError, KeyError, TypeError):
            print(
                f"local-sessions: could not read the board at {args.board}; "
                "ticket numbers from branch names and commits are reported unverified",
                file=sys.stderr,
            )

    result = collect(args.repo, cwd, board_numbers, stall_hours, now())
```

- [ ] **Step 6: Verify against this repository**

Run: `python3 plugins/cabinet/scripts/local-sessions amitbaz/ai-marketplace && cat "${TMPDIR:-/tmp}/cabinet-sessions-amitbaz-ai-marketplace.json"`
Expected: every worktree present with a `ticket_source`, and no ticket invented for a branch like `rich-lead`.

- [ ] **Step 7: Add the CI step**

In `.github/workflows/validate.yml`, after the `Check the metrics collector` step:

```yaml
      - name: Check the local session scan
        run: python3 plugins/cabinet/scripts/local-sessions --self-test
```

- [ ] **Step 8: Run the boundary check and the new CI step locally**

Run: `python3 scripts/check-adapter-boundary.py && python3 plugins/cabinet/scripts/local-sessions --self-test`
Expected: both pass.

- [ ] **Step 9: Commit**

```bash
git add plugins/cabinet/scripts/local-sessions .github/workflows/validate.yml
git commit -m "feat(cabinet): attribute local work to a ticket from evidence, never a guess

The workspace attachment on disk is the ticket the work was opened from, so
it wins. A number read out of a branch name or a commit message is only
accepted when the board has it open, and the rejected candidate is kept so
the delivery lead can say local work exists without naming the wrong ticket."
```

---

### Task 3: `board-snapshot` — fetch what merged

**Files:**
- Modify: `plugins/cabinet/scripts/board-snapshot`
- Modify: `.github/workflows/validate.yml`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `board-snapshot <owner/repo> [--since <iso8601>]`; the board JSON gains `recently_merged` (array of `{number, title, mergedAt, headRefName, closes: [int]}`) and `counts.merged_since` (integer) plus `merged_window` (the ISO timestamp, or `null`).

- [ ] **Step 1: Write the failing self-test**

At the top of `board-snapshot`, immediately after `set -euo pipefail`, add:

```bash
normalize_since() {
    # An ISO-8601 instant, or empty when there is no usable window. Callers
    # treat empty as "the window is unknown" rather than substituting a guess.
    case "${1:-}" in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) printf '%sT00:00:00Z' "$1" ;;
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*) printf '%s' "$1" ;;
        *) printf '' ;;
    esac
}

out_path() {
    printf '%s/cabinet-%s-%s.json' "${TMPDIR:-/tmp}" "$1" "${2//\//-}"
}

if [ "${1:-}" = "--self-test" ]; then
    fail=0
    check() {
        if [ "$2" != "$3" ]; then
            echo "  - $1: expected '$3', got '$2'"
            fail=1
        fi
    }
    check "a date becomes an instant" "$(normalize_since 2026-09-01)" "2026-09-01T00:00:00Z"
    check "an instant is kept" "$(normalize_since 2026-09-01T10:11:12Z)" "2026-09-01T10:11:12Z"
    check "nonsense is rejected" "$(normalize_since yesterday)" ""
    check "an absent window is empty" "$(normalize_since)" ""
    check "the slug replaces every slash" "$(out_path board acme/widget)" \
        "${TMPDIR:-/tmp}/cabinet-board-acme-widget.json"
    if [ "$fail" -ne 0 ]; then
        echo "board-snapshot self-test FAILED:"
        exit 1
    fi
    echo "board-snapshot self-test passed."
    exit 0
fi
```

- [ ] **Step 2: Run it and watch it fail**

Run: `bash plugins/cabinet/scripts/board-snapshot --self-test`
Expected: FAIL — the existing argument handling rejects `--self-test` as a repo before reaching the new block, or `normalize_since` is not yet defined. Move the block above the `REPO=` assignment until it runs and reports a real assertion result.

- [ ] **Step 3: Make the self-test pass and add `--since` parsing**

Confirm the block sits after `set -euo pipefail` and before the existing `REPO="${1:-}"`. Then, after the `REPO` validation, add:

```bash
SINCE=""
if [ "${2:-}" = "--since" ]; then
    SINCE="$(normalize_since "${3:-}")"
    if [ -z "$SINCE" ] && [ -n "${3:-}" ]; then
        echo "board-snapshot: --since '${3}' is not a date I can use; reporting no window" >&2
    fi
fi
```

Then replace the existing output-path lines

```bash
SLUG="${REPO//\//-}"
OUT="${TMPDIR:-/tmp}/cabinet-board-${SLUG}.json"
EPICS_OUT="${TMPDIR:-/tmp}/cabinet-epics-${SLUG}.json"
```

with calls to the function the self-test covers, so it is the real path
builder rather than a copy of one:

```bash
OUT="$(out_path board "$REPO")"
EPICS_OUT="$(out_path epics "$REPO")"
```

Run: `bash plugins/cabinet/scripts/board-snapshot --self-test`
Expected: `board-snapshot self-test passed.`

- [ ] **Step 4: Fetch merged pull requests**

After the `branches=` assignment, add:

```bash
# What has landed since the last run. Without this the brief can only infer
# change by diffing a notebook, and an inference is not something it may
# report as observed fact.
if [ -n "$SINCE" ]; then
    merged="$(gh pr list --repo "$REPO" --state merged --limit 100 \
        --json number,title,mergedAt,headRefName,closingIssuesReferences \
        --jq "[.[] | select(.mergedAt >= \"$SINCE\") |
              {number, title, mergedAt, headRefName,
               closes: [.closingIssuesReferences[].number]}]" 2>/dev/null || echo '[]')"
else
    merged='[]'
fi
```

In the `jq -n` assembly for `$OUT`, add `--argjson merged "$merged"` and `--arg since "$SINCE"`, then add to the object:

```
        merged_window: (if $since == "" then null else $since end),
        recently_merged: $merged,
```

and inside `counts`, add:

```
            merged_since: ($merged | length),
```

- [ ] **Step 5: Verify against the live board**

Run: `bash plugins/cabinet/scripts/board-snapshot amitbaz/ai-marketplace --since 2026-09-01`
Expected: the usual `Board: …` stderr line and `board=…`. Then:

Run: `jq '.counts.merged_since, .merged_window, (.recently_merged[0] // "none")' "${TMPDIR:-/tmp}/cabinet-board-amitbaz-ai-marketplace.json"`
Expected: a non-zero count, the window echoed, and a merged pull request with a `closes` array.

Run without `--since` and confirm `merged_window` is `null` and `recently_merged` is `[]`.

- [ ] **Step 6: Add the CI step**

In `.github/workflows/validate.yml`, after the local session scan step:

```yaml
      - name: Check the board snapshot
        run: bash plugins/cabinet/scripts/board-snapshot --self-test
```

- [ ] **Step 7: Commit**

```bash
git add plugins/cabinet/scripts/board-snapshot .github/workflows/validate.yml
git commit -m "feat(cabinet): fetch what merged, so the brief can stop inferring change

The snapshot fetched open issues and open pull requests and nothing else,
which left the brief describing merges no run had observed. Fetch pull
requests merged since a given moment along with the tickets they close, and
record the window so an absent one can be reported as unknown."
```

---

### Task 4: the delivery lead consumes the local signal

**Files:**
- Modify: `plugins/cabinet/agents/delivery-lead.md`

**Interfaces:**
- Consumes: the `sessions=` JSON contract from Tasks 1 and 2, and `recently_merged` from Task 3.
- Produces: a role that reports what is taken from local and remote signals together, and names which signal it used. Later tasks rely on the role reporting in-flight work with its ticket, age and stall state.

- [ ] **Step 1: Rewrite step 6, "Work out what is taken"**

Replace the existing step 6 with:

```markdown
6. **Work out what is taken**, from two signals rather than one.

   *Remote:* a ticket with an open pull request is in flight.

   *Local:* if you were given a `sessions=` path, read it. It lists every
   worktree of this repository on this machine, with what each one has
   committed and changed. A worktree marked `in_flight` with a `ticket` is
   work in progress, whether or not anything has been pushed — a workspace
   opened from a ticket is a local branch GitHub cannot see, and treating
   that ticket as free is how a startable frontier recommends work somebody
   is already a commit deep in.

   Say which signal you used for each ticket you call taken. A worktree with
   `ticket_source: none` is unattributed local work: report that work is
   underway and that you could not tell which ticket, and never attach it to
   a guess. A `rejected_ticket` means a number was read out of a branch name
   or commit and the board does not have it open — say so; a stale branch
   name is itself worth knowing.

   A worktree marked `stalled` has had no commit and no file touched inside
   the threshold in its `stall_hours` field. Report it with its age and what
   it blocks: work claimed and abandoned holds the frontier closed while
   looking like progress.

   If you were given no `sessions=` path, say that this run had no local
   signal and that anything started outside a pull request is invisible to
   it. Do not infer local work from the branch list.

   Branch names remain the weakest signal. Use the branch convention the
   charter records; if branch names do not carry ticket numbers, say the
   signal is weak and name what you fell back on. Do not treat an assignee
   as in-flight unless the charter says the project uses assignees that way.
```

- [ ] **Step 2: Teach it to use merged data in step 5**

In step 5 ("Re-derive the board"), after the sentence listing `open_issues`, `open_prs` and `branches`, add:

```markdown
   `recently_merged` is what landed inside `merged_window`, each entry naming
   the tickets it closed. This is the only thing you may describe as having
   changed. If `merged_window` is null, the window is unknown: say that
   rather than describing change you did not observe. Never state that
   something merged because your notebook no longer lists it.
```

- [ ] **Step 3: Add `sessions=` to the memory-paths section**

In "Where your memory is", after the sentence naming `memory=`, add:

```markdown
The same is true of every other path you are handed — `board=`, `epics=`,
`sessions=`. You cannot derive any of them and must not guess at one. Work
with the paths you were given and say plainly which you were not given.
```

- [ ] **Step 4: Verify the changes are structurally present**

Run:
```bash
grep -c "sessions=" plugins/cabinet/agents/delivery-lead.md
grep -c "recently_merged" plugins/cabinet/agents/delivery-lead.md
grep -c "ticket_source" plugins/cabinet/agents/delivery-lead.md
```
Expected: each at least 1.

Run: `python3 scripts/check-adapter-boundary.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add plugins/cabinet/agents/delivery-lead.md
git commit -m "feat(cabinet): let the delivery lead see work that never reached GitHub

What is taken came from open pull requests and remote branches alone, so a
workspace open on a ticket with nothing pushed read as free and the ticket
was ranked first on the startable frontier. Read the local session snapshot
alongside the remote signals, say which signal each call came from, and
report unattributed and stalled work rather than guessing at either."
```

---

### Task 5: the standup collects the signal and reports moves

**Files:**
- Modify: `plugins/cabinet/commands/standup.md`

**Interfaces:**
- Consumes: `local-sessions` (Tasks 1–2), `board-snapshot --since` (Task 3), the delivery lead's reporting contract (Task 4).
- Produces: the brief format that `commands/now.md` reuses for its position block in Task 6.

- [ ] **Step 1: Add the scan to §3**

In "3. Take the board snapshot, then dispatch", after the `board-snapshot` invocation block, insert:

```markdown
Pass `--since <date>` using the date of the delivery lead's newest notebook
entry, so the snapshot carries what merged since the last run. With no prior
entry, use seven days ago. With no usable date at all, omit the flag — the
brief then reports the change window as unknown rather than describing
change nobody observed.

Then take the local picture:

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/local-sessions <owner/repo> --board <board path>
```

It prints `sessions=<path>`. **Give that path to the delivery lead in its
prompt** alongside `board=` and `epics=`. It lists every worktree of this
repository on this machine and what each one has done, which is the only way
this run can know that a ticket is already being worked on: a workspace
opened from a ticket is a local branch with nothing pushed, and GitHub cannot
see it. Passing `--board` is what keeps a number read out of a branch name
from being reported as a ticket the board does not have.

Show the owner its stderr line next to the board's:

```
Board: 67 open · 3 epics · 0 PRs · 2 branches → delivery lead
Local: 2 worktrees · 1 in flight (#179, 3h) · 0 stalled
```

If the script reports no signal, say so in one line and carry on. The brief
then says that work started outside a pull request was invisible to this run,
because a frontier derived without the local picture can recommend work that
is already underway.
```

- [ ] **Step 2: Replace §9 entirely**

Replace the whole of "## 9. The brief" with:

```markdown
## 9. The brief

The brief has exactly two blocks. Everything the roles produced is either a
move or a count — there is no third thing, and no section that repeats a fact
already stated.

**Position first.** Four lines at most, derived from the charter's stage and
ending conditions against the snapshots you just took:

```
WHERE YOU STAND · <date>
<stage>. <named gate> not crossed.
Gate <X>: <n> items · <n> startable · <n> purchases · <n> unticketed.
In flight: #179 — local, 1 commit, 5 files dirty, 3h.
```

`In flight` comes from the delivery lead's reading of the session snapshot.
Name each ticket with where it lives, what it has done and how long since it
moved. `In flight: none` when there is none. When the run had no local
signal, write `In flight: unknown — no local signal this run` instead of a
zero. A zero that means "I could not see" is the failure this line exists to
prevent.

Where the "to gate" counts come from: the charter's *what is absent* section
and whatever launch or preconditions epic it cites. If neither exists, say
the count cannot be derived rather than inventing one. A made-up number here
is the worst possible failure of this block, because it is the line the owner
steers by.

**Then the moves.** One ranked list, at most five, decisions and dispatch
interleaved, ranked by cost of delay using the ordering in §7:

```
YOUR MOVES · <n>        (all delivery lead — shallow run)

 1. <Imperative>. <One sentence: what it costs to act on this late.>
    → <the command to type>

 2. ...

Quiet: <n> handled · <n> proposals · <n> more startable · <n> blocked.
Ask for any of these.
```

Four rules make this list worth reading:

1. **A fact appears once.** Anything that became a move does not appear again
   as a contradiction, a proposal or a frontier entry. The owner is reading
   one set of facts, and re-grouping them four ways is not more information —
   it is the pile this brief exists to replace.
2. **Every move ends in a command the owner can type.** `/cabinet:decide <n>`
   for an open decision, `/cabinet:brief <n>` for a ticket about to be picked
   up wrong, `/cabinet:charter` for a line that no longer holds, or the
   dispatch command the charter records for this project. If the charter
   records none, name the ticket and say plainly that there is no recorded
   way to start it — that absence is worth an amendment, not a blank. A move
   with no command is not finished thinking: hand it back to the role.
3. **Imperative verb first, two lines at most**, then the command. The cost
   of delay is one sentence. A role that needs a paragraph has not finished
   translating its own finding.
4. **The role stamp goes in the header when every move came from one role**,
   and on the line only when several roles ran. Six identical labels down the
   left margin carry nothing; the owner can still ask which role raised any
   item and get an accountable answer.

The startable frontier collapses into this list: its top candidate is a move,
the rest is the `more startable` count. Tickets the delivery lead reported as
taken are not on the frontier at all — they are in the position block. A
worktree it reported as stalled becomes its own move: check on it or drop it.
A ticket whose pull request has merged while its worktree is still open and
dirty becomes a move too — the work landed, close the workspace.

Counsel's holds are named in the `Quiet` line with the threshold they protect
and the fact that one decision overrides them. Never let a hold remove
something from the frontier silently.

**Everything in both blocks is written for the owner, not an engineer** — a
capability and what it costs, never the mechanism. No file path, function or
line number appears anywhere in the brief. If a role handed you one, translate
it; if you cannot, that role has not finished its thinking, and say so instead
of passing the mechanism through.

**Never state that anything changed unless this run observed it.** Change
comes from the snapshot's `recently_merged` and its window. If the window is
null, say the change window is unknown. A notebook no longer listing a ticket
is not evidence that it merged.

Never volunteer full ticket bodies, full notebooks, or the whole ledger. Name
counts and offer to expand.
```

- [ ] **Step 3: Check no removed section left a dangling reference**

Run:
```bash
grep -n "CHIEF OF STAFF\|Startable frontier\|WHERE THE COMPANY STANDS" plugins/cabinet/commands/standup.md
```
Expected: no matches. If any remain, they are references to the deleted format — remove or reword them.

Run:
```bash
grep -c "sessions=" plugins/cabinet/commands/standup.md
grep -c "YOUR MOVES" plugins/cabinet/commands/standup.md
```
Expected: each at least 1.

- [ ] **Step 4: Read §7 and §9 together once**

§7 ranks by cost of delay and caps at five; §9 now renders that ranking. Confirm §7 still reads correctly with the queue gone — in particular that "at most five items reach the owner" and the one-way-door rule are stated once, in §7, and not restated in §9.

- [ ] **Step 5: Commit**

```bash
git add plugins/cabinet/commands/standup.md
git commit -m "feat(cabinet)!: end the brief in moves the owner can act on

The brief followed its own specification and was still unactionable: four
decisions, a frontier, contradictions and proposals handed over as separate
groupings with the next move left to be assembled out of them, no item
ending in a command, and the same facts appearing under four headings.

Collapse it into a position block and one ranked list of moves, each an
imperative with the command to type. Take the local session scan before
dispatching so the position block can report what is already in flight
instead of a zero that meant nobody looked."
```

---

### Task 6: `/cabinet:now`

**Files:**
- Create: `plugins/cabinet/commands/now.md`

**Interfaces:**
- Consumes: `memory-path`, `board-snapshot --since`, `local-sessions --board`, and the position-block format from Task 5.
- Produces: a command that reads and prints only. No task depends on it.

- [ ] **Step 1: Write the command**

```markdown
---
description: Where things stand right now — what is in flight on this machine, what merged since the last standup, and what the board looks like. Reads only; dispatches no roles and writes nothing.
argument-hint: ""
---

# /cabinet:now

The standup is a run: it dispatches roles, ranks what reaches you, and writes
to the notebooks. This is not that. It answers one question — what is true
right now — and costs seconds.

Use it when you have opened a workspace, merged something, or come back to
the terminal and want the picture refreshed without paying for a brief.

**This command writes nothing.** Not to the notebooks, not to the decision
inbox, not to the board. If something here deserves a decision, say so and
point at `/cabinet:standup`; do not record it yourself.

Do not narrate the steps. Produce the report.

## 1. Resolve the memory

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/memory-path <owner/repo>
```

`owner/repo` comes from `git remote get-url origin`. If `exists=false`, say
this project has no Cabinet memory, suggest `/cabinet:hire`, and stop.

Read `<memory>/company.md` for the stage and the gate. Read the newest dated
entry in `<memory>/delivery-lead.md` for when the last run happened — that
date is the change window.

## 2. Take both snapshots

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/board-snapshot <owner/repo> --since <that date>
"${CLAUDE_PLUGIN_ROOT}"/scripts/local-sessions <owner/repo> --board <board path>
```

Use seven days ago when there is no prior entry, and omit `--since` when
there is no usable date at all. If either script reports no signal, say which
one and carry on.

## 3. Report

```
NOW · <date> <time>

<stage>. <named gate> not crossed.

In flight
  #179 — local, 1 commit, 5 files dirty, last touched 3h ago
  #204 — pull request open, checks green

Since <window>
  3 merged: #171, #180, #183.

Board
  67 open · 0 pull requests · 4 startable.
```

Rules, the same ones the brief runs under:

- **Written for the owner, not an engineer.** No file path, function or line
  number. A worktree is named by its ticket and its age, never by its
  directory.
- **A ticket with no attribution is reported as unattributed local work.**
  Never attach it to a guess.
- **`In flight: unknown — no local signal` when the scan found nothing to
  read.** A zero that means "I could not see" is worse than saying so.
- **Nothing is described as having changed unless `recently_merged` says so.**
  With no window, say the window is unknown.
- **Stalled work is named** with its age. Work claimed and abandoned holds
  the frontier closed while looking like progress.

Close with one line: `/cabinet:standup` for what to do about any of it.
```

- [ ] **Step 2: Verify it is discoverable and consistent**

Run: `ls plugins/cabinet/commands/`
Expected: `now.md` present. Commands are discovered from this directory — neither `plugin.json` enumerates them, so nothing else registers it.

Run: `head -4 plugins/cabinet/commands/now.md`
Expected: frontmatter with `description:`, matching every other command in the directory.

- [ ] **Step 3: Commit**

```bash
git add plugins/cabinet/commands/now.md
git commit -m "feat(cabinet): add a read-only check of where things stand right now

Detection is poll-at-command-time by design, so the honest answer to seeing
a new workspace or a merged pull request between standups has to be a
command that costs seconds. Take both snapshots, report what is in flight
and what landed, dispatch no roles and write nothing."
```

---

### Task 7: documentation and version

**Files:**
- Modify: `plugins/cabinet/FILES.md`, `plugins/cabinet/README.md`
- Modify: `plugins/cabinet/.claude-plugin/plugin.json`, `plugins/cabinet/.codex-plugin/plugin.json`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing later depends on.

- [ ] **Step 1: Read what is there**

Run: `grep -n "board-snapshot\|memory-path\|standup" plugins/cabinet/FILES.md plugins/cabinet/README.md`

Match the surrounding style rather than inventing a new one.

- [ ] **Step 2: Document the script and the command in `FILES.md`**

Add two entries, formatted like the ones already around them:

- `scripts/local-sessions` — "Enumerates every worktree of this repository on
  this machine and attributes each to a ticket from evidence on disk, so the
  delivery lead can see work that was never pushed. Passed to roles as
  `sessions=`."
- `commands/now.md` — "`/cabinet:now`. What is in flight and what merged since
  the last standup. Reads only: no roles dispatched, nothing written."

- [ ] **Step 3: Update `README.md`**

Three changes:

- Replace the standup section's example output with the two-block shape from
  Task 5 — the `WHERE YOU STAND` block and the `YOUR MOVES` list.
- Add, next to that example: "Cabinet also sees the work already open on this
  machine. A workspace opened from a ticket is a local branch with nothing
  pushed, so the board shows the ticket as free; Cabinet reads the worktrees
  instead. Nothing is registered when you open one — the worktree existing is
  the claim. This covers the machine it runs on."
- Add `/cabinet:now` to the command list: "Where things stand right now — what
  is in flight, what merged since the last standup. Seconds, and writes
  nothing."

- [ ] **Step 4: Bump the version in both manifests**

`0.8.0` → `0.9.0` in `plugins/cabinet/.claude-plugin/plugin.json` and `plugins/cabinet/.codex-plugin/plugin.json`. Leave the descriptions alone: "a chief-of-staff brief capped at five one-way-door decisions" is still true.

- [ ] **Step 5: Run the whole validation suite**

Run:
```bash
for f in plugins/cabinet/.claude-plugin/plugin.json plugins/cabinet/.codex-plugin/plugin.json; do
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" && echo "ok $f"
done
python3 scripts/check-adapter-boundary.py
python3 scripts/check-adapter-boundary.py --self-test
python3 plugins/cabinet/scripts/local-sessions --self-test
bash plugins/cabinet/scripts/board-snapshot --self-test
```
Expected: every one passes.

- [ ] **Step 6: Commit**

```bash
git add plugins/cabinet/FILES.md plugins/cabinet/README.md \
        plugins/cabinet/.claude-plugin/plugin.json \
        plugins/cabinet/.codex-plugin/plugin.json
git commit -m "docs(cabinet): document the local session scan, /cabinet:now and the new brief"
```

---

## Manual verification before the pull request

Automated checks cover the scripts. The brief is prose and cannot be unit
tested, so run it once for real:

1. In `career-platform`, run `/cabinet:standup`.
2. Confirm the position block names #179 as in flight rather than reporting
   zero, and that #179 is not on the frontier.
3. Confirm every move ends in a command that exists.
4. Confirm no fact appears in two places, and that no file path or line
   number reached the brief.
5. Run `/cabinet:now` and confirm it prints the same in-flight picture,
   writes nothing, and takes seconds.
6. Confirm the change line names merged pull requests, and that it says the
   window is unknown when the delivery lead has no prior notebook entry.
