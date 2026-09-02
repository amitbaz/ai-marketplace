# groundwork

Groundwork is a Claude Code extension/wrapper for [`obra/superpowers`](https://github.com/obra/superpowers). It adds parallel-subagent reconnaissance before Superpowers' discussion and planning workflow.

> **Required dependency:** Superpowers must be installed. Groundwork does not bundle or replace it, and `/groundwork` should stop if the required Superpowers skills are unavailable.

## Commands

| Command | Description |
|---------|-------------|
| `/groundwork <problem>` | Three-phase workflow: parallel research → brainstorm/discuss → plan |

## Installation

### 1. Install Superpowers

Install Superpowers from the official Claude plugin marketplace:

```text
/plugin install superpowers@claude-plugins-official
```

Groundwork relies on Superpowers' `brainstorming` and `writing-plans` skills and hands accepted plans off to its execution workflows.

### 2. Install Groundwork

Add this marketplace:

```text
/plugin marketplace add amitbaz/ai-marketplace
```

Then install Groundwork:

```text
/plugin install groundwork@amitbaz
```

## Usage

Hand the command a problem description with any relevant file paths, GitLab issue IDs, library names, or URLs:

```text
/groundwork Investigate why the customers table in dashboard does not scroll.
```

The command runs a three-phase workflow:

1. **Phase 1 — Deep research.** Spawns parallel recon subagents (read files, map callers, fetch GitHub issues, search project memory, pull library docs). Threads are picked to match the problem — no spawning recon for sources you didn't reference. **Phase 1 is a hard gate:** nothing else happens until every agent has reported.
2. **Phase 2 — Discuss & brainstorm.** Uses Superpowers' `brainstorming` skill, then explains the situation in plain language, restates the goal, proposes an approach with tradeoffs, flags gray areas, and asks focused questions.
3. **Phase 3 — Plan.** Only after you greenlight the approach. Uses Superpowers' `writing-plans` skill and produces a structured, verifiable plan before any code is written.

## Superpowers dependency

Superpowers is part of Groundwork's workflow contract, not an optional enhancement.

Groundwork expects the required Superpowers skills to be available before it begins. If they are unavailable, the workflow should stop and tell the user to install Superpowers instead of substituting other skills or continuing with a reduced version of the process.

Groundwork does **not** invoke `using-superpowers` itself. Installing Superpowers is the prerequisite; Groundwork directly uses the specific Superpowers skills needed by each phase.

## Built-in engineering discipline

Groundwork applies its own engineering discipline automatically when converging on an approach and writing the final plan. There is no separate Karpathy flag or Karpathy skill dependency.

The discipline keeps the plan grounded in four principles:

- **Make uncertainty visible** — distinguish verified facts from assumptions and surface decisions that genuinely need user input.
- **Prefer the smallest complete solution** — solve the researched problem without speculative features, abstractions, or configurability.
- **Keep the change boundary tight** — every planned modification should trace directly to the agreed goal; unrelated cleanup stays out of scope.
- **Plan around observable outcomes** — meaningful steps include a concrete way to verify that the intended behavior was achieved.

These constraints deliberately apply during convergence and planning, not during Phase 1 research or the divergent part of Phase 2 brainstorming. Groundwork first explores broadly enough to understand the problem, then narrows toward a precise solution.

## Recon agents

Phase 1 dispatches three color-coded read-only agent types, so you can tell at a glance what each pill is doing:

| Agent | Color | Covers |
|---|---|---|
| `groundwork:recon-code` | cyan | Inside this repo — named files, callers/callees, tests, sibling patterns |
| `groundwork:recon-external` | orange | Outside it — Context7 library docs, GitLab issues/MRs/pipelines, linked URLs |
| `groundwork:recon-context` | green | Prior thinking — project memory, `docs/plans/`, `docs/architecture/`, `docs/decisions/`, git history |

All three are read-only by construction and return the same report shape (findings with receipts, plus what they could not verify), so the collated Phase 2 input is uniform.

## When to Use

- Non-trivial change with multiple unknowns or unfamiliar code
- Problem spans multiple files, services, or tickets
- You want to avoid jumping to code before alignment on approach

Skip it for trivial one-line fixes — the command exits the ceremony early when the problem is obvious.

## Notes

- Phase 1 blocks. The brainstorm never starts on partial recon — reacting to the first report that lands anchors everything to whichever agent happened to be fastest, and the later reports get read as footnotes to a conclusion already drawn.
- Phase 2 is written for a developer who has never opened the code in question. Internal names are glossed on first use, and file paths appear as receipts at the end of a sentence rather than as the sentence itself.
- Phase 2 and Phase 3 Superpowers skill invocations are mandatory — the command calls the specific required skills explicitly, not just narrates the activity.
- Memory hits are treated as past claims and verified against current code before recommendations.
