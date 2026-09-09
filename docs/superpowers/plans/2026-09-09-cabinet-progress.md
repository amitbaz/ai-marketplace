# Cabinet implementation progress and evidence

Planning baseline: `cd52caf` on `codex/cabinet-company-design`.
PR preparation incorporated main at `e5b2598` (PR #28), including Cabinet 0.9.0,
the local-session reader and `/cabinet:now`. Preserve these improvements and
their tests; they do not complete any new operational acceptance gate by themselves.
This file is the cross-session execution checkpoint. Update it after each task;
link evidence rather than copying transcripts. It currently records planning
only. No new runtime, native team test or business pilot has been implemented.

| Task | State | Implementation commit | Verification and next action |
| --- | --- | --- | --- |
| F1 Capability contract | NOT_STARTED | — | Run actual native/Superset probes; Superset CLI was unavailable during planning |
| F2 Transactional state | NOT_STARTED | — | Implement journal, revisions, migration and recovery fixtures |
| F3 Owner approval/policy | NOT_STARTED | — | Implement and test frozen-revision owner consent |
| F4 Service/restricted profiles | NOT_STARTED | — | Implement protocol and verify actual isolation |
| O1 Company staff | NOT_STARTED | — | Replace advisory-only workflow and add missing roles |
| O2 Active handoffs | NOT_STARTED | — | Implement and prove sender/recipient communication |
| O3 GitHub ownership | NOT_STARTED | — | Scoped mutations and native relationship readback |
| O4 Workspace execution | NOT_STARTED | — | Automated isolated Superset launch and worker registration |
| O5 Independent verification | NOT_STARTED | — | Correction loop and integration evidence |
| A1 Recovery | NOT_STARTED | — | Cold session and interrupted external-operation recovery |
| A2 Briefs/steering | NOT_STARTED | — | Business-language lifecycle and pause/override |
| A3 Distribution | NOT_STARTED | — | Claude-only packaging; preserve Groundwork |
| A4 Full acceptance | NOT_STARTED | — | Synthetic proof, then separately approved Career Platform pilot |

Allowed states: NOT_STARTED, IN_PROGRESS, IMPLEMENTED, VERIFIED, BLOCKED.
VERIFIED must name the applicable level of proof. A blocked live gate does not
prevent independent implementation work; it does prevent the corresponding
operational claim. Keep blocked gate and offline task progress separate.

## Requirement evidence

R01–R18: all NOT_RUN. Populate one row per requirement from the master during
implementation; every row must reference its own evidence. Do not substitute a
single overall test count for this map.

## Known prerequisites and assumptions to verify

- Claude Code CLI reported 2.1.267 during planning; feature/permission behavior
  still needs native testing in F1/F4.
- Superset CLI was not found in this session. Owner expects to install it later.
- Superset automatic worktree setup must not execute outside the approved
  containment boundary; verify the actual project/CLI before creating workers.
- The ordinary plugin-loaded MCP service cannot assume it runs in a restricted
  chief session; mutation requires the verified launcher context.
- Native dialog hooks can synthesize responses; qualified profiles must exclude
  those hooks or approval is unavailable.
- Live GitHub fixture writes and a real Career Platform pilot need the owner's
  scoped authorization. Planning authorization supplies neither.

## Planning review

The planning review checked every R01–R18 requirement against its named tasks,
local document links, Python/JSON code-block syntax, task ordering, interface
names, and unresolved-placeholder phrases. It corrected the chief-role startup
dependency, added explicit Skill access/public-context paths, and closed the
generic-child/unrelated-recipient permission gaps in the proposed profile.

These are document checks, not implementation verification. Native compatibility,
isolation, MCP dialogs, Superset setup behavior, GitHub writes, recovery and the
actual business pilot remain unrun and are assigned to the executor's gates.

## Session handoff template

```text
Last completed task and evidence:
Current task / exact unfinished step:
Current branch and commit / unrelated local changes:
Capability blockers and work still possible:
Any contract changes and their justification:
Next action that moves R01–R18 forward:
```
