# Cabinet: an actionable standup brief, and knowing what is already in flight

**Date:** 2026-09-09
**Status:** approved design, not yet implemented

## The problem

The owner ran `/cabinet:standup` on `career-platform` and could not act on the
result. Two separate failures produced that.

**The brief's shape does not end in an action.** The run followed the current
specification exactly, so the specification is what is wrong. Four defects, all
visible in the output that prompted this work:

1. It never says what to do next. Four decisions, a startable frontier, a
   contradictions section and a proposals count are handed over as separate
   groupings, and the owner has to assemble the actual next move out of them.
   That assembly is the work the brief exists to do.
2. No item ends in a command. The brief closes with "Ask for detail on any of
   these" while `/cabinet:decide <n>` exists and is never named. Every item is a
   dead end.
3. The same fact appears in three or four places. Ticket #179 appeared in the
   position block, in "What changed", first on the startable frontier, and twice
   under "Blocked". Two decision items reappeared under "Contradictions" and
   again under "Proposals". This is what reads as an unstructured pile: not more
   information, one set of facts re-grouped four ways.
4. The role stamp carries no information when it is uniform. A shallow run
   dispatches only the delivery lead, so every line was stamped `DELIVERY LEAD`.

**The brief did not know a ticket was already being worked on.** It reported
`In flight: 0` and ranked #179 first on the startable frontier while another
local session had a worktree open on it, one commit ahead of trunk and five
files dirty. The delivery lead derives what is taken from remote branches and
open pull requests only (`plugins/cabinet/agents/delivery-lead.md`, step 6). A
Superset workspace is a local worktree on an unpushed branch, so GitHub cannot
see it. The recommendation was not merely stale, it was unactionable, and a
wrong first recommendation discredits the four correct items above it.

A third problem surfaced while diagnosing the second. `board-snapshot` fetches
`--state open` for both issues and pull requests and nothing else. Nothing
merged is ever fetched, and the delivery lead's tool grant contains no commit
tool. The brief's line "Five items merged to trunk today" therefore had no
source in the run that produced it. Merged data has to be fetched for the
brief to be allowed to make that claim.

## What is not changing

- **Roles hold no shell.** Every path is resolved by the command and passed
  into the role's prompt as `memory=`, `board=`, `epics=`. The new local
  signal follows the same pattern for the same reason.
- **Cabinet does not dispatch or supervise implementation agents.** Reading the
  filesystem to learn that a worktree exists is observation, not supervision.
  Nothing here starts, stops, watches or talks to another session.
- **Cabinet writes nothing to the board.** No label, assignee or comment is
  used to claim a ticket.
- **No external service.** Detection is git and the filesystem. If a second
  machine ever needs covering, the successor is Cabinet's own record under
  `~/.cabinet`, not a third-party bus.
- **`/cabinet:review`'s report format.** It is a different artifact with a
  different job — one block per role, in each role's own voice, weekly. It
  keeps its shape.

## Part A — `plugins/cabinet/scripts/local-sessions`

A new script, sibling to `board-snapshot` and `memory-path`, following their
conventions: bash, a `key=path` line on stdout, a one-line count summary on
stderr, soft failure with a stated reason.

```
local-sessions <owner/repo> [--board <path>] [--since <iso8601>]
```

It runs `git worktree list --porcelain` in the current directory, which
enumerates every worktree of the repository on this machine regardless of where
those directories live. Nothing has to be registered when a workspace is
opened: the worktree existing is the claim.

For each worktree it records:

- `path`, `branch` (or `detached`), and whether it is the worktree the command
  is running in
- `ticket` and `ticket_source`, resolved in this order:
  1. `attachment` — a file matching `.superset/attachments/github-issue-<N>.md`
  2. `branch` — a ticket number in the branch name, accepted **only** from an
     unambiguous pattern (`#<N>`, `issue-<N>`, `issues/<N>`, `gh-<N>`, or a
     leading `<N>-`). A bare number anywhere in the name is not accepted;
     `fix/v2-parser` must not resolve to ticket 2.
  3. `commit` — a `#<N>` reference in the commit messages ahead of the base
  4. `none`
- `commits_ahead` of the default base, and how many of those are unpushed
- `dirty`, the count from `git status --porcelain`
- `last_activity`, the later of the last commit's committer date and the newest
  modification time among tracked modified files
- `idle_hours`, and `stalled` when that crosses a threshold (default 24 hours,
  overridable with `CABINET_STALL_HOURS`)

**Attribution is verified, never guessed.** When `--board` is given, a number
resolved from a branch name or a commit message is only accepted if it appears
as an open issue in the snapshot. A number that fails that check is reported as
`ticket_source: none` with the rejected candidate recorded, so the delivery lead
can say "local work here, ticket unknown" rather than naming the wrong one.

**A clean checkout is not a session.** A worktree sitting on the default
branch, clean, with nothing ahead, is recorded as an idle checkout and is not
reported as work in flight.

Output goes to `${TMPDIR:-/tmp}/cabinet-sessions-<slug>.json` and the script
prints `sessions=<path>`, with a stderr line in the same shape as the board's:

```
Local: 2 worktrees · 1 in flight (#179, 3h) · 0 stalled
```

If the current directory is not a git repository, if its origin does not match
`owner/repo`, or if `git worktree list` fails, the script writes an empty
result and says so in one line. The run continues without a local signal, and
the brief says which kind of run it was.

## Part B — merged work in `board-snapshot`

`board-snapshot` gains an optional `--since <iso8601>` and two additions to its
output:

- `recently_merged`: pull requests merged since that timestamp, each with its
  number, title, `mergedAt`, head branch, and the issues it closed
  (`closingIssuesReferences`)
