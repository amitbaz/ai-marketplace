---
description: Turn subagent transcript capture on or off for this project.
argument-hint: "[on | off]"
---

Switch transcript capture for this project. `$ARGUMENTS` is `on` or `off`; ask which if it is empty rather than assuming.

| `$ARGUMENTS` | Run |
| --- | --- |
| `on` | `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts --enable` |
| `off` | `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts --disable` |

Capture is off in every project until this command turns it on. The hooks that copy transcripts exit immediately while it is off, creating no directory and writing no file.

To see what is currently captured, use `/groundwork-stats`. To produce a cost breakdown, use `/groundwork-report`.

## Before enabling it

Explain what the user is agreeing to, unless they have clearly already decided:

- Whole transcripts of this project's subagent runs are copied into `.groundwork/transcripts/`. That directory and its parent both ignore themselves, so nothing written there can be committed by accident.
- Copies are kept for 90 days, capped at 1 GiB, oldest dropped first.
- Nothing leaves the machine.
- The switch is per project. Enabling it here enables nothing anywhere else.

## After disabling it

Turning capture off stops new copies; it does not delete what was already stored. Say so, and mention that `"${CLAUDE_PLUGIN_ROOT}"/scripts/harvest-transcripts --purge` deletes the stored copies if that is what the user wants.
