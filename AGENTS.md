# AGENTS.md

This file provides guidance to coding agents (Claude Code, Codex, and any agent that reads AGENTS.md) when working with code in this repository.

## What this repo is

A personal plugin marketplace that ships **one plugin, Groundwork, to two platforms** — Claude Code and OpenAI Codex. There is no application source code and no build: every artifact is Markdown with YAML frontmatter, or a JSON manifest, consumed directly by each platform's plugin loader. The only executable is `scripts/check-adapter-boundary.py`, a stdlib-only structural check. "Changing behavior" here means editing prose instructions, not code.

## Dual-platform layout

```
.claude-plugin/marketplace.json        # Claude Code marketplace manifest
.agents/plugins/marketplace.json       # Codex marketplace manifest
plugins/groundwork/
  .claude-plugin/plugin.json           # Claude Code plugin manifest
  .codex-plugin/plugin.json            # Codex plugin manifest
  commands/groundwork.md               # Claude Code: /groundwork (thin adapter)
  agents/recon-*.md                    # Claude Code: groundwork:recon-* subagents
  skills/groundwork/SKILL.md           # canonical workflow; Codex: $groundwork
  README.md
scripts/check-adapter-boundary.py      # enforces the shared-skill/adapter split
.github/workflows/validate.yml         # runs the checks in CI
docs/superpowers/{specs,plans}/        # design docs from past groundwork runs
```

The two marketplace manifests intentionally coexist and have **different schemas** — the Codex one nests `source` as an object (`{"source": "local", "path": ...}`) and carries `policy`/`interface` blocks the Claude one does not. Do not unify them.

Things that must stay in sync when you change anything:

- `version` in **both** `plugin.json` files, plus the version column in the root README table.
- The `description` string across both `plugin.json` files and both `marketplace.json` files.

`python3 scripts/check-adapter-boundary.py` checks both of those automatically.

## Shared skill, thin adapters

The workflow contract lives in exactly one place: `plugins/groundwork/skills/groundwork/SKILL.md`. It is platform-neutral and owns the three phases, the Phase 1 gate, the Superpowers dependency and handoffs, the Phase 2 writing rules, the engineering discipline, and the general rules.

Adapters carry only what is native to their platform:

- **Claude Code** — `commands/groundwork.md` invokes `Skill(skill: "groundwork:groundwork")` first (Claude auto-discovers plugin skills at `skills/<name>/SKILL.md` and namespaces them `<plugin>:<skill>`), then adds `$ARGUMENTS`, `Agent(...)` dispatch syntax, the three `groundwork:recon-*` subagent types and their colors, `AskUserQuestion` usage, and Claude's Superpowers install string.
- **Codex** — consumes the canonical skill directly as `$groundwork`; there is no second Codex file.

Do not re-add workflow prose to an adapter. `python3 scripts/check-adapter-boundary.py` fails when an adapter reintroduces workflow headings, workflow-owned phrases (`brainstorming`, `writing-plans`, `engineering discipline`, …), or any 10-word passage copied from the canonical skill; it also checks version/description sync across the manifests. CI runs it on every push and PR.

## Loader contract

- `marketplace.json` `plugins[].name` must match the `name` in that plugin's `plugin.json`, and the source path must point at the plugin directory.
- A file in `commands/` becomes a slash command named after the *file*, not after any frontmatter field. Frontmatter carries `description` and `argument-hint` (quote the argument hint — an unquoted `<...>` is invalid YAML; that bit us in `3c41ddc`). `$ARGUMENTS` is the user's raw input.
- A file in `agents/` becomes a subagent addressable as `groundwork:<filename>`. Frontmatter carries `description` (this is what the dispatching model reads to pick the agent — write it as selection criteria, not marketing), `tools:` (an allowlist; MCP wildcards like `mcp__context7__*` are valid), and `color:`.
- Codex skills live at `skills/<name>/SKILL.md` with `name` + `description` frontmatter; `plugin.json` points at the directory via `"skills": "./skills/"`.

## Testing a change

Run the structural checks, then verify by installing locally and exercising the workflow:

```bash
python3 scripts/check-adapter-boundary.py
```

```bash
# Claude Code
/plugin marketplace add /Users/amitbaz/my-ai-marketplaces/amitbaz
/plugin install groundwork@amitbaz

# Codex
codex plugin marketplace add amitbaz/ai-marketplace --ref main
codex plugin add groundwork@amitbaz
```

Frontmatter and manifest JSON are the fragile parts — a malformed YAML block or JSON manifest makes a command, agent, or skill silently not appear, with no error. If something doesn't show up after install, suspect frontmatter first.

## Groundwork — design intent

Groundwork is an **extension of `obra/superpowers`, not a replacement**. It does not bundle it. The canonical skill opens with a hard dependency gate that applies on every platform: if `brainstorming` or `writing-plans` is unavailable, stop and tell the user to install Superpowers — never substitute another skill or run a reduced form of the workflow. Groundwork deliberately does *not* invoke `using-superpowers` itself; the dependency only needs to be installed.

Several rules in the workflow look redundant but are load-bearing. Don't "simplify" them without understanding why:

- **Phase 1 is a hard gate.** No user-facing output until every recon thread reports. The reason is anchoring: fanning out only pays off when the threads *disagree*, and reacting to the first report turns the later ones into footnotes.
- **Three phases are deliberately separated** — recon (read-only) → brainstorm (`brainstorming`) → plan (`writing-plans`). Phase 3 never happens on the same turn as Phase 2.
- **Skill invocations must be actual tool calls**, not narration. Describing the activity leaves the skill unloaded and collapses the phase.
- **The workflow ends at an accepted plan.** Execution is out of scope by design; it hands off to a Superpowers execution workflow (`subagent-driven-development` or `executing-plans`).
- All three Claude recon agents are read-only by construction and return the same report shape (findings with `file:line` receipts, plus what they could not verify), so Phase 2's collated input is uniform. Keep that shape if you add a fourth.
- Phase 2 prose rules (paths as receipts at the end of a sentence, gloss every internal name, plain words) exist because the output is written for a developer who has never opened the code in question.
