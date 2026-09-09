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
| Cross-session **delivery** to a restricted recipient | **unsupported under a permission-mode mismatch** | `claude logs <id>` on the recipient | The recipient **held** the message rather than acting on it: `Held peer message — from uds:/tmp/cc-socks/<pid>.sock [verified pid <pid>] … not delivered to Claude (1 held). The sending session's permission mode class doesn't match this session's. Review it below, or set "crossSessionInbound" to "accept".` The recipient's status stayed `waiting blocked` across six polls. Transport is a per-pid Unix domain socket with a verified pid; the body arrives wrapped as `<agent-message from=…>`. **O2 must either match permission-mode classes between chief and staff or set `crossSessionInbound`; a bypass-mode chief messaging a restricted role is held for a human by default.** |
| Reply routing from a subagent | supported, with a caveat | live send; changelog 2.1.248 | The send result states that a reply is delivered to the parent session's main conversation, not to the sending subagent. Confirmed by the tool result text. A Cabinet role that sends must not expect the answer itself. |
| `notify_when_idle` idle wake | not_run | — | The parameter exists on `SendMessage` and was introduced in 2.1.236, but it is documented as usable **from the main conversation only**, and this task ran as a teammate. Not exercised. The only other idle sessions on this machine belong to the owner's unrelated work and were deliberately not messaged. **O2 must run this probe from a main session before claiming idle wake.** |
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
3. **O2's messaging design has a real gate.** Sending works; delivery to a
   recipient in a different permission-mode class is held for a human. Decide
   the permission-mode class of chief and staff together, or set
   `crossSessionInbound` deliberately and say so in the contract.
4. **O1/O2 cannot nest named roles.** A teammate cannot spawn a named teammate.
5. **O4 is prerequisite-blocked, not design-blocked.** The command surface is
   present and matches the plan. Only authentication is missing.
6. **Idle wake is unproven.** It must be probed from a main session before any
   task claims it.
