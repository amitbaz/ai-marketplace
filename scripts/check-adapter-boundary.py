#!/usr/bin/env python3
"""Structural check for the Groundwork shared-skill / thin-adapter boundary.

The canonical, platform-neutral Groundwork workflow lives in
plugins/groundwork/skills/groundwork/SKILL.md. Platform adapters (Claude Code's
commands/groundwork.md, plus the recon agent definitions) may only carry
orchestration syntax native to their platform.

This script fails when an adapter starts reintroducing the workflow contract:
workflow section headings, platform-neutral rule prose, the Superpowers phase
handoffs, or verbatim passages copied from the canonical skill.

Run: python3 scripts/check-adapter-boundary.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "groundwork"
SKILL = PLUGIN / "skills" / "groundwork" / "SKILL.md"
CLAUDE_COMMAND = PLUGIN / "commands" / "groundwork.md"
AGENT_DIR = PLUGIN / "agents"

# Sections the canonical skill must own. If one disappears from SKILL.md, the
# workflow contract has been moved or lost rather than shared.
REQUIRED_SKILL_MARKERS = [
    "Required dependency — hard gate",
    "Phase 1 — Deep research",
    "Phase 1 barrier",
    "Phase 2 — Discuss and brainstorm",
    "Engineering discipline while converging",
    "Phase 3 — Plan",
    "Platform adapters",
    "brainstorming",
    "writing-plans",
]

# Phrases that mark platform-neutral workflow content. An adapter containing one
# of these is duplicating the canonical skill.
FORBIDDEN_IN_ADAPTERS = [
    "phase 2 —",
    "phase 2 -",
    "phase 3 —",
    "phase 3 -",
    "engineering discipline",
    "make uncertainty visible",
    "smallest complete solution",
    "change boundary tight",
    "observable outcomes",
    "who you are writing for",
    "brainstorming",
    "writing-plans",
    "subagent-driven-development",
    "executing-plans",
    "hand off, don't execute",
]

# The adapter is allowed to name the canonical skill and the plugin install
# string; those matches are stripped before the forbidden-phrase scan.
ADAPTER_ALLOWANCES = [
    "groundwork:groundwork",
    "superpowers@claude-plugins-official",
]

SHINGLE_SIZE = 10
MAX_ADAPTER_LINES = 140

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def normalized_words(text: str) -> list[str]:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.findall(r"[a-z0-9]+", text.lower())


def shingles(words: list[str], size: int = SHINGLE_SIZE) -> set[str]:
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def check_canonical_skill(skill_text: str) -> None:
    for marker in REQUIRED_SKILL_MARKERS:
        if marker.lower() not in skill_text.lower():
            fail(f"{SKILL.relative_to(REPO)}: canonical skill is missing '{marker}'")


def check_claude_adapter(adapter_text: str, skill_text: str) -> None:
    rel = CLAUDE_COMMAND.relative_to(REPO)

    if not re.search(r'Skill\(skill:\s*"groundwork:groundwork"\)', adapter_text):
        fail(f'{rel}: adapter must invoke Skill(skill: "groundwork:groundwork")')

    if "skills/groundwork/SKILL.md" not in adapter_text:
        fail(f"{rel}: adapter must point at skills/groundwork/SKILL.md as the fallback source of truth")

    if "$ARGUMENTS" not in adapter_text:
        fail(f"{rel}: adapter must pass the user's problem through $ARGUMENTS")

    for agent in ("groundwork:recon-code", "groundwork:recon-external", "groundwork:recon-context"):
        if agent not in adapter_text:
            fail(f"{rel}: adapter must keep the {agent} subagent type")

    line_count = len(adapter_text.splitlines())
    skill_lines = len(skill_text.splitlines())
    if line_count > MAX_ADAPTER_LINES:
        fail(f"{rel}: adapter is {line_count} lines (budget {MAX_ADAPTER_LINES}); move workflow prose into the canonical skill")
    if line_count >= skill_lines:
        fail(f"{rel}: adapter ({line_count} lines) is no longer thinner than the canonical skill ({skill_lines} lines)")


def check_forbidden_phrases(path: Path, text: str) -> None:
    rel = path.relative_to(REPO)
    haystack = text.lower()
    for allowed in ADAPTER_ALLOWANCES:
        haystack = haystack.replace(allowed.lower(), " ")
    for phrase in FORBIDDEN_IN_ADAPTERS:
        if phrase in haystack:
            fail(f"{rel}: contains workflow-owned phrase '{phrase}'; that belongs in the canonical skill")


def check_copied_passages(path: Path, text: str, skill_words: list[str]) -> None:
    rel = path.relative_to(REPO)
    overlap = shingles(normalized_words(text)) & shingles(skill_words)
    if overlap:
        sample = sorted(overlap)[0]
        fail(
            f"{rel}: reproduces {len(overlap)} passage(s) of {SHINGLE_SIZE}+ words from the canonical skill, "
            f'starting "{sample}..."'
        )


def check_manifest_sync() -> None:
    claude_plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    codex_plugin = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    claude_market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())

    if claude_plugin["version"] != codex_plugin["version"]:
        fail(
            "plugin.json version mismatch: "
            f"Claude {claude_plugin['version']} vs Codex {codex_plugin['version']}"
        )

    descriptions = {
        ".claude-plugin/plugin.json": claude_plugin["description"],
        ".codex-plugin/plugin.json": codex_plugin["description"],
        "marketplace.json": claude_market["plugins"][0]["description"],
    }
    if len(set(descriptions.values())) != 1:
        fail(f"plugin description drifted across manifests: {descriptions}")

    if codex_plugin.get("skills") != "./skills/":
        fail(".codex-plugin/plugin.json must keep \"skills\": \"./skills/\" so Codex loads the canonical skill")

    if f"| {claude_plugin['version']} |" not in (REPO / "README.md").read_text():
        fail(f"README.md plugin table does not list version {claude_plugin['version']}")


def main() -> int:
    if not SKILL.exists():
        print(f"FAIL: canonical skill missing at {SKILL.relative_to(REPO)}")
        return 1

    skill_text = SKILL.read_text()
    skill_words = normalized_words(skill_text)

    check_canonical_skill(skill_text)
    check_manifest_sync()

    adapters = [CLAUDE_COMMAND, *sorted(AGENT_DIR.glob("*.md"))]
    for path in adapters:
        if not path.exists():
            fail(f"missing adapter file {path.relative_to(REPO)}")
            continue
        text = path.read_text()
        check_forbidden_phrases(path, text)
        check_copied_passages(path, text, skill_words)

    if CLAUDE_COMMAND.exists():
        check_claude_adapter(CLAUDE_COMMAND.read_text(), skill_text)

    if failures:
        print("Groundwork adapter boundary check FAILED:\n")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "\nThe platform-neutral workflow belongs in "
            f"{SKILL.relative_to(REPO)}; adapters carry only platform syntax."
        )
        return 1

    print(f"Groundwork adapter boundary check passed ({len(adapters)} adapter files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
