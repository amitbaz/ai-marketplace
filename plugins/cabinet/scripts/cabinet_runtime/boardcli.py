"""The command line the two legacy snapshot wrappers delegate to.

`board-snapshot` and `charter-sources` were written in shell against `gh` and
`jq`, and they still work that way. What they could not do is follow every page
or say when a page did not arrive: a `--limit 500` that hits its limit and a
board of exactly 500 issues look identical from the outside, and a failed page
became an empty list.

This module answers the same two commands from the paginated adapter, writes
the same files, prints the same `key=path` lines and the same one-line summary,
and adds two facts the shell version could not carry: `complete`, and the list
of pages that did not arrive. The wrappers keep their old path for a machine
without `python3`, so nothing here is a new install-time requirement.
"""

import json
import os
import sys
import time

from . import processes
from .errors import CabinetError
from .github import GithubAdapter, gh_run

#: Directories whose prose records how something was built rather than what the
#: company decided. A charter draft skips them unless it is asked for them.
SKIPPED_MARKERS = ("/superpowers/", "/sdd/")
ALWAYS_READ = ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "README.md")

USAGE = "usage: python3 -m cabinet_runtime.boardcli board|charter-sources " \
        "<owner/repo> [--since <instant>]"


def main(argv=None):
    words = list(sys.argv[1:] if argv is None else argv)
    if len(words) < 2 or words[0] not in ("board", "charter-sources"):
        sys.stderr.write(USAGE + "\n")
        return 64
    command, repo = words[0], words[1]
    since = words[3] if len(words) > 3 and words[2] == "--since" else None
    adapter = GithubAdapter(gh_run(cwd=os.getcwd()), repo)
    try:
        if command == "board":
            return _board(adapter, repo, since)
        return _charter_sources(adapter, repo)
    except CabinetError as problem:
        sys.stderr.write("%s: %s\n" % (command, problem.message))
        return 78


# --- board -------------------------------------------------------------------

def _board(adapter, repo, since):
    board = adapter.read_board(since)
    out = _write(_path("board", repo), board)
    epics = _write(_path("epics", repo),
                   {"repo": repo, "taken_at": board["taken_at"],
                    "epics": [row for row in board["open_issues"]
                              if "epic" in (row["labels"] or [])]})
    counts = board["counts"]
    sys.stderr.write(
        "Board: %d open · %d epics · %d PRs · %d branches · %d merged\n"
        % (counts["open_issues"], counts["epics"], counts["open_prs"],
           counts["branches"], counts["merged_since"]))
    _warn_incomplete("board-snapshot", board)
    print("board=%s" % out)
    if counts["epics"]:
        print("epics=%s" % epics)
    return 0


def _warn_incomplete(label, board):
    """Say out loud which part of the board is missing. Never silently.

    The file records the same thing, so a role reading it sees `complete:
    false` too. This line is for the person watching the command run.
    """

    if board.get("complete"):
        return
    for problem in board.get("errors") or []:
        sys.stderr.write(
            "%s: %s page %s did not arrive (%s); this snapshot is incomplete "
            "and does not say what is startable\n"
            % (label, problem.get("collection"), problem.get("page"),
               problem.get("detail")))


# --- charter sources ---------------------------------------------------------

def _charter_sources(adapter, repo):
    rejected, recorded, discussion, complete = _sources(adapter, repo)
    inventory = _inventory()
    taken_at = adapter.board_state()["checked"] or _now()
    comments = sum(len(row["comments"]) for row in discussion)
    out = _write(_path("charter-sources", repo), {
        "repo": repo, "taken_at": taken_at, "complete": complete,
        "note": "Sources that carry decisions rather than work. Bounded on "
                "purpose: this is not the whole repository, and hire is "
                "expected to say what it skipped.",
        "counts": {"rejected": len(rejected),
                   "recorded_decisions": len(recorded),
                   "tickets_with_discussion": len(discussion),
                   "comments": comments},
        "rejected": rejected, "recorded_decisions": recorded,
        "inventory": inventory})
    discussion_path = _write(_path("charter-discussion", repo),
                             {"repo": repo, "taken_at": taken_at,
                              "discussion": discussion})
    sys.stderr.write(
        "Sources: %d rejected · %d recorded decisions · %d comments on %d "
        "tickets · %d docs to read, %d skipped, %d unclassified\n"
        % (len(rejected), len(recorded), comments, len(discussion),
           inventory["read_count"], inventory["skipped_count"],
           inventory["unclassified_count"]))
    print("sources=%s" % out)
    if comments:
        print("discussion=%s" % discussion_path)
    return 0


