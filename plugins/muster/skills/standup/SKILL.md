---
description: Reconstruct the current picture on demand — open PRs and check status, the startable frontier, what's blocked and on what, what's waiting on a decision. Rebuilds from live tracker state every time, never from memory or a prior conversation. Use for "what's the state of things," "what can start," "what's blocking X," or a standup-style check-in.
allowed-tools: Bash(.claude/coordination-state/tracker.sh *), Read
---

# /standup

This is deliberately not the same thing as summarizing recent chat
activity into yesterday/today/blockers — that's a different, adjacent
tool for a different question ("what did I do"). This skill answers "what
is true right now," rebuilt from the tracker every run. Never draw from
this conversation's memory of a previous standup; a stale mental model
presented confidently is worse than no model.

## Gather (live, every run — no caching across invocations)

!`.claude/coordination-state/tracker.sh list-tickets 2>&1 || echo "tracker.sh not found or errored — see fallback below"`

!`.claude/coordination-state/tracker.sh list-prs 2>&1`

## If tracker.sh is missing or errors

Say so plainly — do not fabricate a picture from what the conversation
happens to remember. Suggest running the delivery-lead and release-gate
agents directly, or wiring up `.claude/coordination-state/tracker.sh`
per `STATE_FILE_SPEC.md`.

## Build the report — decisions first, one screen total

1. **Needs a decision** (max 5 lines) — pull from any role's state file
   under `.claude/coordination-state/*.md` that has an open "needs a
   decision" item newer than the last time this was run. Omit if empty.
2. Startable frontier — unblocked and not in-progress (see
   `STATE_FILE_SPEC.md` for what in-progress means and its fallback)
3. Blocked — what, and on what
4. Open PRs and check status
5. What's waiting on the person running this, beyond section 1

Detail is available on request — do not volunteer full ticket bodies, full
PR diffs, or the full contents of any role's state file. Name counts,
offer to expand.
