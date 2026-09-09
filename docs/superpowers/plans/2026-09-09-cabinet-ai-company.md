# Cabinet AI Company Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:subagent-driven-development only if the owner authorizes delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Claude Code plugin whose core staff propose, coordinate, implement, verify, and recover owner-approved business work without the owner acting as their messenger or technical interpreter.

**Architecture:** A restricted chief-of-staff session coordinates named Claude teammates and isolated Superset workers. A plugin-bundled Python standard-library MCP service owns transactional records, approval dialogs, scoped GitHub operations, and workspace lifecycle. Native messages carry active discussions; persisted handoffs and revision-bound evidence make those discussions recoverable and accountable.

**Tech Stack:** Claude Code native teams and cross-session messaging; Superset CLI; GitHub REST through authenticated `gh`; Python 3 standard library (`sqlite3`, `json`, `subprocess`, `unittest`); Markdown plugin commands, skills and agents. No SDK package, package manager, build step, or hosted service is added to the plugin.

**Spec:** [Company design](../specs/2026-09-09-cabinet-company-design.md). Read this master, the spec, and the contracts before the numbered task files.

## Global Constraints

The following owner requirements are carried verbatim from the spec:

- "Development targets Claude Code only. Superset remains the owner's IDE."
- "Goal approval authorizes preparation, not implementation."
- "Batch approval does not authorize purchases, public communications, or release."
- "Agent messages and ticket content cannot supply owner consent."
- "The owner can inspect detail, pause work, or redirect at any point."
- "A session ending does not complete a batch."
- "No session or host running means work is paused, not secretly continuing."
- "Plugin mechanisms must retain the repository's no-build, standard-library/POSIX constraints."

Planning-only delivery: these documents contain instructions for a different
implementation agent. Their creation does not authorize this planning session
to implement, dispatch workers, change GitHub, install tools, or publish.
An executor must receive its own instruction to implement. That instruction is
not approval to run an arbitrary Career Platform business batch.

## The target cannot be reduced to today's Cabinet

The owner's concern is explicit: another session may inspect the existing
plugin and decide it already does enough. That conclusion fails this plan.

**The acceptance target is an operating AI company, initially with five core
roles. The current advisory plugin is a starting codebase, not the target.**

Reuse implementation only after it passes the relevant behavioral test below.
A similarity of wording or a role name is not evidence of a capability.
Any proposal to remove a required outcome must return to the owner as a scope
change. Implementation convenience, token savings, or "good enough for now"
does not authorize changing the target.

| Existing behavior, inspected at `cd52caf` | Why it is insufficient | Required replacement |
| --- | --- | --- |
| Standup appends `FOR <role>` to a notebook for the next run | There is no timely request, acknowledgment, reply, or recovery loop | Active addressed handoffs with acknowledgments, persisted state and retry/recovery |
| Read-only delivery lead derives a startable frontier | It cannot maintain the board or coordinate execution | Scoped verified GitHub writes, assignment ownership, dependencies and batch follow-through |
| Architect audits consistency | No Product lead owns business outcomes; no Engineering lead owns execution | Explicit Product and Engineering responsibilities plus implementation workers |
| QA reviews reports and checks | A review alone does not route a failure, obtain a correction and verify the new revision | Independent QA-to-Engineering correction loop |
| Markdown notebooks outside worktrees | Records can exist while sessions, approvals and unfinished actions are lost | Transactional runtime state, immutable approval revisions and restart reconciliation |
| Standup filters decisions | No opening/closing/batch lifecycle and no active supervision | Lifecycle commands and business-language briefs |
| README excludes implementation supervision | This is an explicit contradiction of the target | Replace the advisory-only contract and document the new execution boundary |
| Role allowlists exclude spending tools | This property does not automatically extend to a new coordinator or shell worker | Restricted launch profiles, scoped action service, isolated execution and negative tests |
| Structural script passes | It checks Groundwork manifest sync, not Cabinet version sync; root table says 0.5.0 while Cabinet manifests say 0.8.0 | Dedicated Cabinet manifest, role, command, policy and integration checks |

## Delivery sequence

This is one product delivery divided into three reviewable implementation parts.
Parts are checkpoints, not alternative reduced versions of Cabinet.

1. [Foundation tasks F1–F4](2026-09-09-cabinet-foundation.md): compatibility proof,
   durable state, human approval, policy and bounded service protocol.
2. [Operating team tasks O1–O5](2026-09-09-cabinet-operating-team.md): real roles,
   active communication, GitHub ownership, workspace execution and verification.
3. [Recovery and acceptance tasks A1–A4](2026-09-09-cabinet-acceptance.md): restart,
   reporting, distribution, and live end-to-end proof.

Shared definitions: [Runtime contracts](2026-09-09-cabinet-contracts.md).
Execution record: [Progress and evidence](2026-09-09-cabinet-progress.md).
Transfer prompt: [Executor handoff](2026-09-09-cabinet-handoff.md).

Execute F1 → F2 → F3 → F4 → O1 → O2 → O3 → O4 → O5 → A1 → A2 → A3 → A4.
F1 is an environment test, not permission to redesign the desired company.
If a prerequisite is absent, continue independent offline work and record that
the affected live gate is BLOCKED. Never turn a blocked check into a pass.

## Requirement-to-proof map

