# Cabinet implementation progress and evidence

Planning baseline: `cd52caf` on `codex/cabinet-company-design`.
PR preparation incorporated main at `e5b2598` (PR #28), including Cabinet 0.9.0,
the local-session reader and `/cabinet:now`. Preserve these improvements and
their tests; they do not complete any new operational acceptance gate by themselves.
This file is the cross-session execution checkpoint. Update it after each task;
link evidence rather than copying transcripts. F1 has since measured the live
capability contract and fixed the distribution drift it exposed. No new runtime
and no business pilot has been implemented.

| Task | State | Implementation commit | Verification and next action |
| --- | --- | --- | --- |
| F1 Capability contract | IMPLEMENTED | `0d9fb97` | Probes run and recorded in [`docs/cabinet/acceptance/environment.md`](../../cabinet/acceptance/environment.md); README version drift fixed under a structural test. Next: F2, and re-probe idle wake from a main session |
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

F1 measured the items below on 2026-09-10. Full evidence, with the exact probe
per row, is in [`docs/cabinet/acceptance/environment.md`](../../cabinet/acceptance/environment.md).
A status here is `supported`, `unsupported` or `not_run`; `not_run` never means
"probably fine".

### Native probe status

| Probe | Status | Consequence |
| --- | --- | --- |
| Claude Code CLI 2.1.267 launcher flags | supported | `--restricted`, `--tools`, `--mcp-config`, `--strict-mcp-config`, `--settings`, `--plugin-dir`, `--add-dir`, `--session-id`, `--agent(s)` all exist under those names |
| `--tools` narrows the built-in tool set | supported | F4 keeps `--tools`; a child launched with `--tools Read` held exactly `Read` |
| `--allowedTools` narrows the tool set | unsupported | It is a permission allowlist only; a child launched with `--allowedTools Read` still held eleven tools including `Write`. Do not substitute it for `--tools` |
| `--max-turns` | unsupported | Absent in 2.1.267; bound child cost another way |
| Restricted child reaches a shell | unsupported (as intended) | A restricted child reported no shell execution tool |
| `CLAUDECODE` nesting guard | unsupported (none present) | `env -u CLAUDECODE` is not required to launch a child |
| `SendMessage` / `ListAgents` cross-session discovery | supported | A restricted child enumerated live sessions with name and busy/idle state |
| `ListAgents` inside a teammate session | unsupported | Not exposed to a teammate; a role that must discover peers cannot be a teammate-of-a-teammate |
| Named teammate spawned by a teammate | unsupported | Verbatim: the team roster is flat. O1/O2 cannot nest named roles |
| Cross-session delivery across permission-mode classes | unsupported by default | The recipient held the message for a human and stayed blocked. O2 must align permission-mode classes or set `crossSessionInbound` deliberately |
| `notify_when_idle` idle wake | not_run | Documented as main-conversation only; F1 ran as a teammate, and the machine's other idle sessions are unrelated owner work. O2 must probe this from a main session before claiming it |
| `ScheduleWakeup` timer | not_run | Tool name observed in a restricted child; schema not captured, never called |
| MCP elicitation | supported (from changelog, not exercised) | Available since 2.1.76; no Cabinet MCP server exists yet to exercise it |
| `Elicitation` / `ElicitationResult` hooks can override a response | supported — this is the risk | A qualified approval profile must exclude them |
| `PermissionRequest` hook present in user settings | supported — this is the risk | Present on this machine. `--restricted` ignores user, project and local settings, which removes it; managed settings and `--settings` still apply |
| A blocked session fabricates a dialog answer | unsupported (good) | The held-message recipient stopped and stayed `waiting blocked` rather than inventing consent |
| Superset CLI installed | supported | 1.27.0. It was absent during planning and is present now |
| Superset workspace and terminal command surface | supported | `workspaces create` and `terminals create/list/read/close` exist with the flags the plan assumed, plus `terminals send` |
| Superset authentication | unsupported | `superset auth whoami` exits 1, not logged in. **O4's blocking prerequisite, and an owner action** |
| `gh` CLI | supported | 2.100.0 |

### Assumptions still to verify

- Superset automatic worktree setup must not execute outside the approved
  containment boundary; verify the actual project/CLI before creating workers.
- The ordinary plugin-loaded MCP service cannot assume it runs in a restricted
  chief session; mutation requires the verified launcher context.
- Live GitHub fixture writes and a real Career Platform pilot need the owner's
  scoped authorization. Planning authorization supplies neither.
- `rtk` is a shell proxy on this machine only. It must never become a plugin
  prerequisite. Note that `rtk proxy` joins its arguments, so a multi-word
  subcommand must be quoted or it reports a false `Unknown command`.

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
