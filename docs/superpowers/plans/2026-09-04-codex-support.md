# Codex Marketplace Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class OpenAI Codex marketplace and Groundwork plugin support while preserving the existing Claude Code marketplace and command.

**Architecture:** Keep Claude's marketplace, command, and custom recon agents intact. Add OpenAI's native `.agents/plugins/marketplace.json`, a `.codex-plugin/plugin.json`, and a Codex-native `groundwork` Agent Skill that reproduces the same three-phase contract using native parallel subagents.

**Tech Stack:** Markdown Agent Skills, Claude plugin manifests, Codex plugin manifests, JSON marketplace catalogs.

**Spec:** `docs/superpowers/specs/2026-09-04-codex-support-design.md`

## Global Constraints

- Claude Code support must remain functional and retain the existing `/groundwork` command and custom recon agents.
- Codex support must use the native `.agents/plugins/marketplace.json` and `.codex-plugin/plugin.json` formats.
- Groundwork must remain a hard-gated extension of Superpowers on both platforms.
- Groundwork must never start planning before all dispatched Phase 1 reconnaissance is accounted for.
- Groundwork must stop after producing an accepted implementation plan; execution remains a Superpowers handoff.
- Version both platform manifests as `1.3.0`.

---

### Task 1: Add native Codex marketplace and plugin manifests

**Files:**
- Create: `.agents/plugins/marketplace.json`
- Create: `plugins/groundwork/.codex-plugin/plugin.json`

**Interfaces:**
- Consumes: repository plugin root `./plugins/groundwork`
- Produces: Codex marketplace entry named `groundwork` and a plugin manifest exposing `./skills/`

- [ ] **Step 1:** Add the repo/team Codex marketplace catalog with explicit availability/authentication policy and Developer Tools category.
- [ ] **Step 2:** Add the native Groundwork Codex plugin manifest with version `1.3.0`, discovery metadata, and the `./skills/` path.
- [ ] **Step 3:** Parse both JSON files and verify marketplace/plugin names and paths agree.

### Task 2: Add the Codex-native Groundwork skill

**Files:**
- Create: `plugins/groundwork/skills/groundwork/SKILL.md`

**Interfaces:**
- Consumes: installed Superpowers `brainstorming` and `writing-plans` skills plus Codex native subagents
- Produces: `$groundwork` workflow with parallel recon, hard Phase 1 barrier, user-aligned brainstorming, and planning handoff

- [ ] **Step 1:** Define skill metadata and the Superpowers hard dependency.
- [ ] **Step 2:** Implement Phase 1 using parallel native subagents with self-contained code, external, and context recon role prompts.
- [ ] **Step 3:** Preserve the barrier: no Phase 2 output until every dispatched subagent is accounted for.
- [ ] **Step 4:** Implement Phase 2 and Phase 3 using Superpowers skills, preserving the current engineering discipline and no-execution boundary.
- [ ] **Step 5:** Review the skill for Claude-only primitives such as `Agent(...)`, `subagent_type`, `AskUserQuestion`, and `$ARGUMENTS`; none should remain.

### Task 3: Version and document both platforms

**Files:**
- Modify: `plugins/groundwork/.claude-plugin/plugin.json`
- Modify: `README.md`
- Modify: `plugins/groundwork/README.md`

**Interfaces:**
- Consumes: the new Codex marketplace/plugin/skill surfaces from Tasks 1-2
- Produces: consistent `1.3.0` release metadata and user-facing Claude/Codex installation and usage docs

- [ ] **Step 1:** Bump the Claude Groundwork manifest to `1.3.0` without changing its existing plugin shape.
- [ ] **Step 2:** Rewrite the root README as a dual-platform marketplace README with separate Claude Code and Codex installation flows.
- [ ] **Step 3:** Update the Groundwork README with platform-specific invocation, installation, and recon implementation notes.
- [ ] **Step 4:** Verify every documented command matches the current platform behavior and every referenced repository path exists.

### Task 4: Verify the complete branch

**Files:**
- Verify only; no new production files expected.

**Interfaces:**
- Consumes: all changes from Tasks 1-3
- Produces: evidence that the PR is internally consistent and Claude support was preserved

- [ ] **Step 1:** Compare the feature branch against `main` and inspect every changed path.
- [ ] **Step 2:** Re-fetch and parse all four marketplace/plugin JSON files from the feature branch.
- [ ] **Step 3:** Confirm the existing Claude command and all three Claude recon-agent files are still present.
- [ ] **Step 4:** Confirm Codex marketplace source path resolves to a plugin containing the declared `./skills/` directory and `groundwork/SKILL.md`.
- [ ] **Step 5:** Open a PR to `main` describing compatibility, installation, and verification limits.
