---
description: Parallel-subagent recon on a problem, then discuss the approach and gray areas before committing to code.
argument-hint: "<problem description with file paths, issue IDs, links, etc.>"
---

# Groundwork — Claude Code adapter

This command is a thin adapter. The workflow itself — every phase, the recon
gate, the Superpowers dependency and handoffs, the writing rules, the
convergence constraints, and the stop-before-implementation contract — lives in
the canonical Groundwork skill and is not repeated here.

**Before anything else, invoke the canonical skill with the Skill tool:**

```
Skill(skill: "groundwork:groundwork")
```

If that skill does not load, read
`${CLAUDE_PLUGIN_ROOT}/skills/groundwork/SKILL.md` and follow it verbatim
instead. Do not reconstruct the workflow from memory, and do not run a reduced
form of it.

Then follow the skill, applying the Claude-specific orchestration below wherever
it refers to dispatching reconnaissance threads.

## Problem

$ARGUMENTS

## Claude-specific: Superpowers install wording

The skill's dependency gate is a hard stop. On Claude Code, the install
instruction to give the user is:

```text
/plugin install superpowers@claude-plugins-official
```

## Claude-specific: Phase 1 dispatch

Spawn the reconnaissance threads in a **single message** with multiple `Agent`
tool calls — sequential calls waste turns. Each call MUST include:

- `name:` — short kebab-case identifier, visible as a pill in the UI (e.g.
  `recon-files`, `recon-callers`, `recon-docs`, `recon-issues`, `recon-memory`,
  `recon-history`). This is the *instance* name, independent of `subagent_type`.
  Never spawn a recon agent without one; unnamed agents render as anonymous
  pills the user cannot tell apart.
- `description:` — 3-5 word label shown next to the pill (e.g. `"Read named
  files"`, `"Map callers + tests"`, `"Pull library docs"`, `"Fetch linked
  issues"`, `"Search project memory"`, `"Scan prior plans"`).
- `subagent_type:` — one of the three `groundwork:recon-*` agents below.
- `prompt:` — the self-contained task packet described by the skill. The agent
  has zero conversation context.

Leave `run_in_background` at its default. Recon agents already run concurrently,
and the harness re-invokes you as each one finishes.

Example spawn shape (single message, multiple blocks):

```
Agent(name: "recon-files",   subagent_type: "groundwork:recon-code",     description: "Read named files",     prompt: "...")
Agent(name: "recon-callers", subagent_type: "groundwork:recon-code",     description: "Map callers + tests",  prompt: "...")
Agent(name: "recon-docs",    subagent_type: "groundwork:recon-external", description: "Pull library docs",    prompt: "...")
```

## Claude-specific: recon agent types

The skill's three reconnaissance roles map onto these custom subagents, which
already carry the read-only constraints and report shape in their own
definitions:

| Role in the skill | `subagent_type` | Color |
| --- | --- | --- |
| Code recon | `groundwork:recon-code` | cyan |
| External recon | `groundwork:recon-external` | orange |
| Context recon | `groundwork:recon-context` | green |

The colors are load-bearing for the user, not decoration: at a glance they can
tell which pills are reading code, which are reaching outside, and which are
digging up old decisions. Never fall back to bare `Explore` or
`general-purpose` for a recon thread — those render as uncolored pills and lose
the fixed report shape.

Pick the threads that match the problem, using the skill's thread menu; do not
spawn an agent for a source the user did not reference.

## Claude-specific: gate mechanics and questions

- Track the dispatched agents as a roster and wait for the harness completion
  notifications, as the skill's Phase 1 barrier requires. `AskUserQuestion` is
  covered by that barrier: do not call it until the roster is complete.
- Use `AskUserQuestion` for the skill's focused questions in Phase 2, for the
  gray areas that genuinely block progress.