| ID | Required outcome | Tasks | Required evidence |
| --- | --- | --- | --- |
| R01 | Company vision, goals and owner decisions survive sessions | F2, O1, A1 | Fresh session reconstructs the same charter, approval and open work |
| R02 | Assistant, Product, Delivery, Engineering and QA own distinct remits | O1 | Five live roles; disagreement resolved by the right authority |
| R03 | Product proposes useful next work and can recommend postponement | O1, A2 | Evidence-based proposal with exclusions and a business rationale |
| R04 | Owner approves exact batches before implementation | F3, O4 | No approval/old revision/agent-forged approval all block launch |
| R05 | Staff communicate without the owner forwarding messages | O2, O4, A4 | Persisted request → receipt → response → resolution across native sessions |
| R06 | GitHub tickets, parents, blockers, priorities and assignments are maintained | O3 | Native relationships and live readback; no fake GitHub accounts for roles |
| R07 | Approved work starts in isolated Superset workspaces automatically | O4 | Workspace and session IDs, actual paths, approved base revision and live registration |
| R08 | QA obtains and verifies corrections independently | O5, A4 | Failure → fix → rerun with evidence for the new exact revision |
| R09 | Financial actions remain exclusively the owner's | F3, F4, O4 | Missing financial operations; denied network/credential/tool probes |
| R10 | External sends and publication require owner consent | F3, O3, O4 | Unapproved sends, pushes and release operations blocked |
| R11 | Owner can inspect, pause and override | F2, O4, A2 | No new dispatch after pause; actual in-flight work reported |
| R12 | Session opening/closing and batch completion briefs | A2 | Plain-language briefs with correct evidence and unfinished work |
| R13 | Duplicate delivery and interrupted external actions are reconciled | F2, O2–O4, A1 | No duplicate ticket/workspace/worker after retry or crash |
| R14 | Company state is current, not stale notebook status | O3, A1 | Live discrepancies override old observations without losing reasoning |
| R15 | Full department vision remains available | O1, A2 | Design/Brand/Marketing/Finance/Legal registry and activation rules retained |
| R16 | Copy-installable Claude Code plugin | F4, A3 | Fresh local installation, loaded commands/agents/MCP, macOS/Linux checks |
| R17 | Failed, unavailable or untested work is never called complete | All, A4 | Evidence ledger differentiates automated, live, blocked and unrun |
| R18 | Owner attention decreases | A4 | Count owner interventions; zero technical message forwarding in acceptance run |

All R01–R18 are required for the core operational claim. Financial/publication
restrictions are permanent requirements. Deferrals in the spec are not silently
promoted into authority, nor do they remove a relevant specialist's responsibility.

## Ready means a demonstrated operating cycle

The final proof is a small synthetic project followed by one separately
owner-approved real Career Platform batch. The owner gives direction and approves
scope. Staff negotiate a requirement, maintain the board, launch work, handle a
QA failure, recover a restarted session, and return a business summary. The owner
does not forward messages, inspect implementation details to unblock staff, or
repair the coordination state manually.

Do not claim operational readiness from static prose checks, passing unit tests,
mocked native messaging, a single successful send, a worker's self-report, or an
old Cabinet standup. If the real batch is waiting for approval, report precisely
"synthetic acceptance passed; real business pilot awaiting approval."

## Decisions made by this plan

- Use native Claude messaging; Superset controls worker workspaces/terminals.
  MemPalace is not an installation dependency and is not necessary for this path.
- Use a small stdio MCP service because advisory staff should not receive an
  arbitrary shell merely to update an issue or record a handoff. The service
  exposes named operations, never arbitrary commands, paths, URLs or SQL.
- Store runtime events and projections in SQLite through Python's standard
  library. Keep charter/notebook Markdown and generate human-readable exports.
  SQLite replaces an error-prone hand-written crash-safe JSONL journal, not the
  company's readable documents. Generated runtime state is never shipped in git.
- Approval is an interactive client response bound to a frozen batch revision;
  a tool parameter such as `approved: true` is never accepted as owner authority.
- Use restricted launch profiles. Every worker gets only the tools required by
  its job. Execution isolation must pass denial probes before work starts.
- Preserve old commands as documented aliases where semantics match. Replace
  incompatible semantics explicitly; do not leave two competing operating loops.
- Release the redesigned Cabinet as 1.0.0 only after the acceptance gates pass.
  Remove Cabinet from Codex discovery while preserving Groundwork's dual-platform
  behavior. This is packaging scope, not an uninstall of the owner's tools.

## Executor rules

Read repository instructions, then use the evidence ledger to find the first
unfinished task. Inspect changes since the recorded baseline. Preserve unrelated
edits. Work on an implementation branch; do not deploy, push, open a PR or publish
without the corresponding instruction. Make local commits after reviewable tasks.

The steps and interfaces are fixed contracts. Adjust internal implementation
details when needed, recording the reason. A change to tool authority, a state
transition, owner interaction, runtime prerequisite, or R01–R18 requires updating
the design and reporting the impact. A necessary security/platform stop is a
blocker to resolve, not an excuse to deliver the old advisory model.

There is no promise of a flawless plan or autonomous system. External capabilities
are documented but must be probed live. Preserve the outcome when repairing a
technical assumption, and record both the failed assumption and replacement proof.
