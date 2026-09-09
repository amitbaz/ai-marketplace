# Muster

A muster is the roll call — who's present, who's missing, what's ready. This
plugin does that for someone running several Claude Code (or Codex) sessions
who cannot read all of them.

## What this is

If you run implementation and QA work in separate agent sessions — separate
worktrees, separate terminals, separate workspaces you open yourself — you
end up reconstructing the picture by hand: what's open, what's blocked, what
changed, what needs your decision. Muster does that reconstruction for you,
every time, read-only, from your issue tracker and pull requests.

## What this is not

**It does not manage your implementation or QA agents.** No dispatch, no
supervision loop, no worker DAG. It's deliberately the layer above that, not
a replacement for it — keeping implementation and QA in sessions you run
yourself is a design choice this plugin assumes, not a limitation it's
working around.

**It does not remember your last conversation.** Every role here is a fresh
subagent dispatch with no memory of the last time it ran. What looks like
continuity comes entirely from state files it reads and writes on disk (see
below), never from anything held in a session. A role that pretended
otherwise would be telling you it knows something it doesn't.

## The roles (Claude Code)

- **delivery-lead** — the board: the startable frontier (unblocked and not
  already in progress), what's blocked and on what, open PRs and their
  checks.
- **architect** — checks whether a ticket's description of the system still
  matches the tree; catches specs that went stale after a merge.
- **release-gate** — checks whether "done" actually holds: a green check
  that's green for the wrong reason (skipped tests, mocked dependencies, a
  required check that doesn't actually gate) is what it looks for.
- **product** — holds the decision trail for naming, pricing and
  positioning: what was proposed, what was rejected and why, and checks new
  proposals against that record before anyone re-evaluates from zero.

Each is read-only by tool grant, not just by instruction — see below.

## `/muster`

Rebuilds the current picture from your tracker on every run: decisions that
need you, the startable frontier, what's blocked, open PRs. It does not
summarize recent chat activity — that's a different, adjacent question
("what did I do"). This one answers "what's true right now."

## Why the tool grant matters more than the role prompt

Every role is granted exactly `Read, Grep, Glob,
Bash(.claude/coordination-state/tracker.sh *)` — nothing else. That grant
*is* the tracker contract: a role can't reach around it even with a
misleading prompt, because permissions are enforced at the tool layer, not
the instruction layer. The reference `tracker.sh` has no write subcommand at
all, for the same reason — a write path behind that wildcard grant would
quietly defeat the read-only guarantee the grant is supposed to provide. A
role that ever needs to write back belongs behind a separate script with its
own, separately granted, tool entry — never folded into this one.

## The state files

Each role reads `.claude/coordination-state/<role>.md` before doing
anything and writes to it after. These hold only what the tracker can't
answer fresh — judgements, rejected proposals, reversed decisions and why —
never facts the tracker already knows (status, assignee, blocking edges get
re-derived every run; a stale copy of a derivable fact is worse than no
copy). A missing or empty file is a normal first-run state — the role says
"cold read" and proceeds, distinct from "checked and found nothing." See
`STATE_FILE_SPEC.md` for the full spec, including what happens when a state
file and the tracker disagree: the tracker wins on facts, the file wins on
reasoning, and the disagreement is reported, never silently resolved.

One example worth calling out: the reference `tracker.sh`'s `in-progress`
check distinguishes "assigned" from "an agent confirmed it's actually
working this," because those look identical in most trackers and conflating
them is how a ticket sits untouched while being reported as in flight. If
your tracker has no equivalent concept, `tracker.sh` says so explicitly
(`unsupported`) instead of guessing, and the calling role falls back to a
weaker signal and says that too.

## Platform support

**Claude Code**: all four roles plus `/muster` and both skills.

**Codex**: the two skills (`muster:standup`-equivalent and
`coordination-rules`) only — Codex's plugin manifest here declares
`"skills": "./skills/"` and nothing else, the same pattern Groundwork uses
in this marketplace. The four roles are defined as Claude Code subagents
(`agents/*.md`, a Claude-specific construct); there is no Codex agent
equivalent shipped yet. If you're on Codex, you get the tracker-reading
skill content but not the four standing roles.

## Setup

1. Install the plugin.
2. Copy `scripts/tracker.sh.github.example` to
   `.claude/coordination-state/tracker.sh` in your repo and `chmod +x` it.
   It wraps `gh` — install and authenticate the GitHub CLI first
   (`gh auth login`); the script fails loudly, not silently, if that's
   missing.
3. Using a different forge? Write a script at the same path implementing
   the same four commands (`list-tickets`, `get-ticket`, `list-prs`,
   `in-progress`) against your tracker's API. Nothing in the role files
   changes.
4. Run `/muster`, or invoke any role directly, to check it's wired up.

## Licence

MIT — see `LICENSE`.
