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

## Required dependency — hard gate

Groundwork requires the Superpowers plugin. Before Phase 1, confirm that the
installed Superpowers skills include at least:

- `brainstorming`
- `writing-plans`

If either skill is unavailable:

1. Stop immediately.
2. Tell the user Groundwork requires Superpowers.
3. For Codex CLI, tell them to open `/plugins`, search for `Superpowers`, and
   install it from the official Codex plugin marketplace. For the Codex app,
   tell them to install Superpowers from the Plugins sidebar.
4. Do not substitute another workflow and do not continue with a reduced form of
   Groundwork.

Groundwork does not need to invoke `using-superpowers` itself. Superpowers only
needs to be installed and its required skills available.

## Input

Treat the user's request that invoked Groundwork as the problem statement.
Preserve every concrete source they supplied: file paths, symbols, issue or PR
IDs, library names, URLs, error messages, screenshots, and constraints.

Do not broaden the research merely because a source is available. Dispatch only
the reconnaissance threads that can materially change the decision.

# Phase 1 — Deep research

**Phase 1 is a hard barrier. Nothing in Phase 2 may begin until every dispatched
reconnaissance subagent is accounted for.**

## Dispatch model

Use native Codex subagents for independent reconnaissance. Spawn the relevant
subagents in one parallel round rather than serially when their questions do not
depend on one another.

The skill instruction is explicit authorization to use subagents for this
read-only reconnaissance phase.

For every subagent:

- give it one focused problem domain;
- provide a self-contained task packet because it may have no useful context
  beyond what you send;
- include the relevant paths, issue IDs, URLs, constraints, and anything already
  ruled out;
- require read-only behavior;
- require a short evidence-backed report;
- tell it not to propose a solution;
- tell it not to ask the user questions; unresolved decisions come back to the
  orchestrator.

Do not delegate the final decision, brainstorming, or plan to Phase 1 scouts.
Their job is evidence gathering only.

## Reconnaissance roles

Choose only the roles that match the problem. It is valid to dispatch multiple
subagents with the same role when there are independent questions inside that
source type.

### Code recon

Use when the problem names files, touches existing behavior, or requires mapping
callers, callees, tests, sibling patterns, configuration, or data flow inside the
current repository.

Include these instructions in the subagent task packet:

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

Include these instructions in the subagent task packet:

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

Include these instructions in the subagent task packet:

> You are a read-only scout for prior thinking. Search only the assigned context
> sources. Treat every historical statement as a claim about the past, not the
> present. Date the finding and, where practical, spot-check it against current
> code. Mark each finding `STILL TRUE`, `STALE`, or `UNVERIFIED`. Never edit
> files and do not propose a solution. Return at most 12 bullets using
> `## Findings`, `## Dead ends already tried`, and optionally
> `## Out of scope, noticed anyway`.

## Canonical thread choices

Use these as a menu, not a checklist:

| Need | Role | Suggested task label |
| --- | --- | --- |
| Read named files in full | code recon | Read named files |
| Map callers, sibling patterns, and tests | code recon | Map callers and tests |
| Verify library/framework/API behavior | external recon | Pull current docs |
| Read linked issues, PRs/MRs, pipelines, or URLs | external recon | Read linked sources |
| Recover project decisions or remembered constraints | context recon | Search prior decisions |
| Scan plans, architecture docs, ADRs, and git history | context recon | Scan prior plans |

Do not create an external or context thread just to make the research look more
thorough. Each subagent must have a concrete reason to exist.

## Phase 1 barrier

After dispatching, maintain an explicit roster of every subagent you started.
Phase 1 opens only when each roster entry has returned a usable report or has
been explicitly accounted for as failed.

Until then:

- do not invoke `brainstorming`;
- do not summarize partial findings to the user;
- do not state the goal or recommend an approach;
- do not ask product/design questions that depend on the recon results;
- do not start writing an implementation plan;
- do not treat the fastest subagent's report as representative of the whole
  research set.

If a subagent fails or returns unusable output, choose one of two actions once:
retry the thread with a tighter self-contained prompt, or mark the thread as
failed and proceed only after explicitly noting that missing evidence in Phase
2. A failed thread still has to be accounted for before the barrier opens.

