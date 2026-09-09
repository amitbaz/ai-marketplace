# State file spec

Every role in this plugin is a stateless dispatch: a fresh context every run,
no memory of the last one unless the host's `autoMemoryEnabled` setting
happens to be on (not guaranteed, never assumed). The state file is how a
role avoids re-deciding what it already decided.

## Location

`.claude/coordination-state/<role>.md` — plain markdown, checked into the
repo. Portable, diffable, readable without this plugin installed.

## What goes in it

Judgements and reasoning the tracker cannot answer. Not facts the tracker
already holds.

| Belongs in the file | Belongs in the tracker (re-derive, never cache) |
|---|---|
| Why a proposal was rejected, and what evidence would change that | Ticket status, assignee, labels |
| A decision that was reversed, and the reasoning for both the old and new position | Blocking/blocked-by edges |
| A claim's confidence downgraded/upgraded, and the named condition | Open PR list, CI/check status |
| A note that a ticket's spec predates a merge and is now wrong in a specific way | Anything a single tracker query answers today |

Rule of thumb: if the tracker can answer it fresh, re-deriving is safer than
trusting a note — a stale note is worse than no note. The file exists only
for what would otherwise be lost.

## Format

Free-form markdown, one entry per judgement, newest first:

```markdown
## 2026-09-09 — pricing: weekly vs. monthly reversed back to weekly
Reasoning: monthly was chosen 09-05 to match [competitor], reversed because
[reason]. Weekly reinstated because [reason]. If [named condition changes],
revisit.

## 2026-09-08 — name "X" rejected
Collision with [competitor in same market]. Do not re-propose unless
[condition].
```

No fixed schema beyond a date and a one-line header per entry — this is a
decision log, not a database row.

## Failure modes, handled explicitly

- **File missing or empty**: the role says so in its output — "no prior
  notes, this is a cold read" — and proceeds by deriving everything fresh
  from the tracker. Missing-file and nothing-to-report are different states
  and the role must say which one it's in. Never treat silence as "all
  clear."
- **File present but stale** (older than the tracker state it references,
  or referencing a ticket/PR that no longer exists): flagged, not
  discarded and not silently trusted. Surface the mismatch to the reader.
- **File disagrees with the tracker on a fact** (ticket says closed, note
  implies still open; a decision the note describes was later reversed by
  someone who didn't update the file): **the tracker wins on facts, the
  file wins on reasoning, and the contradiction is reported rather than
  silently resolved.** A role that quietly picks one side manufactures a
  confident wrong answer — the exact failure this design exists to avoid.

## Who writes it

The role itself, at the end of its run, appending new judgements. Roles
never delete history — superseded entries stay, marked superseded, so the
graveyard (rejected names, reversed decisions) stays intact and searchable
by a later run.

## Pluggable tracker contract

Nothing in a role prompt calls a specific forge's CLI. Each role reads
state through a small contract the host project implements once, as
`.claude/coordination-state/tracker.sh <command> [args]`:

- `list-tickets` — id, title, status, blocking/blocked-by edges
- `get-ticket <id>` — detail
- `list-prs` — open PRs/MRs with check status
- `in-progress <id>` — required concept, not optional: whether an agent has
  *confirmed* it is working the ticket, distinct from merely assigned.
  "Assigned" and "an agent is actually working on it" look identical in
  most trackers and conflating them causes a ticket to sit dispatched and
  untouched while being reported as in flight. If the host tracker has no
  such concept (most strangers' setups won't), `tracker.sh` returns
  "unsupported" and roles fall back to unblocked-and-unassigned as a
  weaker signal, and say so.
`tracker.sh` is read-only by design — none of this plugin's four roles
write to the tracker, so the reference implementation has no write
subcommand at all. This is deliberate: the tool grant
`Bash(.claude/coordination-state/tracker.sh *)` is a wildcard over
subcommands, so a write path behind that same grant would defeat the
read-only guarantee the wildcard is supposed to provide — any subcommand
the script accepts, a role holding the grant can call. A future role that
genuinely needs to write (comment, set a field) belongs behind a separate
script (e.g. `tracker-write.sh`) with its own, separately granted, tool
entry — never folded into the read path.

Roles are given tool access to `tracker.sh` only, not general shell —
read-only is enforced by the tool grant plus the script having nothing to
write with, not just stated in the prompt. Reference implementation: a
thin wrapper script over `gh` for GitHub. A different forge needs only a
new script satisfying the same contract — nothing in `agents/*.md`
changes.
