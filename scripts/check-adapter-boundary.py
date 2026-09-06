#!/usr/bin/env python3
"""Structural check for the Groundwork shared-skill / thin-adapter boundary.

The canonical, platform-neutral Groundwork workflow lives in
plugins/groundwork/skills/groundwork/SKILL.md. Platform adapters (Claude Code's
commands/groundwork.md, plus the recon agent definitions) may only carry
orchestration syntax native to their platform.

This script fails when an adapter starts reintroducing the workflow contract:
workflow section headings, platform-neutral rule prose, the Superpowers phase
handoffs, or verbatim passages copied from the canonical skill.

The same boundary applies to the plugin's executables and hook definitions
(plugins/*/scripts/, plugins/*/hooks/). A script carries mechanism — paths,
parsing, I/O — and points at the canonical skill for the workflow instead of
restating it. Scripts are held to a slightly narrower phrase list than adapters
because a script may legitimately reference an upstream skill as data.

Run: python3 scripts/check-adapter-boundary.py
     python3 scripts/check-adapter-boundary.py --self-test
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
import tempfile
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

# Bare skill names. An adapter must not name them — invoking a phase is the
# canonical skill's job. A script may: the metrics collector reads
# subagent-driven-development's workspace directory, and naming a directory is
# referencing a skill as data, not restating its workflow.
SKILL_NAME_REFERENCES = {
    "brainstorming",
    "writing-plans",
    "subagent-driven-development",
    "executing-plans",
}

FORBIDDEN_IN_SCRIPTS = [p for p in FORBIDDEN_IN_ADAPTERS if p not in SKILL_NAME_REFERENCES]

# The adapter is allowed to name the canonical skill and the plugin install
# string; those matches are stripped before the forbidden-phrase scan.
ADAPTER_ALLOWANCES = [
    "groundwork:groundwork",
    "superpowers@claude-plugins-official",
]

# Directories inside a plugin that hold executables and hook definitions rather
# than workflow prose. Everything under them is scanned.
PLUGIN_SCRIPT_DIRS = ("scripts", "hooks")

SHINGLE_SIZE = 10
MAX_ADAPTER_LINES = 140

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


@contextlib.contextmanager
def captured_failures():
    """Run checks against a private failure list (used by --self-test)."""
    global failures
    saved = failures
    failures = []
    try:
        yield failures
    finally:
        failures = saved


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


def check_forbidden_phrases(path: Path, text: str, phrases: list[str], root: Path = REPO) -> None:
    rel = path.relative_to(root)
    haystack = text.lower()
    for allowed in ADAPTER_ALLOWANCES:
        haystack = haystack.replace(allowed.lower(), " ")
    for phrase in phrases:
        if phrase in haystack:
            fail(f"{rel}: contains workflow-owned phrase '{phrase}'; that belongs in the canonical skill")


def check_copied_passages(path: Path, text: str, skill_words: list[str], root: Path = REPO) -> None:
    rel = path.relative_to(root)
    overlap = shingles(normalized_words(text)) & shingles(skill_words)
    if overlap:
        sample = sorted(overlap)[0]
        fail(
            f"{rel}: reproduces {len(overlap)} passage(s) of {SHINGLE_SIZE}+ words from the canonical skill, "
            f'starting "{sample}..."'
        )


def plugin_script_files(root: Path = REPO) -> list[Path]:
    """Every file shipped under a plugin's scripts/ or hooks/ directory.

    Repo-level checks under the root scripts/ directory are deliberately not
    scanned: they are development tooling, not plugin content, and this file
    itself has to spell out the forbidden phrases.
    """
    found: list[Path] = []
    for plugin_dir in sorted((root / "plugins").glob("*")):
        if not plugin_dir.is_dir():
            continue
        for name in PLUGIN_SCRIPT_DIRS:
            for path in sorted((plugin_dir / name).rglob("*")):
                if path.is_file() and not path.name.startswith("."):
                    found.append(path)
    return found


def check_plugin_scripts(skill_words: list[str], root: Path = REPO) -> list[Path]:
    scanned: list[Path] = []
    for path in plugin_script_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: nothing to read prose out of
        scanned.append(path)
        check_forbidden_phrases(path, text, FORBIDDEN_IN_SCRIPTS, root)
        check_copied_passages(path, text, skill_words, root)
    return scanned


def self_test(skill_words: list[str]) -> int:
    """Prove the script rule fires, using fixtures in a temp directory."""
    problems: list[str] = []

    def expect(condition: bool, description: str) -> None:
        if not condition:
            problems.append(description)

    # A window of canonical-skill prose that carries no forbidden phrase, so the
    # copied-passage rule is tested in isolation from the phrase rule.
    copied = ""
    for i in range(len(skill_words) - SHINGLE_SIZE - 1):
        window = " ".join(skill_words[i : i + SHINGLE_SIZE + 2])
        if not any(p.strip(" —-") in window for p in FORBIDDEN_IN_SCRIPTS):
            copied = window
            break
    expect(bool(copied), "could not build a copied-passage fixture from the canonical skill")

    cases = [
        (
            "scripts/harvest.py",
            "#!/usr/bin/env python3\n# Copy subagent transcripts before the OS deletes them.\nimport json, os\n",
            None,
            "a mechanism-only script must pass",
        ),
        (
            "scripts/collect.py",
            '# Read the subagent-driven-development workspace at .superpowers/sdd/.\nimport json\n',
            None,
            "a script may name an upstream skill as data",
        ),
        (
            "scripts/harvest.py",
            "# Apply the engineering discipline: keep the change boundary tight.\nimport json\n",
            "workflow-owned phrase",
            "workflow prose in a script must fail",
        ),
        (
            "hooks/hooks.json",
            '{"note": "make uncertainty visible"}\n',
            "workflow-owned phrase",
            "workflow prose in a hook definition must fail",
        ),
        (
            "scripts/harvest.py",
            f"# {copied}\nimport json\n",
            "reproduces",
            "a passage copied from the canonical skill must fail",
        ),
    ]

    for rel, body, expected, description in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "plugins" / "groundwork" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            # Prose files elsewhere in the plugin are not script artifacts.
            readme = root / "plugins" / "groundwork" / "README.md"
            readme.write_text("Engineering discipline: make uncertainty visible.\n", encoding="utf-8")

            with captured_failures() as found:
                scanned = check_plugin_scripts(skill_words, root)

            expect(target in scanned, f"{description}: fixture {rel} was not scanned")
            expect(readme not in scanned, f"{description}: README.md must not be scanned as a script")
            if expected is None:
                expect(not found, f"{description}: unexpected failures {found}")
            else:
                expect(
                    any(expected in f for f in found),
                    f"{description}: expected a '{expected}' failure, got {found}",
                )

    # The repo's own checks are development tooling, not plugin content.
    expect(
        all("plugins/" in str(p.relative_to(REPO)) for p in plugin_script_files()),
        "plugin script scan must stay inside plugins/",
    )

    if problems:
        print("Adapter boundary self-test FAILED:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"Adapter boundary self-test passed ({len(cases)} script-rule fixtures).")
    return 0


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


def main(argv: list[str]) -> int:
    if not SKILL.exists():
        print(f"FAIL: canonical skill missing at {SKILL.relative_to(REPO)}")
        return 1

    skill_text = SKILL.read_text()
    skill_words = normalized_words(skill_text)

    if "--self-test" in argv:
        return self_test(skill_words)

    check_canonical_skill(skill_text)
    check_manifest_sync()

    adapters = [CLAUDE_COMMAND, *sorted(AGENT_DIR.glob("*.md"))]
    for path in adapters:
        if not path.exists():
            fail(f"missing adapter file {path.relative_to(REPO)}")
            continue
        text = path.read_text()
        check_forbidden_phrases(path, text, FORBIDDEN_IN_ADAPTERS)
        check_copied_passages(path, text, skill_words)

    if CLAUDE_COMMAND.exists():
        check_claude_adapter(CLAUDE_COMMAND.read_text(), skill_text)

    scripts = check_plugin_scripts(skill_words)

    if failures:
        print("Groundwork adapter boundary check FAILED:\n")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "\nThe platform-neutral workflow belongs in "
            f"{SKILL.relative_to(REPO)}; adapters and scripts carry only platform syntax and mechanism."
        )
        return 1

    print(
        f"Groundwork adapter boundary check passed "
        f"({len(adapters)} adapter files, {len(scripts)} plugin script files checked)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
