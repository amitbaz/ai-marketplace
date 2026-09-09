---
description: One-time setup for this repository — installs the tracker script, verifies it actually runs, orients in the repository's own documentation, and writes a project profile. Run once per repository, and again whenever conventions change.
argument-hint: "[no arguments]"
---

# /muster:setup

Run these steps in order. Report at the end, in the decisions-first shape
below — don't narrate each step as you go.

## 1. Install and verify the tracker script

- Create `.claude/coordination-state/` if it doesn't exist.
- If `.claude/coordination-state/tracker.sh` already exists, leave it alone
  — someone already wired up a tracker (possibly for a different forge) and
  this must not overwrite it. Skip to verification.
- Otherwise copy `"${CLAUDE_PLUGIN_ROOT}"/scripts/tracker.sh.github.example`
  to `.claude/coordination-state/tracker.sh` and make it executable.
  - If this repository has no GitHub remote, don't install the GitHub
    reference script — say plainly that it won't fit, and point at
    `STATE_FILE_SPEC.md`'s tracker contract (`list-tickets`, `get-ticket`,
    `list-prs`, `in-progress`) for writing one against the actual forge.
- **Verify by calling it**, not by assuming a copy succeeded: run
  `.claude/coordination-state/tracker.sh list-prs`. If it fails because
  `gh` is missing or unauthenticated, say exactly that and name the fix
  (`gh` install, or `gh auth login`) — don't guess at a different cause.

## 2. Orient in the repository's own knowledge

Read what's relevant to identify these, not to summarize what the code
currently does:

- Agent instruction files: `AGENTS.md`, `CLAUDE.md`, and any nested copies
  near areas that look load-bearing (not every subdirectory — use judgement
  on what's worth checking).
- A documentation directory if one exists (`docs/`, or whatever the repo
  calls it), and any architecture decision records or design-doc
  convention.
- Contribution and process conventions: branch naming, PR/commit
  conventions, how tests are run and what "done" requires.
- The tracker's actual label vocabulary — call
  `.claude/coordination-state/tracker.sh list-tickets` and note which
  labels appear and, where discoverable, what they seem to mean (e.g. an
  `in-progress` or equivalent label, a `blocked-by:#N` convention or its
  absence).

## 3. Write the project profile

Write `.claude/coordination-state/project-profile.md`. This file is
re-runnable — overwrite it completely each time `/muster:setup` runs, and
report what changed since the previous version if one existed. Never touch
any role's own state file (`delivery-lead.md`, `architect.md`,
`release-gate.md`, `product.md`) — those hold judgements, this command has
no business writing them.

**The profile is a map, not a snapshot.** Put this sentence at the top of
the file, verbatim, so whoever edits it next knows what belongs there:

> This is a map of where things live and what the conventions are — not a
> summary of what the code currently does. A summary goes stale within
> days and nobody re-reads it to check; a map of locations and rules stays
> useful because roles re-derive current behavior fresh every time they
> use it. If you're about to add "currently the system does X" to this
> file, it belongs in a role's own state file as a judgement, or nowhere.

Then record, as pointers and conventions only:

- Where documentation lives, and where architecture decision records live
  if they exist.
- What the tracker is (forge, and confirmation that `tracker.sh` is wired
  and verified working).
- The label vocabulary found in step 2 and what each label means.
- The branch-naming and contribution convention, in one line, with a
  pointer to the source document.
- How tests are run and what CI requires, in one line, with a pointer.
- **Generated at:** today's date, and **against commit:** the current
  `git rev-parse HEAD` (short form is fine). This is what lets a later
  reader say "this profile is from commit X, HEAD is now Y" instead of
  trusting it blindly — record it even though it will drift; the drift
  being visible is the point.

## 4. Report

Decisions-first, capped, one screen:

1. **Needs a decision** (max 5 lines) — anything that blocked full setup:
   `gh` unauthenticated, no GitHub remote, ambiguous documentation
   structure. Omit if nothing blocked.
2. What was installed / already present (tracker script — installed or
   left alone and why)
3. What the profile now records, one line per category, not the full
   content
4. What changed since the previous profile, if one existed
5. What could not be determined (no docs directory found, no ADR
   convention, tracker has no label vocabulary yet, etc.) — say this
   plainly rather than leaving it implicit
6. Next: run `/muster:wakeup`
