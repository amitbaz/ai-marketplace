# groundwork

Groundwork is a cross-platform extension/wrapper for [`obra/superpowers`](https://github.com/obra/superpowers). It adds parallel read-only reconnaissance before Superpowers' discussion and planning workflow.

Groundwork supports **Claude Code** and **OpenAI Codex** with native packaging for each platform.

> **Required dependency:** Superpowers must be installed for the platform you are using. Groundwork does not bundle or replace it, and the workflow stops if the required Superpowers skills are unavailable.

## Usage

| Platform | Invocation |
| --- | --- |
| Claude Code | `/groundwork <problem>` |
| Codex | `$groundwork <problem>` |

Example:

```text
$groundwork Investigate why the customers table in dashboard does not scroll.
```

The workflow has three phases:

1. **Phase 1 — Deep research.** Dispatches only the reconnaissance threads relevant to the problem. Independent threads run in parallel and are read-only. **Phase 1 is a hard gate:** nothing downstream starts until every dispatched thread has returned or has been explicitly accounted for as failed.
2. **Phase 2 — Discuss & brainstorm.** Invokes Superpowers' `brainstorming` skill, explains the evidence in plain language, restates the goal, compares approaches, surfaces gray areas, and gets user alignment.
3. **Phase 3 — Plan.** Starts only after the user greenlights the approach. Invokes Superpowers' `writing-plans` skill and produces a structured, verifiable implementation plan before any code is written.

Groundwork ends after planning. The accepted plan is handed to Superpowers' `subagent-driven-development` or `executing-plans` workflow for implementation.

## Installation

### Claude Code

Install Superpowers first:

```text
/plugin install superpowers@claude-plugins-official
```

Add this marketplace and install Groundwork:

```text
/plugin marketplace add amitbaz/ai-marketplace
/plugin install groundwork@amitbaz
```

### Codex CLI

Install Superpowers from the official Codex plugin marketplace first:

```text
/plugins
```

Search for **Superpowers** and select **Install Plugin**.

Then add this marketplace and install Groundwork:

```text
codex plugin marketplace add amitbaz/ai-marketplace --ref main
codex plugin add groundwork@amitbaz
```

To refresh the Git-backed marketplace later:

```text
codex plugin marketplace upgrade amitbaz
```

### Codex app / workspace

For the Codex app, install **Superpowers** from the Plugins sidebar first. A workspace admin can import `https://github.com/amitbaz/ai-marketplace` from **Workspace settings → Plugins → Marketplaces**; Codex reads `.agents/plugins/marketplace.json` from the repository.

## Superpowers dependency

Superpowers is part of Groundwork's workflow contract, not an optional enhancement.

Groundwork requires the `brainstorming` and `writing-plans` skills before it starts. If they are unavailable, Groundwork stops and tells the user to install Superpowers instead of silently substituting another skill or continuing with a reduced workflow.

Groundwork does **not** need to invoke `using-superpowers` itself. Installing Superpowers is the prerequisite; Groundwork invokes the specific skills required at its phase boundaries.

## Platform architecture

Groundwork is built as **one shared workflow contract plus thin platform adapters**.

### Canonical shared skill — the single source of truth

`skills/groundwork/SKILL.md` owns every platform-neutral behavior:

- the three-phase workflow and the phase entry conditions;
- reconnaissance intent, roles, task-packet quality bar, and report shapes;
- the Phase 1 hard gate;
- the Superpowers dependency gate and the `brainstorming` / `writing-plans` handoffs;
- the requirement for explicit user approval before planning;
- stop-before-implementation and the execution handoff;
- the built-in engineering discipline and the general workflow rules.

No other file in the plugin restates this contract. If an adapter and the skill disagree about *what* Groundwork does, the skill wins; the adapter only decides *how* recon threads are spawned on that platform.

A structural check enforces this: `python3 scripts/check-adapter-boundary.py` (run in CI) fails when an adapter reintroduces workflow sections, workflow-owned phrases, or passages copied from the canonical skill.

### Claude Code adapter

Claude uses:

- `.claude-plugin/plugin.json` for plugin metadata;
- `commands/groundwork.md` for `/groundwork` — a thin adapter that invokes the canonical skill (`groundwork:groundwork`) first and then adds only Claude-specific concerns: `$ARGUMENTS`, `Agent(...)` dispatch syntax, the `groundwork:recon-*` subagent types and their colors, `AskUserQuestion` usage, and Claude's Superpowers install wording;
- three custom read-only recon agents under `agents/`;
- Claude's agent/subagent primitives to dispatch those recon agents in parallel.

The three Claude recon agents remain color-coded in the UI:

| Agent | Color | Covers |
| --- | --- | --- |
| `groundwork:recon-code` | cyan | Inside the repo — named files, callers/callees, tests, sibling patterns |
| `groundwork:recon-external` | orange | Outside it — current docs, issues/MRs/PRs/pipelines, linked URLs |
| `groundwork:recon-context` | green | Prior thinking — plans, architecture/decision docs, project memory, git history |

### Codex adapter

Codex uses:

- `.codex-plugin/plugin.json` for plugin metadata, pointing at `./skills/`;
- `skills/groundwork/SKILL.md` directly for `$groundwork` — Codex consumes the canonical skill with no separate adapter file;
- native Codex subagents for Phase 1 reconnaissance, described by the skill's platform-neutral dispatch model.

Codex does not depend on Claude's `Agent(...)`, `subagent_type`, `$ARGUMENTS`, or `AskUserQuestion` primitives. The skill gives each native subagent a self-contained read-only role packet for code recon, external recon, or prior-context recon, and requires the orchestrator to account for every dispatched subagent before Phase 2 begins.

The semantic roles are the same across platforms even though their UI and orchestration primitives differ.

## Phase 1 — reconnaissance

Groundwork chooses threads from the evidence actually needed by the problem rather than spawning every possible scout.

Typical threads include:

- read named files completely;
- map callers, callees, sibling patterns, and tests;
- verify current library/framework/API documentation;
- read linked issues, PRs/MRs, pipelines, or URLs;
- search prior project decisions and remembered constraints;
- scan plans, architecture docs, ADRs, and git history.

Every scout is read-only and returns evidence rather than recommendations. Code findings cite `file:line`; external findings cite links/IDs/versions; prior-context findings are dated and marked as still true, stale, or unverified where practical.

### The Phase 1 gate

Recon is a barrier, not a stream. Groundwork does not start brainstorming from whichever scout happens to answer first.

Until every dispatched scout is accounted for, Groundwork does **not**:

- invoke `brainstorming`;
- summarize partial findings as a conclusion;
- recommend an approach;
- ask design questions that depend on missing recon;
- write an implementation plan.

If a scout fails, Groundwork either retries that focused thread or explicitly records the missing evidence before moving on. It never silently drops a dispatched thread.

## Phase 2 — discussion and brainstorming

Once the Phase 1 gate opens, Groundwork invokes Superpowers' `brainstorming` skill before converging on a design.

The discussion is written for a competent developer who has not read the researched code. Internal names are explained on first use and file paths/links appear as receipts rather than forcing the reader to reconstruct the explanation from source files.

Groundwork covers:

1. what the research established;
2. the problem in plain language;
3. the goal as now understood;
4. viable approaches and their tradeoffs;
5. gray areas and what changes depending on each answer;
6. only the focused questions that evidence cannot resolve.

No implementation code or implementation plan is written in Phase 2. Groundwork waits for user alignment.

## Phase 3 — implementation plan

After the user explicitly accepts the direction, Groundwork invokes Superpowers' `writing-plans` skill and produces a concrete plan with observable verification steps.

Groundwork then stops. It does not silently turn the planning workflow into an implementation workflow.

## Built-in engineering discipline

Groundwork applies its own engineering discipline automatically while converging on an approach and writing the final plan. There is no separate Karpathy flag or Karpathy skill dependency.

The discipline keeps the result grounded in four principles:

- **Make uncertainty visible** — distinguish verified facts from assumptions and surface decisions that genuinely need user input.
- **Prefer the smallest complete solution** — solve the researched problem without speculative features, abstractions, or configurability.
- **Keep the change boundary tight** — every planned modification should trace directly to the agreed goal; unrelated cleanup stays out of scope.
- **Plan around observable outcomes** — meaningful steps include a concrete way to verify that the intended behavior was achieved.

These constraints deliberately apply during convergence and planning, not as a reason to narrow Phase 1 research before the problem is understood.

## Subagent transcript harvest (Claude Code only)

Claude Code writes a separate JSONL transcript for every subagent it dispatches, carrying the agent id, the parent session id, the model used on each turn, and a full token-usage block with its cache splits. It is the only source that can attribute cost to one specific dispatch — the parent session transcript does not contain subagent turns, and Claude Code's OpenTelemetry metrics do not identify which dispatch spent what.

Those transcripts live under a per-user temp root and are deleted within roughly three days. Capture therefore has to happen while the session is warm; nothing can be recovered afterwards.

Groundwork ships a capture step for them, and nothing more. Parsing the records and computing cost is deliberately not part of it.

### What runs, and when

`hooks/hooks.json` registers `scripts/harvest-transcripts` on two events, which overlap on purpose:

| Event | Purpose |
| --- | --- |
| `SubagentStop` | Copy transcripts as soon as a dispatch ends, while the source file certainly still exists. |
| `SessionStart` | Sweep for anything a previous session left behind — including sessions that were killed before their stop hook could run. |

Each run is a full sweep rather than a lookup of one file, because the path cannot be derived from a session id. Measured across 61 transcripts on macOS, the session directory name disagreed with the session id recorded inside its own transcripts 37 times, and one directory held transcripts belonging to two different sessions. The sweep enumerates directories and reads identity out of each file instead. Transcripts are matched to the current project by the `cwd` each one records, so another project's runs are never pulled in.

Concurrent dispatches finish at the same moment, so a lock file serialises sweeps; a run that cannot take the lock exits quietly and the next trigger picks up whatever it missed. A hook run never fails and never blocks a session — errors go to the store's log and the exit status stays 0.

### What is stored, and where

Default location: `.groundwork/transcripts/` inside the project directory. It is created with a `.gitignore` of its own containing `*`, so the store is ignored in any repository without editing that repository's `.gitignore`.

```text
.groundwork/transcripts/
├── .gitignore
├── harvest.log
└── <parent session id>/
    ├── <agentId>.jsonl        # the transcript, copied whole
    └── <agentId>.meta.json    # source path, byte count, source mtime, capture time,
                               # line count, whether the last line is a complete record
```

Transcripts are stored whole rather than reduced to metrics, because the fields worth extracting are expected to change once real executions are analysed and the source files cannot be regenerated.

Capture is idempotent on `agentId`. Re-running over an already-harvested session copies nothing and reports nothing new. A transcript whose source has since grown — a copy taken while the file was still being written — is copied again on the next sweep, and `endsWithCompleteRecord` in the metadata records whether the stored copy ends on a whole JSON record.

### Retention and purging

Defaults: 90 days, capped at 1 GiB. Whichever bites first wins, and the oldest transcripts are dropped first. For scale, 61 real transcripts measured 15.8 MB in total, with a median of 231 KB.

| Environment variable | Default | Effect |
| --- | --- | --- |
| `GROUNDWORK_HARVEST_DIR` | `<project>/.groundwork/transcripts` | Where transcripts are stored. |
| `GROUNDWORK_HARVEST_MAX_DAYS` | `90` | Age cap, measured from the source file's modification time. |
| `GROUNDWORK_HARVEST_MAX_BYTES` | `1073741824` | Total size cap for the store. |
| `GROUNDWORK_TEMP_ROOT` | discovered | Overrides temp-root discovery. |

Run it by hand, inspect the store, or delete what it holds:

```bash
harvest-transcripts                      # sweep this project now
harvest-transcripts --all-projects       # sweep every project under the temp root
harvest-transcripts --list               # what is stored, and how much
harvest-transcripts --purge              # delete everything in the store
harvest-transcripts --purge --older-than-days 30
harvest-transcripts --self-test          # fixtures in a temp directory
```

Purging deletes only the local copies. It has no effect on Claude Code's own transcripts, which the operating system removes on its own schedule.

### Platform scope

Capture is specific to Claude Code, because the file format and the temp layout are. Codex ships no equivalent, and the harvest hooks are registered only in the Claude Code manifest.

## When to use Groundwork

Use it when:

- a change is non-trivial and has multiple unknowns;
- the code is unfamiliar or spans multiple files/services;
- external docs, issues, or URLs can materially change the decision;
- prior design decisions may matter;
- you want explicit alignment before an implementation plan is committed.

Skip it for a genuinely trivial one-line fix where reconnaissance would add ceremony without changing the decision.

## Repository surfaces

```text
plugins/groundwork/
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json
├── agents/
│   ├── recon-code.md
│   ├── recon-context.md
│   └── recon-external.md
├── commands/
│   └── groundwork.md          # Claude adapter (thin)
├── hooks/
│   └── hooks.json             # Claude Code hook entries (transcript harvest)
├── scripts/
│   └── harvest-transcripts    # stdlib-only Python 3 executable
├── skills/
│   └── groundwork/
│       └── SKILL.md           # canonical shared workflow (source of truth)
└── README.md
```

Claude-specific and Codex-specific orchestration stays at the platform boundary. The behavior users rely on — research first, wait for complete evidence, discuss the design, then plan — is defined once, in the canonical skill.