def _sources(adapter, repo):
    """The three provider-side source sets, each fully paginated.

    This reaches the adapter's own paging helper rather than a public
    endpoint-taking method, deliberately: adding one would put an arbitrary
    endpoint back on the adapter's surface, and the surface being closed is
    what makes `apply`'s nine operations the whole of what can be reached.
    """

    errors = []
    issues, issues_complete = adapter._collect(
        "issues", "repos/%s/issues?state=all&per_page=%d"
        % (repo, adapter.page_size), errors)
    pulls, pulls_complete = adapter._collect(
        "merged", "repos/%s/pulls?state=closed&per_page=%d"
        % (repo, adapter.page_size), errors)
    rejected = [{"number": row["number"], "title": row.get("title"),
                 "url": row.get("html_url"), "closedAt": row.get("closed_at"),
                 "body": row.get("body")}
                for row in issues
                if "pull_request" not in row
                and row.get("state_reason") == "not_planned"]
    recorded = [{"number": row["number"], "title": row.get("title"),
                 "url": row.get("html_url"), "mergedAt": row.get("merged_at"),
                 "body": row.get("body")}
                for row in pulls
                if row.get("merged_at")
                and (row.get("title") or "").lower().startswith(("docs:",
                                                                 "docs("))]
    discussion = []
    for row in issues:
        if "pull_request" in row or row.get("state") != "open":
            continue
        if not row.get("comments"):
            continue
        comments, complete = adapter._collect(
            "comments", "repos/%s/issues/%d/comments?per_page=%d"
            % (repo, row["number"], adapter.page_size), errors)
        if not complete:
            continue
        discussion.append({
            "number": row["number"], "title": row.get("title"),
            "url": row.get("html_url"),
            "comments": [{"author": (item.get("user") or {}).get("login"),
                          "at": item.get("created_at"),
                          "body": item.get("body")} for item in comments]})
    return rejected, recorded, discussion, issues_complete and pulls_complete


def _inventory():
    """Every tracked Markdown file, split three ways, nothing falling through."""

    result = processes.run_argv(
        ["git", "ls-files", "*.md"], os.getcwd(),
        processes.build_env(("PATH", "HOME")), 60)
    if result["returncode"] != 0:
        return {"total": 0, "read_these": [], "read_count": 0,
                "skip_these_unless_asked": [], "skipped_count": 0,
                "unclassified": [], "unclassified_count": 0,
                "note": "not inside a git working tree; no inventory taken"}
    every = [line for line in result["stdout"].splitlines() if line.strip()]
    skip = [name for name in every
            if any(marker in "/" + name for marker in SKIPPED_MARKERS)]
    read = [name for name in every
            if name not in skip
            and (name.startswith("docs/") or "/" not in name
                 or name.rsplit("/", 1)[-1] in ALWAYS_READ)]
    rest = [name for name in every if name not in skip and name not in read]
    return {"total": len(every), "read_these": read, "read_count": len(read),
            "skip_these_unless_asked": skip, "skipped_count": len(skip),
            "unclassified": rest, "unclassified_count": len(rest),
            "note": "unclassified matched neither filter. Name the count and "
                    "offer them; a file that falls through silently is the "
                    "failure this script exists to end."}


# --- files -------------------------------------------------------------------

def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _path(kind, repo):
    root = os.environ.get("TMPDIR") or "/tmp"
    return os.path.join(root.rstrip("/") or "/",
                        "cabinet-%s-%s.json" % (kind, repo.replace("/", "-")))


def _write(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


if __name__ == "__main__":
    sys.exit(main())
