---
description: Show whether transcript capture is on for this project and what has been captured so far.
argument-hint: "[no arguments]"
---

Report the state of measurement in this project. Run both, in order:

1. `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts --status`
2. `"${CLAUDE_PLUGIN_ROOT}"/scripts/collect-metrics --summary`, but only if the first says something is stored.

Report what they print. Do not recompute any figure, and do not estimate anything the scripts did not measure.

If capture is off, say so first and plainly: nothing new is being captured, and any stored transcripts are from before it was switched off. Point at `/groundwork-metrics on`.

If nothing is stored at all, say that and stop. Do not run the collector against an empty store.

## Reading the roll-up out loud

Two points change how a reader interprets the numbers, so state them whenever you show a cost breakdown:

- Cost is split by token class and weighted by published price ratios, which the collector prints. Uncached input is routinely a rounding error, so a "token reduction" that only moves that number is worth nothing.
- Runs the collector could not place are reported as unattributed. They are counted, never guessed at, and never folded into a role's total.

For a full breakdown by role, with the caveats that belong to it, use `/groundwork-report`.
