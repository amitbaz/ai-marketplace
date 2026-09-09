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

**It remembers decisions, not conversations.** Every role here is a fresh
subagent dispatch — no session survives between runs. But that's not the
same as having no memory: continuity comes from an explicit, written
decision trail (see *The state files* below), and that's a better memory
than a conversation transcript would be anyway. A transcript is long,
carries abandoned reasoning next to conclusions, and nobody re-reads it. A
person actually doing this job doesn't recall yesterday's meeting
word-for-word either — they carry what was decided and why. That's what
the state file holds, and it's read in full on every run, so what looks
like a role "just knowing things" is a role that read its notes.

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

Each is read-only by tool grant, not just by instruction — see below. Each
also orients in your project's own documentation before touching the
tracker — `AGENTS.md`/`CLAUDE.md`, contribution rules, architecture decision
records, whatever's relevant to that role's function — read fresh every
run, never cached into the state file, for the same reason the tracker
itself is re-derived rather than trusted from a note. If a ticket
contradicts what the docs say, that's reported as a finding, not quietly
resolved either way.

## `/muster:setup` and `/muster:wakeup`

Two commands, run at different times:

- **`/muster:setup`** — once per repository, and again whenever
  conventions change. Installs and verifies the tracker script, orients in
  the repository's own documentation, and writes a project profile: where
  things live and what the conventions are, not a summary of what the code
  currently does. That profile records the commit it was written against,
  so a later run can tell whether it's gone stale rather than trusting it
  blindly.
- **`/muster:wakeup`** — at the start of every working session. Reads the
  project profile and every role's state file first — the actual memory —
  then re-derives live state from the tracker and reports what happened,
  what needs a decision, and what contradicts what was believed last time.
  It is deliberately not just a fresh tracker listing with a friendlier
  name: a report only from the tracker would be exactly the "no memory"
  framing this plugin exists to avoid. Reading the memory first, then
  checking it against what's true right now, is the whole point.

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

Writing nothing is a correct outcome, not a failure to write. A role that
checks a ticket and finds it still matches the tree has nothing worth
keeping — the tree already answers that question, so a note would just be
a fact restated. Don't read an empty state-file update as the role having
"done less" than one that wrote three judgements; it did exactly as much
work and correctly decided none of it needed to survive to next time.

## Platform support

**Claude Code**: all four roles, `/muster:setup`, `/muster:wakeup`, and the
`coordination-rules` skill.

**Codex**: the `coordination-rules` skill only — Codex's plugin manifest
here declares `"skills": "./skills/"` and nothing else, the same pattern
Groundwork uses in this marketplace. Commands and agent definitions are
Claude Code constructs; there's no Codex equivalent shipped yet, so a
Codex install of Muster today gets the background coordination rules and
none of the roles or commands. Said plainly rather than papered over — if
you're on Codex, this plugin isn't yet doing its main job for you.

## Setup

Run `/muster:setup` once per repository. It installs the tracker script,
verifies it actually runs, orients in your repository's own documentation,
and writes a project profile. Run it again any time your conventions
change — it's re-runnable and won't touch any role's own notes.

Then run `/muster:wakeup` at the start of a working session.

**Using a forge other than GitHub?** `/muster:setup` will tell you the
bundled `scripts/tracker.sh.github.example` won't fit if there's no GitHub
remote. Write a script at `.claude/coordination-state/tracker.sh`
implementing the same four commands (`list-tickets`, `get-ticket`,
`list-prs`, `in-progress`) against your tracker's API — see
`STATE_FILE_SPEC.md` for the exact contract. Nothing in the role files or
commands changes; `/muster:setup` will detect and verify it the same way.

## Licence

MIT — see `LICENSE`.
