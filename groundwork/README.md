# groundwork

Parallel-subagent recon on a problem, then discuss the approach and gray areas before committing to code.

## Commands

| Command | Description |
|---------|-------------|
| `/groundwork [--karpathy] <problem>` | Three-phase workflow: parallel research → brainstorm/discuss → plan |

## Quick Start

```bash
claude plugin install groundwork@amitbaz
```

## Usage

Hand the command a problem description with any relevant file paths, GitLab issue IDs, library names, or URLs:

```
/groundwork Investigate why the customers table in dashboard does not scroll.
```

The command runs a three-phase workflow:

1. **Phase 1 — Deep research.** Spawns parallel recon subagents (read files, map callers, fetch GitHub issues, search project memory, pull library docs). Threads are picked to match the problem — no spawning recon for sources you didn't reference. **Phase 1 is a hard gate:** nothing else happens until every agent has reported.
2. **Phase 2 — Discuss & brainstorm.** Loads the `brainstorming` skill, then explains the situation in plain language, restates the goal, proposes an approach with tradeoffs, flags gray areas, and asks focused questions.
3. **Phase 3 — Plan.** Only after you greenlight the approach. Loads `writing-plans` and produces a structured plan before any code is written.

## Recon agents

Phase 1 dispatches three color-coded read-only agent types, so you can tell at a glance what each pill is doing:

| Agent | Color | Covers |
|---|---|---|
| `groundwork:recon-code` | cyan | Inside this repo — named files, callers/callees, tests, sibling patterns |
| `groundwork:recon-external` | orange | Outside it — Context7 library docs, GitLab issues/MRs/pipelines, linked URLs |
| `groundwork:recon-context` | green | Prior thinking — project memory, `docs/plans/`, `docs/architecture/`, `docs/decisions/`, git history |

All three are read-only by construction and return the same report shape (findings with receipts, plus what they could not verify), so the collated Phase 2 input is uniform.

## Flags

| Flag | Effect | When it fires |
|------|--------|---------------|
| `--karpathy` | Loads `andrej-karpathy-skills:karpathy-guidelines` for surgical/minimal code discipline | Phase 3 entry only (loading earlier collapses brainstorm) |

Flags are stripped from the problem text before research starts. Unavailable skills are silently skipped.

## When to Use

- Non-trivial change with multiple unknowns or unfamiliar code
- Problem spans multiple files, services, or tickets
- You want to avoid jumping to code before alignment on approach

Skip it for trivial one-line fixes — the command exits the ceremony early when the problem is obvious.

## Notes

- Phase 1 blocks. The brainstorm never starts on partial recon — reacting to the first report that lands anchors everything to whichever agent happened to be fastest, and the later reports get read as footnotes to a conclusion already drawn.
- Phase 2 is written for a developer who has never opened the code in question. Internal names are glossed on first use, and file paths appear as receipts at the end of a sentence rather than as the sentence itself.
- Phase 2 and Phase 3 skill invocations are mandatory — the command calls the `Skill` tool explicitly, not just narrates the activity.
- Memory hits are treated as past claims and verified against current code before recommendations.
