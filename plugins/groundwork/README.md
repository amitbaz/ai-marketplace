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

Groundwork preserves one workflow contract while using each platform's native extension model.

### Claude Code

Claude uses:

- `.claude-plugin/plugin.json` for plugin metadata;
- `commands/groundwork.md` for `/groundwork`;
- three custom read-only recon agents under `agents/`;
- Claude's agent/subagent primitives to dispatch those recon agents in parallel.

The three Claude recon agents remain color-coded in the UI:

| Agent | Color | Covers |
| --- | --- | --- |
| `groundwork:recon-code` | cyan | Inside the repo — named files, callers/callees, tests, sibling patterns |
| `groundwork:recon-external` | orange | Outside it — current docs, issues/MRs/PRs/pipelines, linked URLs |
| `groundwork:recon-context` | green | Prior thinking — plans, architecture/decision docs, project memory, git history |

### Codex

Codex uses:

- `.codex-plugin/plugin.json` for plugin metadata;
- `skills/groundwork/SKILL.md` for `$groundwork`;
- native Codex subagents for Phase 1 reconnaissance.

Codex does not depend on Claude's `Agent(...)`, `subagent_type`, `$ARGUMENTS`, or `AskUserQuestion` primitives. Instead, the Groundwork skill gives each native subagent a self-contained read-only role packet for code recon, external recon, or prior-context recon and explicitly requires the orchestrator to account for every dispatched subagent before Phase 2 begins.

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
│   └── groundwork.md
├── skills/
│   └── groundwork/
│       └── SKILL.md
└── README.md
```

Claude-specific and Codex-specific orchestration stays at the platform boundary. The behavior users rely on — research first, wait for complete evidence, discuss the design, then plan — remains the same.
