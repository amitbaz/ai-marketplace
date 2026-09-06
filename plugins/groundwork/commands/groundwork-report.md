---
description: Sweep for new subagent transcripts and report what the captured runs cost, by role.
argument-hint: "[--anonymize] [--out PATH]"
---

Produce a cost breakdown from the captured transcripts. Pass any flags in `$ARGUMENTS` through to the collector.

1. `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts` — sweep now, so runs that finished since the last capture are included.
2. `"${CLAUDE_PLUGIN_ROOT}"/scripts/collect-metrics --summary` — the roll-up.

Use `--anonymize` whenever the user intends to publish, commit, or share the result: it aliases plan names and drops branch and session identifiers, keeping the per-run ids so every figure stays traceable to a row. Offer it if they have not asked and the destination looks public. Write a file with `--out PATH` only when a file was asked for, and use `--anonymize` alongside it for anything entering version control.

If capture is off, the sweep still works — running this command is itself the user's consent for that one sweep — but say that ongoing capture is off and that runs finishing later will be missed unless they turn it on.

## Reporting the numbers

Report what the scripts print. Do not recompute, and do not estimate anything they did not measure.

State these alongside any cost breakdown, because a reader who misses them draws the wrong conclusion:

- Cost is split by token class and weighted by published price ratios, which the collector prints. Uncached input is routinely a rounding error, so a "token reduction" that only moves that number is worth nothing.
- Runs the collector could not place are reported as unattributed. They are counted, never guessed at, and never folded into a role's total.
- A handful of executions on one machine is a data point, not a distribution. Say what the sample does not cover before drawing a conclusion from it.

If the user asks what a figure means or what to do about it, answer from the measurement write-ups under `docs/measurements/` in this repository when one applies. Do not invent a recommendation the measurements do not support.
