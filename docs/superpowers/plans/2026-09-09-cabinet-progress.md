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
| F2 Transactional state | IMPLEMENTED | `da4675d` | 58 unit tests pass in `tests/cabinet/test_store.py` (unit_verified): frozen revisions, append-only events with UPDATE/DELETE triggers, lease fencing on process identity, idempotency conflicts, fault injection, backup/restore, non-destructive migration and atomic views. Review round 1 closed in `3049abe` (71 tests): assignment error code, a real threaded claim race with STORE_BUSY, an implicit process lease closing the lease-free write window, restore path containment, live current-batch selection. Deferred to O4: scope paths are checked textually only; resolving them against a repository checkout and refusing a symlink that leaves it needs the checkout O4 creates. Next: F3 owner approval and policy on top of this store |
| F3 Owner approval/policy | IMPLEMENTED | `1a46655` | 93 unit tests pass in `tests/cabinet/test_approval.py` and `tests/cabinet/test_policy.py`, 166 across the suite (unit_verified). `ApprovalService` builds the dialog from the stored batch body, records the digest, lease and pause state before asking, and rejects with SCOPE_CHANGED / LEASE_CHANGED / PAUSED when any of them moved during the wait. Only `action=accept` with `approve: true` creates a grant: a forged `approved` field, a string `"true"`, `1`, an owner-sounding message, decline, cancel, timeout, closed session and a missing capability all create none, and a pending request answers once. `Policy.authorize` classifies the kind against three closed sets before parsing the envelope or reading a record, so money, pricing, subscriptions, publication, comments, releases, deploys, pushes, repository and branch creation, workflow dispatch, GraphQL, arbitrary URLs and arbitrary shell commands are refused before an adapter could be selected; unknown kinds are refused too. Board maintenance runs on the setup grant, execution on a live grant for that exact revision and digest. Five mutation checks confirm the tests bite. Deferred: no MCP surface yet, so RESTRICTED_SESSION_REQUIRED and hook-synthesized elicitation responses are F4's; public-board prose refuses rather than preparing an artifact, which O3 owns. Next: F4 wraps ApprovalService behind the MCP elicitation dialog |
| F4 Service/restricted profiles | IMPLEMENTED | `f85ea0b`, `f9fedaa`, fix round 1 | 428 tests pass across the suite (unit_verified): 117 new in `tests/cabinet/test_rpc.py` (33) and `tests/cabinet/test_service.py` (84), on top of F4a's 121. The service exposes the 19 contract operations as `cabinet_*` tools with closed schemas; the ordinary plugin connection lists only the four read operations and refuses every writing name with `RESTRICTED_SESSION_REQUIRED`; `execute_action` runs `Policy.authorize` before it looks for an executor, so a forbidden kind fails with its F3 code rather than with `NOT_IMPLEMENTED_YET`. The protocol layer negotiates 2025-11-25 and 2025-06-18 with each version's elicitation shape, keeps the reader free of tool work, and matches dialog answers by request id: a mismatched or replayed response creates no grant. Six mutations confirm the tests bite. **Native smoke** in [`docs/cabinet/acceptance/f4-service-smoke.md`](../../cabinet/acceptance/f4-service-smoke.md): (a) supported — a scripted stdio client drove initialize/ping/list/call against the real `cabinet-service`, which resolved its identity from `git remote get-url origin`; (b) supported — `claude -p --mcp-config` listed and called `mcp__cabinet__cabinet_doctor`, and the first attempt was denied by the *permission* layer, not the tool layer; (c) supported — with the chief's exact `--tools` value the child held those seven built-ins and all four MCP tools, so **`--tools` does not gate MCP names** and `include_service_tools_in_tools_flag` stays False, settling F4a concern 1; (d) supported — `cabinet-launch --dry-run` printed the F4a argv verbatim with no capability anywhere in it; (e) **unsupported** — a `-p` session does not advertise form elicitation, so approval refuses with `ELICITATION_UNSUPPORTED` and records nothing, which also proves the restricted launch handshake worked (`launch: restricted`, lease taken at generation 2). **Owner-dialog gate: awaiting the owner.** One interactive session started through `cabinet-launch`, approving a synthetic batch, is the missing evidence; it was deliberately not simulated. **O1 obligation unchanged:** the packaged advisory agent files still contradict the staff tool set. **New for O1:** the chief profile's `permissions.defaultMode: "manual"` means every Cabinet tool call prompts; decide whether the profile allows those names — a real launch confirmed it, the chief answered `the tool permission for cabinet_doctor hasn't been granted in this session`. **Fix round 1** closed both Important findings. `wait_events` now hands the store's lock back between polls: a concurrent `cabinet_doctor` that waited 2.60 s during a 3 s wait now waits 0.00 s, under test. The launch record is bound rather than merely carried — the profile at `profile_path` is re-verified and its digest compared, the settings the session launches with must be the settings that profile describes, the service's parent process must be the process that wrote the record, and the record binds to the generation its session acquires. A launch that fails any of these serves read-only and `doctor` says which check failed. All three bindings are native_verified: a real `os.execve` launch reported `launch: restricted` and renewed the record to generation 1, and replaying that same record from an unrelated process was refused with `LAUNCH_HOST_MISMATCH` and degraded to 4 of 19 tools. That launch also found a defect no earlier probe could: the launcher's environment allowlist omitted `USER` and `LOGNAME`, without which Claude reports `Not logged in`. Next: O1 and O2 build on this surface |
| O1 Company staff | IN_PROGRESS | `fbd4087` | **O1a committed `fbd4087`; O1b (commands + live scenario) pending.** 444 tests pass, 16 new in `tests/cabinet/test_distribution.py` (unit_verified): all 15 structural assertions failed on the baseline for the reasons the brief named — no Product/Engineering/worker definitions, no handoff lifecycle in the skill, `## FOR <role>` as the only return channel, advisory tool lines carrying `mcp__github__*`/`WebSearch`/`WebFetch`. `SKILL.md` is now the single workflow entrypoint (350 lines) carrying the ten steps, the spec's authority table, the money invariant restated for the service, mandatory owner batch approval, the disagreement rule, the event-routing table and the `recorded → sent → acknowledged → resolved` lifecycle; the detail moved into `references/company.md`, `batch.md`, `communication.md`, `recovery.md` and `briefing.md`, each naming the task that extends it. Thirteen agent definitions: chief expanded to the operating remit, new `product`, `engineering`, `design`, `marketing`, `implementer`, `test-runner`, and `qa`/`delivery-lead`/`architect`/`brand`/`cfo`/`counsel` rewritten onto the registry tool line while keeping their standing questions and domain checklists. **Advisory-role tool reconciliation:** every staff `tools:` line now equals `STAFF_TOOLS + STAFF_SERVICE_TOOLS`; `mcp__github__*`, `WebSearch` and `WebFetch` are gone from architect, brand, cfo, counsel, delivery-lead and qa, so board and web evidence reach a role through the chief's service reads and the public views, and a role needing web research says so in its output for the chief to decide. `scripts/check-cabinet.py` is the mechanism: a local frontmatter parser (no YAML package) rejecting duplicate keys, unquoted colon-bearing values and malformed tool lists, plus registry equality, service-tool-name existence, skill step/event coverage, reference linkage, command skill loading and manifest/README agreement; `--self-test` proves seven negative fixtures fail. `python3 scripts/check-adapter-boundary.py` still passes. Owner-facing docs reconciled: `AGENTS.md` now states batch approval as the explicit exception to the one-way-door filter. Next: O1b writes `commands/company.md`, `commands/batch.md` and updates `hire.md`/`ask.md`, then runs the live read-only Product–Engineering scenario |
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
| Cross-session delivery, default | unsupported without recipient consent | The recipient held the message for its user and stayed blocked. Reproduced independently from the controller session. A launched worker cannot receive chief messages unattended |
| Cross-session delivery with `crossSessionInbound: "accept"` | supported | Passed via `--settings` (there is no launcher flag), the same restricted worker received the message with no hold and no prompt. `--restricted` ignores user/project/local settings but `--settings` still applies. **This belongs in F4's argv contract** |
| Subagent delivery into the parent session | supported | The parent confirmed `<agent-message from="…">` with the exact probe body. Replies route to the parent's main conversation, not to the sending subagent |
| Round trip to a completed subagent | supported | Sending to a finished subagent's id resumed it and its reply arrived back |
| Teammate name colliding with a cross-session peer name | unsupported — hazard | A bare name resolved to the peer socket, not the in-process teammate, and was then held. Namespace worker session names away from role names |
| `notify_when_idle` idle wake | supported (native_verified) | Probed from the main session, which a teammate cannot do. Subscribing with no message returned a subscription notice, and the peer's completion produced `[Cross-session idle notice] … is idle now`. **Caveat: it arrived across a permission-class difference, so either the "spawned by this session" clause applied or the class rule is looser than its wording. O2 must re-probe with a Superset-launched worker that is not a child process.** Only the chief, as the main session, can arm it |
| `claude -p` child delivering into the parent session | not_run | The nearest evidence used an in-process `Agent`-tool subagent, which addresses `main` differently from a cross-session peer. Not folded in |
| `ScheduleWakeup` timer | not_run | Tool name observed in a restricted child; schema not captured, never called |
| MCP elicitation, print mode | **unsupported** | F4b drove the real Cabinet server from `claude -p`: the client advertises no form elicitation, so `cabinet_request_owner_approval` refused with `ELICITATION_UNSUPPORTED` and created no grant and no pending request. **A print-mode session can never approve a batch; the chief must run interactively** |
| MCP elicitation, interactive | not_run — awaiting the owner | Needs one real owner answer in a dialog. Deliberately not simulated |
| Cabinet MCP server under `claude -p` | supported (native_verified) | `initialize`, `tools/list` and `tools/call` all worked over `--mcp-config` on 2.1.267; the tool result came back verbatim |
| `--tools` gates MCP tool names | **unsupported (they survive)** | With `--tools Read,Grep,Glob,Skill,Agent,SendMessage,ListAgents` a child held exactly those seven built-ins and all four `mcp__cabinet__*` names. F4a concern 1 settled: `include_service_tools_in_tools_flag` stays False |
| An MCP tool call needs a permission grant | supported | Without `--allowedTools` the print-mode child answered `I don't have permission to use the cabinet_doctor tool`. The chief profile's `manual` default mode therefore prompts per call |
| Restricted launch capability handshake | supported (native_verified) | A `claude -p` session started from `cabinet-launch`'s own MCP configuration reported `launch: restricted` and took the company lease under the launcher's session id |
| Launch bound to the launching process | supported (native_verified) | `cabinet-launch` execs Claude, which keeps the identifier and start time, so the spawned MCP server's parent **is** the process that wrote the record. A real launch reported `launch: restricted`; replaying the same record from an unrelated process was refused `LAUNCH_HOST_MISMATCH` and served 4 of 19 tools with `doctor` naming the failed check |
| Claude authenticates under an allowlisted environment | supported, with two required names | With only `PATH` and `HOME` a child answers `Not logged in · Please run /login`. Adding `USER` and `LOGNAME` is sufficient and was measured. They name the account, not the credential. **Any launcher that sanitizes the environment must carry them** |
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
  chief session; mutation requires the verified launcher context. **Resolved by
  F4b and native_verified**: the ordinary connection lists four read operations
  and refuses every writing name with `RESTRICTED_SESSION_REQUIRED`.
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
