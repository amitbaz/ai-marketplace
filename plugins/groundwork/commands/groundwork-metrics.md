---
description: Turn subagent transcript capture on or off for this project, and report what the captured runs cost.
argument-hint: "[on | off | status | report]"
---

Run the plugin's measurement scripts and report what they say. `$ARGUMENTS` selects the action; treat an empty argument as `status`.

Capture is **off by default in every project**. The hooks that copy transcripts do nothing until someone turns capture on here, and turning it on is this command's job. Say so plainly if the user asks for a report while capture is off, because there will be nothing to report.

## Actions

| `$ARGUMENTS` | Do this |
| --- | --- |
| `on` | `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts --enable` |
| `off` | `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts --disable` |
| `status` or empty | `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts --status`, then `"${CLAUDE_PLUGIN_ROOT}"/scripts/collect-metrics --summary` if anything is stored |
| `report` | `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts` to sweep now, then `"${CLAUDE_PLUGIN_ROOT}"/scripts/collect-metrics --summary` |

Add `--anonymize` to the collector when the user intends to publish or commit the result: it aliases plan names and drops branch and session identifiers, keeping the per-run ids so every figure stays traceable. Write a file with `--out PATH` only when asked for one.

## What to tell the user

Report the numbers the scripts print. Do not recompute them, and do not estimate anything the scripts did not measure.

Two things are worth stating whenever you show a cost breakdown, because a reader who misses them draws the wrong conclusion:

- Cost is split by token class and weighted by published price ratios, which the collector prints. Uncached input is routinely a rounding error, so a "token reduction" that only moves that number is worth nothing.
- Runs the collector could not place are reported as unattributed. They are counted, never guessed at, and never quietly folded into a role's total.

If the user asks what a number means or what to do about it, answer from the report at `docs/measurements/` in this repository when one applies. Do not invent a recommendation the measurements do not support.

## Turning capture on

Explain what it does before enabling it, unless the user has clearly already decided:

- Whole transcripts of this project's subagent runs are copied into `.groundwork/transcripts/`, which ignores itself so it cannot be committed by accident.
- Copies are kept for 90 days, capped at 1 GiB, oldest dropped first.
- Nothing leaves the machine.
- `off` stops it; `--purge` on the harvester deletes what was already stored.