- `counts.merged_since` and the window it covers

The standup passes the date of the delivery lead's newest notebook entry as
`--since`, falling back to seven days when there is no prior entry. When no
window can be established, the field is absent and the brief must say the
change window is unknown rather than describing changes it did not observe.

This buys two things the owner asked for:

- **"What changed" becomes observed fact** — which pull requests merged and
  which tickets they closed, instead of a diff against a notebook that can
  invent merges.
- **Stale worktree cleanup** — a worktree whose ticket's pull request has
  merged, still sitting on disk dirty or ahead, becomes a move: the work
  landed, close the workspace.

## Part C — the brief contract, `commands/standup.md` §9

The position block and the decision queue are replaced by a position block and
a single ranked list of moves.

```
WHERE YOU STAND · <date>
<stage>. <gate> not crossed.
Gate <X>: <n> items · <n> startable · <n> purchases · <n> unticketed.
In flight: #179 — local, 1 commit, 5 files dirty, 3h.

YOUR MOVES · <n>        (all delivery lead — shallow run)

 1. <Imperative>. <One sentence: what it costs to answer or act late.>
    → <exact command to type>

 2. ...

Quiet: <n> handled · <n> proposals · <n> more startable · <n> blocked.
Ask for any of these.
```

Four rules do the work:

1. **A fact appears once.** Anything that became a move does not also appear in
   a tail section. The tail sections carry only what did not become a move, as
   counts.
2. **Every move ends in a runnable command.** `/cabinet:decide <n>`,
   `/cabinet:brief <n>`, `/cabinet:charter`, or the dispatch command the
   charter records for this project. If the charter records none, the move
   names the ticket and says plainly that there is no recorded way to start
   it — an absence worth an amendment, not a blank. A move with no command is
   not finished thinking and does not ship.
3. **Imperative verb first, two lines maximum**, then the command. The cost of
   delay is one sentence, not a paragraph.
4. **The role stamp moves to a header when it is uniform**, and appears per
   line only when several roles ran. Accountability is preserved — the owner
   can still ask which role raised an item — without four identical labels.

Decisions and dispatch interleave in the one list, ranked by cost of delay by
the existing rules in §7. The cap stays at five.

The startable frontier collapses into this: its top candidate becomes a move,
the rest is a count. Tickets found in flight are excluded from the frontier and
named in the position block with their age; one that has stalled past the
threshold becomes its own move — check on it or drop it.

Everything the current §9 says about writing for the owner rather than an
engineer, and about never letting a file path or line number reach the brief,
stands unchanged.

**A new prohibition:** the brief may not state that anything changed unless the
run observed it. With `recently_merged` present, changes are named from it.
Without it, the brief says the window is unknown.

## Part D — `/cabinet:now`

A new command for the gap between standups. It resolves the memory, takes a
board snapshot and a local session scan, and prints the position block, what is
in flight, and what has merged since the last standup. It dispatches no roles
and writes nothing — not to notebooks, not to the decision inbox, not to the
board. It closes by pointing at `/cabinet:standup` for moves.

It exists because the design is poll-at-command-time by choice, and the honest
answer to "how do I see a new workspace or a merged pull request right now" has
to be a command that costs seconds rather than a run that dispatches roles.

## Part E — the delivery lead

Step 6 of `agents/delivery-lead.md` ("Work out what is taken") gains the local
signal. When given a `sessions=` path it reads it, and a worktree with an
attributed ticket counts as taken alongside the existing remote signals. It
must say which signal it used. Local work whose ticket could not be attributed
is reported as unattributed work in progress, never assigned to a guess.

Its "Where your memory is" section gains `sessions=` to the list of paths it is
given and cannot derive.

## Testing

`local-sessions --self-test` builds a temporary repository with worktrees as
fixtures and asserts:

- attribution precedence: attachment beats branch name beats commit reference
- the never-guess rule: `fix/v2-parser` resolves to no ticket
- board cross-check: a branch-derived number absent from the board snapshot is
  rejected, and the rejected candidate is recorded
- a clean default-branch worktree is an idle checkout, not work in flight
- stall threshold arithmetic against `CABINET_STALL_HOURS`
- soft failure outside a git repository produces an empty result and exit 0

`board-snapshot --self-test` covers `--since` parsing and output path
construction without network access.

Both are wired into `.github/workflows/validate.yml` next to the existing
`harvest-transcripts` and `collect-metrics` self-tests.

## Files

| File | Change |
|---|---|
| `plugins/cabinet/scripts/local-sessions` | new |
| `plugins/cabinet/scripts/board-snapshot` | `--since`, `recently_merged`, `--self-test` |
| `plugins/cabinet/commands/standup.md` | §3 dispatch gains the scan; §9 rewritten |
| `plugins/cabinet/commands/now.md` | new |
| `plugins/cabinet/agents/delivery-lead.md` | step 6 and the memory-paths section |
| `plugins/cabinet/.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` | version bump only — neither manifest enumerates commands |
| `.github/workflows/validate.yml` | two self-test steps |
| `plugins/cabinet/FILES.md`, `plugins/cabinet/README.md` | document the script, the command, the brief shape |

## Out of scope

- Cross-machine detection. One machine is the current reality; the successor,
  when needed, is Cabinet's own record under `~/.cabinet`.
- Session hooks that push a claim when a session starts. Rejected: they see
  only Claude Code sessions, a crashed session leaves a claim that outlives the
  work, and a worktree whose hook did not install looks like nothing is
  happening — a silent failure worse than a poll being a few hours old.
- Any write to the board to mark a ticket taken.
- `/cabinet:review`'s report format.
