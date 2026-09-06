# AGENTS.md

This file provides guidance to coding agents (Claude Code, Codex, and any agent that reads AGENTS.md) when working with code in this repository.

## What this repo is

A personal plugin marketplace that ships **one plugin, Groundwork, to two platforms** — Claude Code and OpenAI Codex. There is no source code, no build, no test suite, and no dependencies: every artifact is Markdown with YAML frontmatter, or a JSON manifest, consumed directly by each platform's plugin loader. "Changing behavior" here means editing prose instructions, not code.

## Dual-platform layout

```
.claude-plugin/marketplace.json        # Claude Code marketplace manifest
.agents/plugins/marketplace.json       # Codex marketplace manifest
plugins/groundwork/
  .claude-plugin/plugin.json           # Claude Code plugin manifest
  .codex-plugin/plugin.json            # Codex plugin manifest
  commands/groundwork.md               # Claude Code: /groundwork
  agents/recon-*.md                    # Claude Code: groundwork:recon-* subagents
  skills/groundwork/SKILL.md           # Codex: $groundwork
  README.md
docs/superpowers/{specs,plans}/        # design docs from past groundwork runs
```

The two marketplace manifests intentionally coexist and have **different schemas** — the Codex one nests `source` as an object (`{"source": "local", "path": ...}`) and carries `policy`/`interface` blocks the Claude one does not. Do not unify them.

Things that must stay in sync when you change anything:

- `version` in **both** `plugin.json` files, plus the version column in the root README table.
- The `description` string across both `plugin.json` files and both `marketplace.json` files.
- The workflow contract itself: `commands/groundwork.md` (Claude) and `skills/groundwork/SKILL.md` (Codex) express the *same* three-phase workflow for two runtimes. A change to one is almost always a change to both. They differ only at the edges — Claude fans out to real parallel subagents, Codex runs the recon threads within one agent.

## Loader contract

- `marketplace.json` `plugins[].name` must match the `name` in that plugin's `plugin.json`, and the source path must point at the plugin directory.
- A file in `commands/` becomes a slash command named after the *file*, not after any frontmatter field. Frontmatter carries `description` and `argument-hint` (quote the argument hint — an unquoted `<...>` is invalid YAML; that bit us in `3c41ddc`). `$ARGUMENTS` is the user's raw input.
- A file in `agents/` becomes a subagent addressable as `groundwork:<filename>`. Frontmatter carries `description` (this is what the dispatching model reads to pick the agent — write it as selection criteria, not marketing), `tools:` (an allowlist; MCP wildcards like `mcp__context7__*` are valid), and `color:`.
- Codex skills live at `skills/<name>/SKILL.md` with `name` + `description` frontmatter; `plugin.json` points at the directory via `"skills": "./skills/"`.

## Testing a change

There is nothing to run. Verify by installing locally and exercising the workflow:

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

Groundwork is an **extension of `obra/superpowers`, not a replacement**. It does not bundle it. Both entrypoints open with a hard dependency gate: if `brainstorming` or `writing-plans` is unavailable, stop and tell the user to install Superpowers — never substitute another skill or run a reduced form of the workflow. Groundwork deliberately does *not* invoke `using-superpowers` itself; the dependency only needs to be installed.

Several rules in the workflow look redundant but are load-bearing. Don't "simplify" them without understanding why:

- **Phase 1 is a hard gate.** No user-facing output until every recon thread reports. The reason is anchoring: fanning out only pays off when the threads *disagree*, and reacting to the first report turns the later ones into footnotes.
- **Three phases are deliberately separated** — recon (read-only) → brainstorm (`brainstorming`) → plan (`writing-plans`). Phase 3 never happens on the same turn as Phase 2.
- **Skill invocations must be actual tool calls**, not narration. Describing the activity leaves the skill unloaded and collapses the phase.
- **The workflow ends at an accepted plan.** Execution is out of scope by design; it hands off to a Superpowers execution workflow (`subagent-driven-development` or `executing-plans`).
- All three Claude recon agents are read-only by construction and return the same report shape (findings with `file:line` receipts, plus what they could not verify), so Phase 2's collated input is uniform. Keep that shape if you add a fourth.
- Phase 2 prose rules (paths as receipts at the end of a sentence, gloss every internal name, plain words) exist because the output is written for a developer who has never opened the code in question.
