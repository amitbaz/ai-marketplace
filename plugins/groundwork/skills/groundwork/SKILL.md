---
name: groundwork
description: Use before non-trivial code changes when the problem needs evidence from the codebase, external sources, or prior decisions before choosing an approach. Runs parallel read-only reconnaissance, then Superpowers brainstorming and planning. Requires the Superpowers plugin.
---

# Groundwork

Groundwork is a research-first wrapper around Superpowers. It exists to stop an
agent from committing to an implementation before it has enough evidence to make
a good decision.

Use Groundwork for non-trivial changes with multiple unknowns, unfamiliar code,
linked issues or docs, or meaningful architectural/product tradeoffs. Skip the
ceremony for a truly obvious one-line fix.

**This file is the single source of truth for Groundwork's workflow.** Every
supported platform runs the same three phases, the same Phase 1 barrier, the
same Superpowers handoffs, and the same engineering discipline. A platform
adapter — Claude Code's `/groundwork` command, or a future agent's entrypoint —
supplies only the dispatch syntax and orchestration primitives native to that
agent. If an adapter and this file disagree about *what* Groundwork does, this
file wins; the adapter only decides *how* the recon threads are spawned on that
platform. See "Platform adapters" at the end of this file.

## Required dependency — hard gate

Groundwork is an extension of the Superpowers plugin, not a replacement for it,
and it does not bundle it. Before Phase 1, confirm that the installed
Superpowers skills include at least:

- `brainstorming` — required by Phase 2
- `writing-plans` — required by Phase 3

If either skill is unavailable:

1. Stop immediately.
2. Tell the user Groundwork requires Superpowers and cannot run without it.
3. Give them the install instructions for the agent they are running:
   - **Claude Code** — `/plugin install superpowers@claude-plugins-official`
   - **Codex CLI** — open `/plugins`, search for `Superpowers`, install it from
     the official Codex plugin marketplace
   - **Codex app** — install Superpowers from the Plugins sidebar
4. Do not substitute another skill or workflow, and do not continue with a
   reduced form of Groundwork.

Groundwork does not invoke `using-superpowers` itself. Superpowers only needs to
be installed and its required skills available.

## Input

Treat the user's request that invoked Groundwork as the problem statement.
Preserve every concrete source they supplied: file paths, symbols, issue or PR
IDs, library names, URLs, error messages, screenshots, and constraints.

Do not broaden the research merely because a source is available. Dispatch only
the reconnaissance threads that can materially change the decision.

# Phase 1 — Deep research

**Phase 1 is a hard barrier. Nothing in Phase 2 may begin until every dispatched
reconnaissance thread is accounted for.** This is the most-violated rule in the
workflow.

## Dispatch model

Run independent reconnaissance threads in parallel using the platform's native
subagent mechanism, in a single dispatch round rather than serially, whenever
their questions do not depend on one another. This skill is explicit
authorization to use subagents for this read-only reconnaissance phase.

For every reconnaissance thread:

- give it one focused problem domain;
- provide a self-contained task packet, because it may have no useful context
  beyond what you send;
- include the relevant paths, issue IDs, URLs, constraints, and anything already
  ruled out;
- require read-only behavior;
- require a short evidence-backed report;
- tell it not to propose a solution;
- tell it not to ask the user questions — unresolved decisions come back to the
  orchestrator.

Do not delegate the final decision, the brainstorm, or the plan to a Phase 1
scout. Their job is evidence gathering only.

### Task packet quality bar

Each recon prompt is judged on three axes — a weak prompt returns mush:

1. **Focused** — one problem domain per thread. "Read the auth files" not
   "understand the codebase." If a thread sprawls, split it in two.
2. **Self-contained** — paste the actual context: file paths, ticket IDs, error
   text, what is already ruled out. Assume the scout knows nothing.
3. **Specific output** — state the return shape and a length cap, e.g. "Return
   ≤10 bullets: each a finding plus a `path:line` receipt. No preamble, no code
   dumps."

Common misses, each of which wastes a thread:

- **Too broad** — "research X" makes the scout boil the ocean. Name the exact
  files and sources.
