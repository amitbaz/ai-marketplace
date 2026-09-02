---
description: Parallel-subagent recon on a problem, then discuss the approach and gray areas before committing to code.
argument-hint: [--karpathy] <problem description with file paths, GitLab issues, links, etc.>
---

## Flag handling (do this FIRST, before anything else)

Scan `$ARGUMENTS` for these flags. Strip them from the problem text before treating the rest as the problem description. Record which flags were set — they fire at specific phases below, NOT all at the top.

- `--karpathy` → DO NOT invoke yet. `karpathy-guidelines` biases toward surgical/minimal code and will collapse the brainstorm phase if loaded early. Defer until Phase 3 (see below). If not available there, silently skip.

Then invoke the `using-superpowers` skill. Then tackle the request below.

## Problem

$ARGUMENTS (with flags stripped)

## Phase 1 — Deep research (parallel subagents)

**Phase 1 is a hard gate.** Nothing downstream starts until every recon agent has finished and returned its report. See "The Phase 1 gate" below — it is the most-violated rule in this command.

Spawn parallel subagents in a **single message** with multiple `Agent` tool calls — sequential calls waste turns. Each call MUST include:

- `name:` — short kebab-case identifier visible as a pill in the UI (e.g. `recon-files`, `recon-callers`, `recon-docs`, `recon-issues`, `recon-memory`, `recon-history`). Pick names that read at a glance. This is the *instance* name and is independent of `subagent_type`.
- `description:` — 3–5 word label shown next to the pill (e.g. `"Read named files"`, `"Map callers + tests"`, `"Pull library docs"`, `"Fetch GitLab issues"`, `"Search project memory"`, `"Scan prior plans"`).
- `subagent_type:` — one of groundwork's three color-coded recon agents (below). They are read-only by construction and return a fixed report shape, so the collated Phase 2 input is uniform.
- Self-contained `prompt:` — agent has zero conversation context; brief it like a smart colleague (goal, what's already ruled out, file paths, expected output format, response length cap).

Do NOT pass `run_in_background` — it is not an `Agent` parameter. Subagents already run concurrently and the harness notifies you as each one finishes.

### The three recon agent types

| `subagent_type` | Color | Covers |
|---|---|---|
| `groundwork:recon-code` | cyan | Anything inside this repo — reading named files, mapping callers/callees/tests, finding sibling patterns |
| `groundwork:recon-external` | orange | Anything outside it — Context7 library docs, GitLab issues/MRs/pipelines, linked URLs |
| `groundwork:recon-context` | green | Prior thinking — project memory, `docs/plans/`, `docs/architecture/`, `docs/decisions/`, git history |

The colors are load-bearing for the user, not decoration: at a glance they can tell which pills are reading code, which are reaching outside, and which are digging up old decisions. Never fall back to bare `Explore` or `general-purpose` for a recon thread — those render as uncolored pills and lose the fixed report shape. (`gsd-codebase-mapper` remains a valid exception if a `.planning/codebase/` structure already exists and you need it refreshed.)

Pick the threads that actually match the problem — do not spawn an agent for a source the user did not reference. Canonical thread menu:

| Thread | subagent_type | description (label) | When |
|---|---|---|---|
| Read named files/issues/URLs in full | `groundwork:recon-code` | `"Read named files"` | User cited specific paths |
| Map callers/callees/sibling patterns/tests | `groundwork:recon-code` | `"Map callers + tests"` | Touching existing code |
| Pull library/API docs via Context7 | `groundwork:recon-external` | `"Pull library docs"` | Library/framework mentioned |
| Fetch GitLab issues/MRs/pipelines | `groundwork:recon-external` | `"Fetch GitLab issues"` | Ticket/MR IDs in prompt |
| Read linked URLs / external pages | `groundwork:recon-external` | `"Read linked pages"` | URLs in prompt |
| Search project memory + prior decisions | `groundwork:recon-context` | `"Search project memory"` | Likely prior thinking exists |
| Scan `docs/plans/`, `docs/architecture/`, `docs/decisions/` | `groundwork:recon-context` | `"Scan prior plans"` | Repo has these dirs |

Example spawn shape (single message, multiple blocks):

```
Agent(name: "recon-files",   subagent_type: "groundwork:recon-code",     description: "Read named files",     prompt: "...")
Agent(name: "recon-callers", subagent_type: "groundwork:recon-code",     description: "Map callers + tests",  prompt: "...")
Agent(name: "recon-docs",    subagent_type: "groundwork:recon-external", description: "Pull library docs",    prompt: "...")
```

### The Phase 1 gate

Recon is a barrier, not a stream. Until **every** dispatched agent has reported back:

- Do NOT invoke `brainstorming`.
- Do NOT summarize partial findings to the user.
- Do NOT state the goal, propose an approach, or name gray areas.
- Do NOT call `AskUserQuestion`.
- Do NOT enter Phase 2 or Phase 3 in any form.

The reason is not tidiness. The whole point of fanning out is that the threads disagree — the memory agent says a decision was made, the code agent shows it was never implemented, the docs agent shows the API changed underneath both. Reacting to the first report that lands anchors the brainstorm to whichever agent happened to be fastest, and the later reports get read as footnotes to a conclusion you already drew.

Mechanics:

- After dispatching, **stop and wait.** Do NOT poll, do NOT sleep, do NOT run filler tool calls to look busy. The harness re-invokes you as each agent finishes.
- On each completion notification, check the roster: are all dispatched agents accounted for? If not, wait again — the correct action is to produce no user-facing output at all.
- Track the roster explicitly. If you dispatched five agents, you need five reports before the gate opens.
- If an agent dies or returns nothing usable, that counts as accounted-for. Decide once: re-spawn it (and the gate stays shut until the replacement returns) or proceed without it and say so explicitly in Phase 2. Do not silently drop a thread.
- Only when the roster is complete: collate all reports, then open Phase 2.

### Agent prompt quality bar (adapted from `dispatching-parallel-agents`)

Each recon prompt is judged on three axes — a weak prompt returns mush:

1. **Focused** — one problem domain per agent. "Read the auth files" not "understand the codebase." If a thread sprawls, split it into two agents.
2. **Self-contained** — paste the actual context: file paths, ticket IDs, error text, what's already ruled out. The agent has zero session history; assume it knows nothing.
3. **Specific output** — state the return shape and a length cap. e.g. "Return ≤10 bullets: each a finding + `file:line`. No preamble, no code dumps."

Common misses (each wastes the agent):
- **Too broad** — "research X" → agent boils the ocean. Name the exact files/sources.
- **No constraints** — agent reads 50 files when 5 matter. Scope it: "only `src/renderer/`, ignore tests."
- **Vague output** — "tell me what you find" → unstructured wall. Demand the format above.

> Note: this is the *read-recon* adaptation. The skill's mutation-safety half (conflict review, "don't edit shared files," post-dispatch suite run) does NOT apply here — recon agents read only. That half belongs to a future execute phase, not groundwork.

## Phase 2 — Discuss & brainstorm

Entry condition: the Phase 1 gate is open — every dispatched agent has reported.

First, **invoke the `brainstorming` skill via the Skill tool BEFORE drafting your reply**. This is not optional and not implicit — call `Skill(skill: "brainstorming")` explicitly. The skill enforces divergent exploration of intent, requirements, and design before any solution shape is locked in. Skipping it collapses Phase 2 into a thin recap.

### Who you are writing for

Write for a competent developer who has **never opened this part of the codebase**. They know how to code. They do not know what `resolveDraftRef` does, why there are two config paths, or what the team decided six months ago. If they have to open a file to follow your sentence, you wrote the sentence wrong.

That means:

- **Explain the thing, then cite where it lives.** Never make a file path the subject of a sentence. Write "The status command reads timestamps from a cached snapshot instead of the live file, so it shows whatever was true at the last save (`commands/status.md:40`)" — not "`commands/status.md:40` uses the snapshot."
- **Paths go at the end, in backticks, as receipts.** One per point, max. They are there so the reader can verify you, not so they can reconstruct your reasoning. If a point needs three paths to make sense, the point is really three points.
- **Gloss every name the first time.** Function, file, flag, service, table, internal term — one short clause saying what it is for. "the resolver (the bit that turns a slug into a full config)". No exceptions for names that feel obvious to you; they feel obvious because you just spent Phase 1 reading them.
- **Plain words.** Say "runs twice" not "double-invocation"; "the two lists drift apart" not "state divergence"; "we never check" not "there is no validation layer". If a term of art is genuinely the clearest option, use it and gloss it.
- **Short sentences.** One idea each. Prefer prose to nested bullets; a bullet that needs sub-bullets is usually a paragraph.
- **No unexplained internal shorthand.** Never assume the reader knows a ticket number, an acronym, or a service nickname. Expand it once.

### What to write

1. **What's going on** — 5–10 bullets in plain language. Each is a finding stated as something the reader can picture, with the receipt at the end. Where the agents contradicted each other, say so out loud and say which one you believe and why.
2. **The problem in one paragraph** — before any solution talk, describe the situation in prose, as you would to a teammate at a whiteboard: what happens today, what should happen, and why the gap exists. No paths in this paragraph at all. If you cannot write it without them, you do not understand the problem yet.
3. **The goal as you now understand it** — one sentence. Surface any mismatch with the original ask.
4. **Proposed approach** — 3–6 steps, each described by what it achieves rather than which function it edits. Name at least one alternative and say plainly why you prefer yours — the tradeoff in real terms (slower but simpler, more code but no migration, etc.).
5. **Gray areas** — every unknown, ambiguity, missing decision, or risk. For each, three things in this order: **what is unclear**, **what breaks or changes depending on the answer** (consequences the reader can feel, not abstract risk), and **the options you see**. Do not pick silently.
6. **Focused questions** — use `AskUserQuestion` for the gray areas that genuinely block progress. Skip questions you can answer from the research. Phrase options so someone who has not read the code can choose between them.

Do not write code in this phase. Do not start a plan file. Wait for the user to redirect, confirm, or answer the gray areas.

## Phase 3 — Plan (after user confirms approach)

Trigger condition: user has answered the gray areas, accepted the approach, or otherwise greenlit moving forward. Do NOT enter Phase 3 on the same turn as Phase 2.

When entering Phase 3:

1. **If `--karpathy` flag was set**, invoke `andrej-karpathy-skills:karpathy-guidelines` NOW via the Skill tool. It governs code-quality discipline during planning + execution. Silently skip if unavailable.
2. **Invoke `writing-plans` skill** via the Skill tool. It enforces structured multi-step plan output before touching code.
3. Under those skills' framing, produce the plan. Only after the plan is reviewed/accepted do you write code.
4. **Hand off, don't execute.** groundwork ends at an accepted plan. State the exit explicitly: the user runs `superpowers:subagent-driven-development` (same session) or `superpowers:executing-plans` (parallel session) to build. Do NOT start coding inside groundwork — execution is out of scope by design.

## Rules

- Parallel by default in Phase 1. Sequential subagent calls waste turns when the threads are independent. ALL Phase 1 agents go in a single message, each with `name:` + `description:` + a `groundwork:recon-*` `subagent_type`. Never spawn a recon agent without a `name` — unnamed agents show as anonymous pills and the user cannot tell them apart at a glance.
- Phase 1 blocks. No brainstorming, no summary, no questions, no Phase 2 until every dispatched agent has reported. Partial recon is worse than none — it looks complete and isn't.
- Trust-but-verify: if a subagent claims a file/symbol exists, spot-check before basing the proposal on it.
- If the problem is trivial (one-line fix, obvious answer), say so and skip the ceremony — do not force the two-phase dance.
- Memory hits are claims about the past, not the present — verify against current code before recommending.
- Phase 2 is written for someone unfamiliar with this code. Paths are receipts at the end of a sentence, never the sentence itself. Gloss every internal name on first use.
- Skill invocations in Phase 2 and Phase 3 are NOT optional narration — call the `Skill` tool with the exact skill name. If you describe the activity without calling the tool, the skill never loads and the phase collapses.
- `--karpathy` fires at Phase 3 entry, never earlier. Loading it during recon/brainstorm biases the model toward minimal/surgical output and kills divergent exploration.
