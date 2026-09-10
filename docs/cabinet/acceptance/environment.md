# Cabinet capability contract — measured environment

Recorded by task F1 on 2026-09-10, on the owner's macOS machine (Darwin 25.6.0,
arm64), from worktree `codex/cabinet-company-design` at baseline commit `05b9bc3`
with a clean tree. The planning baseline was `cd52caf`; `main` was merged at
`e5b2598` (PR #28), and the only intervening commits are documentation.

**This file is the contract.** Tasks F4, O2 and O4 must use the tool, flag and
field names recorded here verbatim. A version number is not evidence: every row
marked `supported` was executed, and every row that was not executed says
`not_run` with the reason.

Three conventions:

- **Status** is `supported`, `unsupported`, or `not_run`. `not_run` never means
  "probably fine".
- **Evidence** is sanitized. No authentication output, tokens, account
  identifiers, or other sessions' names appear here.
- `rtk` is a token-saving shell proxy installed on this machine only. It is
  developer tooling and **must never become a plugin prerequisite**. Probes below
  are recorded as the plain command actually run.

## Toolchain

| Capability | Status | Version | Probe | Evidence |
| --- | --- | --- | --- | --- |
| Claude Code CLI | supported | 2.1.267 | `claude --version` | `2.1.267 (Claude Code)`, resolved at `~/.superset/bin/claude` |
| Superset CLI | supported | 1.27.0 | `superset --version` | `1.27.0`, resolved at `~/.superset/bin/superset`. It was absent when the plan was written; it is present now. |
| GitHub CLI | supported | 2.100.0 | `gh --version` | `gh version 2.100.0 (2026-09-03)` |
| `rtk` proxy | supported | n/a | `which rtk` | `/opt/homebrew/bin/rtk`, wired as a `PreToolUse` hook. Developer tooling; not a prerequisite. `rtk proxy` joins its arguments, so a multi-word subcommand must be quoted or it reports a false `Unknown command`. |

## Claude Code launcher flags

Every flag below was read from `claude --help` on 2.1.267. The rows marked
*executed* were additionally run.

| Capability | Status | Probe | Evidence |
| --- | --- | --- | --- |
| `--restricted` | supported (executed) | `claude --help` | Removes the built-in command- and code-running tools and `WebFetch` unless `--tools` names them; ignores user, project and local settings files; confines file tools to the working directories; refuses `bypassPermissions`. Also available as `CLAUDE_CODE_RESTRICTED=1`. Introduced 2.1.248. |
| `--tools <tools...>` | supported (executed) | see *Restricted child sessions* | **This is the tool-set restrictor F4 needs, and it does exist under that name.** Names built-in tools; `""` disables all, `default` enables all. |
| `--allowedTools` / `--allowed-tools` | supported | `claude --help` | A *permission* allowlist accepting patterns such as `Bash(git *)`. **It does not narrow the tool set** — see the probe below where a child launched with `--allowedTools Read` still held eleven tools. Do not use it where F4 means `--tools`. |
| `--disallowedTools` / `--disallowed-tools` | supported | `claude --help` | Present. Runtime behaviour not separately executed. |
| `--mcp-config <configs...>` | supported | `claude --help` | Space-separated JSON files or strings. |
| `--strict-mcp-config` | supported (executed) | used in every child probe | Only MCP servers from `--mcp-config`; ignores all other MCP configuration. |
| `--settings <file-or-json>` | supported | `claude --help` | Still applies under `--restricted`, together with managed settings. |
| `--setting-sources <sources>` | supported | `claude --help` | Comma-separated `user,project,local`. |
| `--plugin-dir <path>` | supported | `claude --help` | Repeatable; a directory or `.zip`; a folder of plugins loads each child. |
| `--add-dir <directories...>` | supported | `claude --help` | Additional tool-accessible directories; included in the restricted-mode confinement. |
| `--session-id <uuid>` | supported | `claude --help` | Must be a valid UUID. |
| `--agent <agent>` / `--agents <json>` | supported | `claude --help` | `--agents` takes an inline JSON object of custom agents. |
| `--permission-mode <mode>` | supported | `claude --help` | Choices: `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan`. |
| `--permission-prompts <target>` | supported | `claude --help` | `host` or `none`; `none` denies anything that would prompt. |
| `--output-format <format>` | supported (executed) | every child probe | `text`, `json`, `stream-json`. |
| `--bg` / `--background` | supported (executed) | `claude --bg --name … ` | Returns a short id for `claude attach|logs|stop|rm`. |
| `--max-turns` | **unsupported** | `grep -- '--max-turns'` over `claude --help` | Absent in 2.1.267. Bound child cost with `--max-budget-usd` or a small prompt instead. |

## Restricted child sessions

Run from a synthetic scratch directory, non-interactive, with
`--strict-mcp-config`.

| Capability | Status | Probe | Evidence |
| --- | --- | --- | --- |
| Nesting guard on `CLAUDECODE` | unsupported (no guard) | same probe with and without `env -u CLAUDECODE` | `CLAUDECODE=1` was set in the parent. The child ran and returned `is_error: false` either way. **`env -u CLAUDECODE` is not required on 2.1.267.** |
| `--allowedTools` narrows the tool set | **unsupported** | `claude -p --restricted --strict-mcp-config --allowedTools Read --output-format json "List every tool you can call, names only"` | Child answered: `Agent, Edit, Glob, Grep, ListAgents, Read, ScheduleWakeup, Skill, ToolSearch, Write, ReportFindings`. Write and Edit survived. |
| `--tools` narrows the tool set | supported | same command with `--tools Read` | Child answered exactly `Read`. One turn, no permission denials. |
| Restricted child cannot reach a shell | supported | `claude -p --restricted --strict-mcp-config --output-format json "Run the shell command … or reply NO_SHELL_TOOL"` | Child answered `No shell execution tool is available to me in this session.` then `NO_SHELL_TOOL`. |
| Restricted mode ignores user/project/local settings | supported | `claude --help`, changelog 2.1.248 | This is the mechanism that excludes the owner's `PermissionRequest` hook from a staff session. See *Owner dialogs* below. |

## Native team and messaging tools

Schemas below are the ones this installed version actually supplied to a running
session, captured with `ToolSearch` and from the live tool listing. Field names
are verbatim. There is no `TeamCreate` or `TeamDelete`, and no private socket
protocol is used by Cabinet.

| Capability | Status | Probe | Evidence |
| --- | --- | --- | --- |
| `Agent` tool parameters | supported | live tool listing | `description`, `prompt`, `subagent_type`, `name`, `model` (`sonnet`\|`opus`\|`haiku`\|`fable`), `isolation` (`worktree`\|`remote`). `team_name` and `mode` are present but documented as deprecated and ignored. `subagent_type: "fork"` inherits the parent context and ignores `model`. |
| `SendMessage` tool parameters | supported (executed) | `ToolSearch("select:SendMessage")` | `to` (required), `message` (required; string or a `shutdown_request`/`shutdown_response`/`plan_approval_response` object carrying `type`, `request_id`, `approve`, `reason`, `feedback`), `summary`, `notify_when_idle`. |
| `SendMessage` success result fields | supported (executed) | live send | `success`, `message`, `msg_id`. Resuming an existing agent instead returns `success`, `message`, `resumedAgentId`, and `pin` with `id`, `name`, `ref`. |
| `ListAgents` in a *teammate* session | **unsupported** | `ToolSearch("select:ListAgents")`, then a keyword search | Not exposed to this teammate session and not resolvable through `ToolSearch`. `SendMessage` documents `ListAgents` as the discovery mechanism, so a Cabinet role that must discover peers cannot be a teammate-of-a-teammate. |
| `ListAgents` in a restricted child session | supported | `claude -p --restricted --strict-mcp-config --tools ListAgents --output-format json "Call ListAgents once…"` | A freshly launched restricted child enumerated three live sessions on this machine, each row carrying a name and a busy/idle state. Peer names are redacted here. |
| Session registry from the shell | supported | `claude agents --json` | Three rows; keys `cwd`, `kind`, `name`, `pid`, `sessionId`, `startedAt`, `status` (plus `state` when done). Same population `ListAgents` reported. |
| Spawning a **named** teammate from a teammate | **unsupported** | `Agent(name: "f1-probe", …)` | Verbatim error: `Teammates cannot spawn other teammates — the team roster is flat. To spawn a subagent instead, omit the name parameter.` Cabinet's operating team therefore cannot be a tree of named roles spawned by a role; naming must come from a main session. **Blocker to design around in O1/O2.** |
| Cross-session send to a named local session | supported (executed) | `SendMessage(to: "f1-idle-probe", …)` to a `--bg` session started for this probe | Accepted with `success: true` and an `msg_id`. The result named the recipient as another Claude session on this machine. |
| Cross-session **delivery**, default | **unsupported without recipient consent** | `claude logs <id>` on the recipient | The recipient **held** the message rather than acting on it: `Held peer message — from uds:/tmp/cc-socks/<pid>.sock [verified pid <pid>] … not delivered to Claude (1 held). The sending session's permission mode class doesn't match this session's. Review it below, or set "crossSessionInbound" to "accept".` The recipient's status stayed `waiting blocked` across six polls. Transport is a per-pid Unix domain socket with a verified pid; the body arrives wrapped as `<agent-message from=…>`. Independently reproduced from the controller session, which received `[Cross-session delivery notice] Your message to another session was held for the recipient user's approval … Not delivered to that session's Claude yet; its user must approve first.` **A launched worker cannot receive chief messages unattended by default.** |
| Cross-session **delivery** with `crossSessionInbound: "accept"` | **supported (executed — this is the mechanism O2/O4 need)** | `claude --bg --name … --restricted --strict-mcp-config --tools Read --settings '{"crossSessionInbound":"accept"}' "…"`, then `SendMessage` to it, then `claude logs <id>` | Delivered with no hold and no approval prompt. The recipient's transcript shows `Message from @<sender-session>: <agent-message from="impl-F1">` and it answered `INBOUND-DELIVERED`, then went idle. The log contains no `Held peer message` and no `approval`. The identical launch **without** the setting was held, so the setting is the difference. There is **no launcher flag** for this — `claude --help` has no `crossSessionInbound`, `inbound` or `peer` option — so it must be passed as settings. `--restricted` ignores user, project and local settings but **`--settings` still applies**, which is exactly why this works for a restricted worker. |
| Subagent → parent-session delivery | supported (executed, confirmed by the recipient) | an **in-process `Agent`-tool subagent** called `SendMessage(to: "main", …)` | The parent session confirmed receiving `<agent-message from="aa3fd74e12b29d52e">PROBE-TOKEN-8F31C</agent-message>`. It landed in the parent's main conversation, not in the spawning teammate's. The `from` attribute carries the sender's agent name or teammate name; the peer address shown to a human is the **parent session's** name. |
| `claude -p` child → parent session delivery | not_run | — | The row above is the closest evidence, but its sender was an in-process `Agent`-tool subagent, **not** a `claude -p` child process. The two use different addressing (`to: "main"` versus a cross-session peer name), so the `-p` case is not covered by it and is recorded here unrun rather than folded in. |
| Round trip to a completed subagent | supported (executed) | `SendMessage(to: "<agentId>", …)` to a finished subagent | The send resumed the agent (`resumedAgentId`, `pin{id,name,ref}`) and its reply `PROBE-ACK-8F31C` arrived back in this teammate's conversation. Resuming a finished subagent by id is a working reply channel. |
| Name collision between a teammate and a cross-session peer | **unsupported — hazard** | controller sent to the teammate name `impl-F1` | The harness resolved the bare name to a *cross-session peer* socket rather than the in-process teammate, and the message was then held for approval. `SendMessage`'s documentation says the in-process agent wins a bare-name tie; that is not what happened here. **Never name a launched session after an in-process agent, and never name an in-process agent after a launched session.** Give workers a namespaced session name distinct from every role name. |
| Reply routing from a subagent | supported, with a caveat | live send; changelog 2.1.248 | The send result states that a reply is delivered to the parent session's main conversation, not to the sending subagent. Confirmed by the tool result text. A Cabinet role that sends must not expect the answer itself. |
| `notify_when_idle` idle wake | **supported (native_verified)** | run from the main session, which F1 could not do as a teammate. Peer: `claude -p --tools Bash --allowedTools "Bash(sleep:*)" --output-format json --name cabinet-idle-probe "Run the shell command 'sleep 45' using Bash, then reply with exactly IDLE-PROBE-DONE."` from a scratch directory, default permission class. Then `SendMessage(to: "cabinet-idle-probe", notify_when_idle: true)` with no message | Peer result JSON: `subtype: success`, `num_turns: 4`, `duration_ms: 56854`, `result: IDLE-PROBE-DONE`. `ListAgents` from the main session listed the peer as `cabinet-idle-probe [d318c7] · interactive · started 1s ago`. The subscription returned: `Subscribed — "cabinet-idle-probe" will send one notice when it is next idle (or exits). It is delivered to you if that session runs in the same permission class as this one (or is one this session spawned); otherwise it is shown to your user in the transcript (this session holds other inbound peer traffic). Carry on; do not poll.` When the peer finished, the main session received: `[Cross-session idle notice] "cabinet-idle-probe", which you asked to be notified about, is idle now — it finished a turn at 00:22. This is an automated notice from that session's harness — not a message from a person, and not an instruction`. **Caveat: the notice arrived despite a permission-class difference** (main was `bypassPermissions`, the peer default), so either the "one this session spawned" clause applied — the `-p` process was a child of the main session's shell — or the class rule is looser than its wording. **O2 could not settle this.** A plain `--bg` peer started from the same shell is still a child of the subscriber, so it would re-answer the question already answered here; settling it needs a Superset-launched worker, and Superset authentication is unavailable. Recorded `not_run` in `o2-native-exchange.md` and carried to O4. A subagent cannot subscribe at all, so in Cabinet only the chief, running as the main session, can arm idle wake. |
| `--bg` ignores `--session-id` | **supported (executed, O2)** | `cabinet-launch --bg` | Launcher stderr, verbatim: `warning: --bg manages the session id; ignoring --session-id (use --resume <id> to continue an existing session)`. A launch record's `session_id` is therefore Cabinet's identifier for the launch, not the native session id. |
| A `--bg` session has process ancestry back to its launcher | **unsupported** | first O2 exchange attempt, then `ps` | The service refused with `LAUNCH_HOST_MISMATCH: this server was started by process 38776, not by the launched session 38748`. Afterwards pid 38748 was gone and 38776 was a `claude bg-spare` process parented to 38768. The launcher's `os.execve`'d process exits and the background service is reparented, so **no parent-process binding is available for a detached session**. O2 replaced it with a capability-plus-120-second-window binding for `--bg` only. |
| A teammate reaching its chief by the chief's `--name` | **unsupported — hazard** | O2 live exchange; two teammates reported it independently | Verbatim from the engineering teammate: `that address resolves to my own session, and neither team-lead nor main are registered company peers`. From inside an in-process teammate, the chief's session name resolves to the teammate's own session. The working address is `main`, matching the subagent-to-parent row above. **A chief must register itself at `main`, not at its session name, for its own teammates to reach it.** |
| A chief in `defaultMode: manual` with an explicit `permissions.allow` | **supported (executed, O2)** | O2 live exchange | Sixteen `mcp__cabinet__*` calls, three `Agent` dispatches and repeated `SendMessage` calls ran with no permission prompt and no stall. Without the allowlist, manual mode prompts per call, which was F4b's open concern. |
| `--agent <plugin>:<name>` with `--plugin-dir` | supported, with a misleading warning | O2 live exchange | Launcher stderr said `warning: no agent named 'cabinet:chief-of-staff' — spawning with default template`, but the session header showed `@cabinet:chief-of-staff` and the chief loaded its packaged skill. The warning appears before plugin agents resolve. Recorded as observed, not explained. |
| One-shot wake timer | not_run | tool name observed only | A restricted child listed a `ScheduleWakeup` tool. Its schema was not captured and it was not called. |

## Owner dialogs and approval integrity

| Capability | Status | Probe | Evidence |
| --- | --- | --- | --- |
| MCP elicitation (structured input mid-task) | supported | installed changelog | Added in 2.1.76: MCP servers can request structured input through an interactive dialog (form fields or browser URL). Later entries fix elicitation form rendering and `elicitation/create` in print/SDK mode, so the feature is live rather than announced. Not exercised by F1; no Cabinet MCP server exists yet. |
| `Elicitation` / `ElicitationResult` hooks can override a response | supported — and this is the risk | installed changelog | Added in 2.1.76 to "intercept and override responses before they're sent back". A profile that must obtain genuine owner consent has to exclude these hooks. |
| Hooks configured on this machine | supported (inspected) | read `~/.claude/settings.json` keys only | User settings define `PermissionRequest`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `SessionStart`, `SessionEnd`, `Stop`, `StopFailure`, `SubagentStart`, `SubagentStop`, `UserPromptSubmit`. **A `PermissionRequest` hook is present**, so an unqualified session on this machine can have permission dialogs answered without the owner. No `Elicitation` hook is currently configured. No project `.claude/settings.json` or `.claude/settings.local.json` exists in this worktree, and no managed policy file exists at either standard path. |
| Mitigation for the hook risk | supported | `claude --help` | `--restricted` ignores user, project and local settings files, which is what removes the owner's `PermissionRequest` hook from a staff session. Managed settings and `--settings` still apply, so a managed policy file could reintroduce a hook. |
| No fabricated response to an owner dialog | supported | `claude logs <id>` on the held-message session | The recipient did not invent an answer. It stopped at the dialog and stayed `waiting blocked` until the session was stopped. |

## Superset workspaces

Command surface verified from `--help`. The plan's assumed names are correct;
an earlier apparent mismatch was the `rtk proxy` argument-joining artifact noted
above, not a missing command.

| Capability | Status | Probe | Evidence |
| --- | --- | --- | --- |
| `superset workspaces create` (alias `ws`) | supported (help verified) | `superset workspaces create --help` | Options: `--host`, `--local`, `--project`, `--name`, `--branch`, `--pr`, `--task`, `--base-branch`, `--skip-branch-prefix`, `--agent`, `--prompt`, `--model`, `--effort`, `--command`, `--attachment`, `--tag`. `--prompt` is required when `--agent` is set. `--agent` takes a preset id such as `claude`. |
| `superset terminals create` | supported (help verified) | `superset terminals create --help` | Options: `--workspace`, `--host`, `--command`, `--cwd`. |
| `superset terminals list` | supported (help verified) | `superset terminals list --help` | Options: `--workspace`, `--host`. |
| `superset terminals read` | supported (help verified) | `superset terminals read --help` | Options: `--workspace`, `--host`, `--terminal`, `--max-lines`. |
| `superset terminals close` | supported (help verified) | `superset terminals close --help` | Options: `--workspace`, `--host`, `--terminal`. |
| `superset terminals send` | supported (help verified) | `superset terminals --help` | Exists in addition to the four the plan named: sends a follow-up message to a terminal already running in a workspace. O4 needs it to steer a worker. |
| Global output control | supported | `superset --help` | `--json` (auto-on under CI/agent environments), `--quiet` (ids only), `--api-key` or `SUPERSET_API_KEY`. |
| Superset **authentication** | **unsupported at runtime** | `superset auth whoami --json` | Exit status 1. The failure class, with no account content, is `Error: Not logged in` and a hint to run `superset auth login` or set `SUPERSET_API_KEY`. `superset status` fails identically. **No workspace, terminal or host call can succeed until the owner authenticates. This is O4's prerequisite, and it is an owner action — do not attempt it, and do not treat the installed CLI as a working one.** |

## What this changes in the plan

1. **F4 may keep `--tools`.** The flag exists under that name and is the only
   one of the two that actually narrows the tool set. Rewrite any F4 argv that
   used `--allowedTools` for that purpose.
2. **F4 has no `--max-turns`.** Bound child cost another way.
3. **O2's messaging design has a real gate, and a verified way through it.**
   Sending works, but delivery into an independent session is held for that
   session's user by default. The launcher must start every worker with
   `--settings '{"crossSessionInbound":"accept"}'`, which is executed and
   working above. There is no flag for it, and it is a deliberate consent
   decision: write it into F4's argv contract rather than leaving it implicit.
4. **O1/O2 cannot nest named roles.** A teammate cannot spawn a named teammate.
   Separately, worker session names must not collide with in-process role names,
   because a bare name resolved to the cross-session peer rather than the
   in-process agent. Namespace worker session names.
5. **O4 is prerequisite-blocked, not design-blocked.** The command surface is
   present and matches the plan. Only authentication is missing.
6. **Idle wake works, and only the chief can arm it.** A subagent cannot
   subscribe, so the chief must be the main session. The notice crossed a
   permission-class boundary that its own wording says it might not, and the
   peer was a child process of the subscriber's shell. O2 tried and could not
   settle it: a plain `--bg` peer is still a child of the shell that started
   it, and the Superset-launched worker that would settle it needs
   authentication the machine does not have. Carried to O4.

## Addendum 2026-09-10 — interactive client elicitation capability (native_verified)

Probe: a `claude --bg --model haiku --strict-mcp-config --mcp-config <capture>` session
against a capture MCP server that records the client's `initialize` params. Observed:

```json
{"protocolVersion": "2025-11-25",
 "capabilities": {"roots": {"listChanged": true}, "elicitation": {}},
 "clientInfo": {"name": "claude-code", "version": "2.1.267"}}
```

Claude Code 2.1.267 declares `"elicitation": {}` (no `form`/`url` sub-keys) while
negotiating 2025-11-25. The service originally required `form` under that version and
refused the owner's first interactive dialog attempt with `ELICITATION_UNSUPPORTED`;
the empty object is now accepted as the backwards-compatible form declaration.
Print mode (`-p`) still advertises no elicitation at all.