- **No constraints** — the scout reads 50 files when 5 matter. Scope it: "only
  `src/renderer/`, ignore tests."
- **Vague output** — "tell me what you find" returns an unstructured wall.
  Demand the format above.

Read-only recon is the only kind of fan-out Groundwork does. Mutation-safety
concerns — conflict review, "don't edit shared files", running the suite after
dispatch — belong to an execution workflow, not here.

## Reconnaissance roles

Choose only the roles that match the problem. It is valid to dispatch multiple
threads with the same role when there are independent questions inside that
source type.

### Code recon

Use when the problem names files, touches existing behavior, or requires mapping
callers, callees, tests, sibling patterns, configuration, or data flow inside the
current repository.

Include these instructions in the task packet:

> You are a read-only codebase scout. Investigate only the assigned question.
> Never edit, create, or delete files and never run state-mutating commands.
> Every factual claim must include a `path:line` receipt. If you cannot verify a
> claim, put it under `Unverified` instead of guessing. Do not propose a fix.
> Return at most 12 bullets using `## Findings`, `## Unverified`, and optionally
> `## Out of scope, noticed anyway` with at most two lines.

### External recon

Use only when the problem actually depends on information outside the repository,
such as current library/framework/API documentation, a linked URL, or an issue,
PR/MR, pipeline, or other remote artifact.

Include these instructions in the task packet:

> You are a read-only external-source scout. Investigate only the assigned
> outside-source question. Prefer authoritative current documentation over model
> memory. Never post, edit, comment on, retry, close, or otherwise mutate remote
> resources. Every factual claim must include a URL, issue/PR identifier, or
> versioned documentation receipt. Put unreachable or ambiguous facts under
> `Unverified`. Do not propose a fix. Return at most 12 bullets using
> `## Findings`, `## Unverified`, and optionally `## Out of scope, noticed anyway`.

### Context recon

Use when previous thinking may matter: implementation plans, architecture docs,
decision records, project instructions/memory, or git history.

Include these instructions in the task packet:

> You are a read-only scout for prior thinking. Search only the assigned context
> sources. Treat every historical statement as a claim about the past, not the
> present. Date the finding and, where practical, spot-check it against current
> code. Mark each finding `STILL TRUE`, `STALE`, or `UNVERIFIED`. Never edit
> files and do not propose a solution. Return at most 12 bullets using
> `## Findings`, `## Dead ends already tried`, and optionally
> `## Out of scope, noticed anyway`.

All three roles are read-only by construction and return the same report shape,
so the collated Phase 2 input is uniform. Keep that shape if a platform adds a
fourth role.

## Canonical thread choices

Use these as a menu, not a checklist:

| Need | Role | Suggested task label | When |
| --- | --- | --- | --- |
| Read named files in full | code recon | Read named files | User cited specific paths |
| Map callers, sibling patterns, and tests | code recon | Map callers and tests | Touching existing code |
| Verify library/framework/API behavior | external recon | Pull current docs | Library or framework mentioned |
| Read linked issues, PRs/MRs, pipelines, or URLs | external recon | Read linked sources | Ticket/MR IDs or URLs in the prompt |
| Recover project decisions or remembered constraints | context recon | Search prior decisions | Prior thinking likely exists |
| Scan plans, architecture docs, ADRs, and git history | context recon | Scan prior plans | Repo has these directories |

Do not create an external or context thread just to make the research look more
thorough. Each thread must have a concrete reason to exist.

## Phase 1 barrier

After dispatching, maintain an explicit roster of every thread you started.
Phase 1 opens only when each roster entry has returned a usable report or has
been explicitly accounted for as failed. If you dispatched five threads, you
need five outcomes.

Until then:

- do not invoke `brainstorming`;
- do not summarize partial findings to the user;
- do not state the goal or recommend an approach;
- do not name gray areas or ask product/design questions that depend on the
  recon results;
- do not start writing an implementation plan;
- do not enter Phase 2 or Phase 3 in any form;
- do not treat the fastest thread's report as representative of the whole
  research set.