When all dispatched threads are accounted for, collate their reports and move to
Phase 2.

# Phase 2 — Discuss and brainstorm

Entry condition: the Phase 1 barrier is open.

Invoke the installed Superpowers `brainstorming` skill **before drafting the
Phase 2 response**. Follow that skill's approval gate and classification rules.
Groundwork adds the evidence below; Superpowers owns the design conversation.

Write for a competent developer who has not read the researched part of the
codebase. The explanation must stand on its own.

Produce, in this order:

1. **What's going on** — 5-10 concise evidence-backed findings. Explain each
   internal name the first time it appears. Put paths/links at the end as
   receipts rather than making them the subject of the sentence. If scouts
   disagree, say so and explain which evidence is stronger.
2. **The problem** — one plain-language paragraph describing what happens today,
   what should happen, and why the gap exists. No source paths in this paragraph.
3. **The goal** — one sentence stating the outcome as you now understand it.
4. **Approaches** — propose the smallest credible set of alternatives, normally
   2-3. Lead with the recommended option and state the real tradeoff.
5. **Gray areas** — for each genuine unknown: what is unclear, what changes
   depending on the answer, and the options available.
6. **Focused questions** — ask only the decisions that cannot be resolved from
   the research. Ask one at a time when the brainstorming workflow requires it.

Do not write implementation code or an implementation plan in Phase 2. Wait for
the user to redirect, answer the gray areas, or approve the design.

## Engineering discipline while converging

Apply these constraints after exploration, not as a reason to prematurely narrow
Phase 1 or the divergent part of brainstorming.

### Make uncertainty visible

- Separate verified facts from assumptions.
- Never silently choose between materially different interpretations.
- Resolve uncertainty from evidence when possible; ask the user only for real
  product or engineering decisions.
- Push back when the requested direction conflicts with verified evidence.

### Prefer the smallest complete solution

- Solve the researched problem, not every adjacent problem.
- Avoid abstractions, options, configuration, or extensibility with no current
  requirement.
- Prefer existing project patterns when they are adequate.
- When two options achieve the goal, prefer fewer moving parts unless the extra
  complexity buys something the user actually needs.

### Keep the change boundary tight

- Every proposed modification must trace directly to the agreed goal.
- Keep unrelated cleanup and refactoring out of scope.
- Mention nearby technical debt separately rather than absorbing it into the
  implementation.
- Include cleanup only when the agreed change directly makes something obsolete.

### Plan around observable outcomes

For each meaningful planned change, the eventual plan should say:

1. what behavior or condition it establishes;
2. where the implementation belongs;
3. how the result will be verified.

Prefer concrete tests, reproduced behavior, build/type checks, API responses, or
other observable evidence over vague "verify it works" steps.

# Phase 3 — Plan

Entry condition: the user has explicitly accepted the approach, answered the
blocking gray areas, or otherwise greenlit planning. Do not enter Phase 3 in the
same turn that first presents the Phase 2 design.

1. Invoke the installed Superpowers `writing-plans` skill before writing the
   plan.
2. Follow its required plan structure and verification discipline.
3. Make every planned change trace to the accepted design and Phase 1 evidence.
4. Do not implement the plan inside Groundwork.
5. End by handing execution to Superpowers' `subagent-driven-development`
   (recommended when subagents are available) or `executing-plans` workflow.

Groundwork is finished when the implementation plan has been produced and handed
off. Research, alignment, and planning are its scope; coding is not.

# Rules

- Parallelize independent Phase 1 reconnaissance by default.
- Phase 1 blocks: no partial-result brainstorming or planning.
- Trust but verify subagent claims before basing the design on them when a cheap
  spot-check is available.
- Historical context is evidence about the past until current code confirms it.
- Phase 1 scouts are read-only and never choose the solution.
- Superpowers `brainstorming` and `writing-plans` invocations are mandatory at
  their respective phase boundaries.
- Keep Phase 2 understandable without forcing the user to open source files.
- Skip Groundwork for a genuinely trivial change rather than forcing ceremony on
  a problem that does not need research.
