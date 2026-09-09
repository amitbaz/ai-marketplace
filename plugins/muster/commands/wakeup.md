---
description: Catch up at the start of a working session — read the project profile and every role's state file, re-derive live state from the tracker, and report what happened, what needs a decision, and what contradicts what was believed last time.
argument-hint: "[no arguments]"
---

# /muster:wakeup

This is not a fresh status listing built only from the tracker — that
would just be a report with a friendlier name. This command reads memory
first, then checks it against what's true right now. Run these in order.

## 1. Read the project profile

Read `.claude/coordination-state/project-profile.md`. If it doesn't exist,
say so plainly and stop after suggesting `/muster:setup` — don't improvise
a picture without it, and don't silently fall back to guessing where docs
or the tracker live.

If it exists, check its recorded commit against the repository's current
`HEAD`. If they differ, say so in the report — the profile may describe
conventions that have since moved, and the reader should know that before
trusting it, not discover it later.

## 2. Read every role's state file

Read everything under `.claude/coordination-state/*.md` except
`tracker.sh` and `project-profile.md` itself — `delivery-lead.md`,
`architect.md`, `release-gate.md`, `product.md`, whichever exist. Pull
every open "needs a decision" item. This is the genuine memory read: what
was decided, rejected, or flagged last time, not re-derived from the
tracker.

If none of these exist, that's normal and not a setup problem — those
files are written by the roles themselves the first time each one runs,
not by `/muster:setup`. Say plainly that no role has left notes yet; don't
suggest re-running `/muster:setup`, which wouldn't create them.

## 3. Re-derive live state from the tracker

Using the profile's pointers (not blind guessing), run the literal
commands `.claude/coordination-state/tracker.sh list-tickets` and
`.claude/coordination-state/tracker.sh list-prs`. Do not call `gh`,
`glab`, or any other tracker CLI directly, and don't report `tracker.sh`
as missing without actually running it at that path first. Check each
open item's `in-progress` state via
`.claude/coordination-state/tracker.sh in-progress <id>` where relevant.
Never trust a state file for anything the tracker can answer fresh — the
state files hold judgements, not current facts.

## 4. Read what the profile points at, as needed

If a state file or the tracker raises something that touches documentation
the profile pointed at (a ticket that might contradict an architecture
decision record, a question about a testing convention) — read that
specific document now, using the profile's pointer. Don't re-read
everything the profile mentions on every run; read what's relevant to what
came up.

## 5. Report contradictions

Two kinds, both reported rather than silently resolved:

- **State file vs. tracker**: a note describes something the tracker no
  longer confirms. Tracker wins on facts, the note wins on reasoning —
  report the mismatch either way.
- **Ticket/PR vs. documentation**: something a ticket or PR claims
  contradicts what an architecture decision record or doc says. This is a
  real finding, not noise — surface it.

## 6. Build the report — decisions first, one screen total

1. **Needs a decision** (max 5 lines) — aggregated from every role's state
   file plus anything this run found. Omit if empty.
2. What happened / changed since the state files' last entries
3. Startable frontier — unblocked and not in-progress. "In progress" means
   confirmed by `tracker.sh in-progress <id>`, not merely assigned — those
   look identical in most trackers, and conflating them is how a ticket
   sits untouched while reported as in flight. If the tracker has no such
   concept, say that plainly and fall back to unblocked-and-unassigned.
4. Blocked — what, and on what
5. Open PRs and check status
6. Any contradiction found this run (state/tracker, ticket/docs, or a
   stale profile commit)

Detail is available on request — don't volunteer full ticket bodies, full
PR diffs, or the full contents of any state file or the profile. Name
counts, offer to expand.