The reason is not tidiness. Fanning out pays off precisely when the threads
disagree — memory says a decision was made, code shows it was never implemented,
the docs show the API changed underneath both. Reacting to the first report that
lands anchors the brainstorm to whichever thread happened to be fastest, and the
later reports get read as footnotes to a conclusion you already drew.

Mechanics:

- After dispatching, stop and wait. Do not poll, sleep, or run filler tool calls
  to look busy.
- On each completion, check the roster. If entries are outstanding, the correct
  action is to produce no user-facing output at all.
- If a thread fails or returns unusable output, choose one of two actions once:
  retry it with a tighter self-contained packet, or mark it failed and proceed
  only after explicitly noting the missing evidence in Phase 2. A failed thread
  still has to be accounted for before the barrier opens. Never silently drop a
  dispatched thread.

When all dispatched threads are accounted for, collate their reports and move to
Phase 2.

# Phase 2 — Discuss and brainstorm

Entry condition: the Phase 1 barrier is open.

Invoke the installed Superpowers `brainstorming` skill **before drafting the
Phase 2 response**. This is an actual tool call, not narration: describing the
activity without invoking the skill leaves it unloaded and collapses Phase 2
into a thin recap. Follow that skill's approval gate and classification rules.
Groundwork supplies the evidence below; Superpowers owns the design
conversation.

## Who you are writing for

Write for a competent developer who has **never opened** the researched part of
the codebase. They know how to code. They do not know what an internal function
does, why there are two config paths, or what the team decided six months ago.
If they have to open a file to follow your sentence, the sentence is wrong.

That means:

- **Explain the thing, then cite where it lives.** Never make a path the subject
  of a sentence. Write "The status command reads timestamps from a cached
  snapshot instead of the live file, so it shows whatever was true at the last
  save (`commands/status.md:40`)" — not "`commands/status.md:40` uses the
  snapshot."
- **Paths go at the end, in backticks, as receipts.** One per point, max. They
  exist so the reader can verify you, not so they can reconstruct your
  reasoning. If a point needs three paths, it is really three points.
- **Gloss every name on first use.** Function, file, flag, service, table,
  internal term — one short clause saying what it is for. No exceptions for
  names that feel obvious to you; they feel obvious because you just spent
  Phase 1 reading them.
- **Plain words.** "Runs twice", not "double-invocation". "The two lists drift
  apart", not "state divergence". If a term of art is genuinely clearest, use it
  and gloss it.
- **Short sentences, one idea each.** Prefer prose to nested bullets; a bullet
  needing sub-bullets is usually a paragraph.
- **No unexplained internal shorthand** — ticket numbers, acronyms, service
  nicknames. Expand each once.

## What to write

Produce, in this order:

1. **What's going on** — 5-10 concise evidence-backed findings in plain
   language, each stated as something the reader can picture, with the receipt
   at the end. Where scouts contradicted each other, say so out loud and say
   which evidence you believe and why.
2. **The problem** — one plain-language paragraph describing what happens today,
   what should happen, and why the gap exists. No source paths in this
   paragraph. If you cannot write it without them, you do not understand the
   problem yet.
3. **The goal** — one sentence stating the outcome as you now understand it.
   Surface any mismatch with the original ask.
4. **Approaches** — the smallest credible set of alternatives, normally 2-3.
   Lead with the recommended one, describe each by what it achieves rather than
   which function it edits, and state the real tradeoff (slower but simpler,
   more code but no migration, and so on).
5. **Gray areas** — for each genuine unknown, in this order: what is unclear,
   what breaks or changes depending on the answer, and the options you see. Do
   not pick silently.
6. **Focused questions** — ask only the decisions that cannot be resolved from
   the research, phrased so someone who has not read the code can choose. Ask
   one at a time when the brainstorming workflow requires it.

Do not write implementation code or an implementation plan in Phase 2. Wait for
the user to redirect, answer the gray areas, or approve the design.

## Engineering discipline while converging

Apply these constraints after exploration, not as a reason to prematurely narrow
Phase 1 or the divergent part of brainstorming.

### Make uncertainty visible

