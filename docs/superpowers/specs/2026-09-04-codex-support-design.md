# Codex Marketplace Support Design

## Goal

Make `amitbaz/ai-marketplace` a first-class marketplace for both Claude Code and OpenAI Codex without breaking the existing Claude installation or `/groundwork` workflow.

## Architecture

Keep the existing Claude surfaces unchanged in shape:

- `.claude-plugin/marketplace.json` remains the Claude marketplace catalog.
- `plugins/groundwork/.claude-plugin/plugin.json` remains the Claude plugin manifest.
- `plugins/groundwork/commands/groundwork.md` and the three custom Claude recon agents continue to power `/groundwork`.

Add native Codex surfaces alongside them:

- `.agents/plugins/marketplace.json` is the repo/team Codex marketplace catalog.
- `plugins/groundwork/.codex-plugin/plugin.json` is the native Codex plugin manifest.
- `plugins/groundwork/skills/groundwork/SKILL.md` is the Codex-native Groundwork workflow.

The two platform adapters preserve the same workflow contract rather than trying to share platform-specific orchestration syntax.

## Groundwork workflow contract

Both implementations keep the same three phases:

1. **Deep research.** Run only the reconnaissance threads relevant to the problem, run independent threads in parallel, and block until every dispatched thread is accounted for.
2. **Discuss and brainstorm.** Invoke Superpowers' `brainstorming` skill, explain the evidence in plain language, propose alternatives, surface uncertainty, and get user alignment.
3. **Plan.** Only after the user greenlights the approach, invoke Superpowers' `writing-plans` skill, produce a verifiable implementation plan, then stop and hand off to a Superpowers execution workflow.

Codex uses native subagents with self-contained role prompts instead of Claude's `Agent(...)` calls and custom `subagent_type` values. The roles remain code recon, external recon, and prior-context recon.

## Dependency contract

Groundwork remains an extension of `obra/superpowers`; it does not bundle or replace Superpowers. Both platform implementations hard-stop when the required Superpowers skills are unavailable.

Claude users install Superpowers from Anthropic's official plugin marketplace. Codex users install Superpowers from the official Codex plugin marketplace before installing Groundwork.

## Marketplace and plugin metadata

The Codex marketplace follows OpenAI's repo/team format under `.agents/plugins/marketplace.json`, pointing to `./plugins/groundwork` as a local plugin source. The Groundwork plugin uses `.codex-plugin/plugin.json` and exposes `./skills/`.

The release version is bumped from `1.2.1` to `1.3.0` on both platform manifests because Codex support is a backwards-compatible feature addition.

## Documentation

The root README becomes platform-neutral and documents installation for Claude Code and Codex. The Groundwork README documents platform-specific invocation and explains that Claude retains color-coded custom recon agents while Codex uses native subagents with the same semantic roles.

## Verification

Because this repository contains manifests, Markdown commands, agents, and skills rather than executable application code, verification focuses on:

- parsing all marketplace/plugin JSON as valid JSON;
- confirming marketplace entries and manifest names match `groundwork`;
- confirming every declared local path exists in the branch;
- confirming Claude files remain present and only the Claude plugin version changes;
- reviewing the branch diff for accidental unrelated changes.