- Separate verified facts from assumptions.
- Never silently choose between materially different interpretations; show the
  alternatives when evidence supports more than one.
- Call out missing information when it could materially change the approach.
- Resolve uncertainty from evidence when possible; ask the user only for real
  product or engineering decisions.
- Push back when the requested direction conflicts with verified evidence.

### Prefer the smallest complete solution

- Solve the researched problem, not every adjacent problem.
- Avoid abstractions, options, configuration, indirection, or defensive
  machinery with no current requirement.
- Prefer existing project patterns when they are adequate.
- When two options achieve the goal, prefer fewer moving parts unless the extra
  complexity buys something the user actually needs.

Small does not mean crude. The solution still has to handle the real cases
uncovered during recon.

### Keep the change boundary tight

- Every proposed modification must trace directly to the agreed goal.
- Keep unrelated cleanup and refactoring out of scope.
- Preserve existing conventions unless changing them is necessary.
- Mention nearby technical debt separately rather than absorbing it into the
  implementation.
- Include cleanup only when the agreed change directly makes something obsolete,
  such as imports, helpers, or paths that would become unused.

### Plan around observable outcomes

For each meaningful planned change, the eventual plan should say:

1. what behavior or condition it establishes;
2. where the implementation belongs;
3. how the result will be verified.

Prefer concrete tests, reproduced behavior, build/type checks, API responses, or
other observable evidence over vague "verify it works" steps. For bug fixes,
reproduce the failure before fixing it whenever practical. For refactors,
preserve behavior with verification before and after. For new behavior, define
the expected result clearly enough that the implementation can be judged against
it.

# Phase 3 — Plan

Entry condition: the user has explicitly accepted the approach, answered the
blocking gray areas, or otherwise greenlit planning. Do not enter Phase 3 in the
same turn that first presents the Phase 2 design.

1. Invoke the installed Superpowers `writing-plans` skill before writing the
   plan — again an actual tool call, not narration.
2. Follow its required plan structure and verification discipline.
3. Make every planned change trace to the accepted design and Phase 1 evidence,
   under the engineering discipline above.
4. Do not implement the plan inside Groundwork.
5. End by handing execution to Superpowers' `subagent-driven-development`
   (recommended when subagents are available) or `executing-plans` workflow, and
   state that exit explicitly.

Groundwork is finished when the implementation plan has been produced and handed
off. Research, alignment, and planning are its scope; coding is not.

# Rules

- Parallelize independent Phase 1 reconnaissance by default; serial dispatch
  wastes turns when the threads are independent.
- Phase 1 blocks: no partial-result summary, questions, brainstorming, or
  planning. Partial recon is worse than none — it looks complete and is not.
- Trust but verify scout claims before basing the design on them when a cheap
  spot-check is available.
- Historical context is evidence about the past until current code confirms it.
- Phase 1 scouts are read-only and never choose the solution.
- Superpowers `brainstorming` and `writing-plans` invocations are mandatory at
  their respective phase boundaries, and must be real skill invocations.
- Keep Phase 2 understandable without forcing the user to open source files.
- The engineering discipline governs convergence in Phase 2 and all of Phase 3.
  It must not narrow Phase 1 recon or suppress legitimate alternatives during
  brainstorming.
- Skip Groundwork for a genuinely trivial change rather than forcing ceremony on
  a problem that does not need research.

# Platform adapters

This skill is platform-neutral. Each supported agent adds a thin adapter that
carries only its own orchestration syntax and entrypoint, and never restates the
workflow above.

| Platform | Adapter | Adapter owns |
| --- | --- | --- |
| Claude Code | `commands/groundwork.md` (`/groundwork`) | `$ARGUMENTS`, `Agent(...)` dispatch syntax, the `groundwork:recon-*` subagent types and their colors, Claude install wording |
| Codex | this skill, invoked as `$groundwork` | native Codex subagent dispatch, described by the platform-neutral dispatch model above |

Codex consumes this file directly and needs no separate adapter file. When an
adapter maps the reconnaissance roles above onto named platform agents, the
mapping is adapter-local; the roles, report shapes, barrier, and phase contract
stay here.
