#!/usr/bin/env python3
"""Structural checks for the Cabinet plugin's roles, workflow and manifests.

Repository-only (see AGENTS.md: the `scripts/` and `tests/` trees are not
shipped to users). Standard library only, no YAML package.

What this exists to catch: a role's `tools:` line is the enforcement surface
for an in-process teammate. If it drifts from the registry in
`cabinet_runtime.profiles`, a role silently gains a capability the money
invariant says it cannot have, and nothing else in the tree notices. The same
applies to a service tool name that no longer exists, a workflow skill missing
the execution order every role loads it for, and a manifest version that
disagrees with the README.

The frontmatter parser here is deliberate. Cabinet's frontmatter is a simple
line-per-key format, not general YAML, so this parser rejects what a real YAML
loader would quietly accept: a duplicate key (last-wins hides the first), an
unquoted value carrying a colon (an argument hint that parses as a mapping), a
malformed tool list.

Run:
    python3 scripts/check-cabinet.py
    python3 scripts/check-cabinet.py --self-test
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "cabinet" / "scripts"))

from cabinet_runtime import profiles, service  # noqa: E402

PLUGIN = "plugins/cabinet"
AGENT_DIR = "%s/agents" % PLUGIN
COMMAND_DIR = "%s/commands" % PLUGIN
SKILL_PATH = "%s/skills/coordination-rules/SKILL.md" % PLUGIN
REFERENCE_DIR = "%s/skills/coordination-rules/references" % PLUGIN

REFERENCES = ("company", "batch", "communication", "recovery", "briefing")

#: Every role in the packaged registry needs a definition, and so does every
#: worker type, even though a worker is launched rather than dispatched.
REQUIRED_ROLES = tuple(profiles.STAFF_AGENT_TYPES) + tuple(profiles.WORKER_TYPES)

#: A staff role holding any of these can run code, change the tree, reach the
#: network on its own, or act on the board outside the scoped executor.
BROAD_TOOL_PREFIXES = ("Bash", "Write", "Edit", "NotebookEdit", "WebFetch",
                       "WebSearch", "mcp__github__")

SKILL_MARKER = 'Skill(skill: "cabinet:coordination-rules")'

TEN_STEPS = (
    "1. Verify company identity, restricted runtime and current lease.",
    "2. Load company context and reconcile live work before proposing new work.",
    "3. Start/register the required staff; hand each its remit and relevant context.",
    "4. Product gathers evidence and proposes a business outcome with exclusions.",
    "5. Engineering defines technical work; QA defines independent acceptance.",
    "6. Delivery prepares the board and dependencies; assistant presents the batch.",
    "7. Owner response grants or declines the frozen scope. Only then dispatch work.",
    "8. Staff resolve in-scope questions through active handoffs and report results.",
    "9. QA verifies the actual resulting revision; Delivery reconciles the board.",
    "10. Assistant gives the completion/session brief and persists the checkpoint.",
)

EVENT_ROWS = (
    "Company starts or a goal/charter changes",
    "Batch proposed",
    "Batch approved",
    "Board changes or a handoff stalls",
    "Worker reports a candidate",
    "Batch completes",
    "New customer evidence arrives",
    "Relevant financial/privacy/design threshold appears",
)

KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
TOOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
QUOTED_RE = re.compile(r'^(".*"|\'.*\')$', re.DOTALL)

AGENT_KEYS = ("name", "description", "tools", "disallowedTools", "model")


class Frontmatter:
    """One parsed frontmatter block, plus the failures found parsing it."""

    def __init__(self, values, order, problems):
        self.values = values
        self.order = order
        self.problems = problems

    def get(self, key, default=""):
        return self.values.get(key, default)


def parse_frontmatter(label, text):
    """Parse Cabinet's line-per-key frontmatter without a YAML package."""
    problems = []
    values = {}
    order = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        problems.append("%s: no frontmatter block (first line must be ---)" % label)
        return Frontmatter(values, order, problems)
    try:
        end = lines.index("---", 1)
    except ValueError:
        problems.append("%s: frontmatter block is never closed" % label)
        return Frontmatter(values, order, problems)

    for number, raw in enumerate(lines[1:end], start=2):
        if not raw.strip():
            continue
        if raw[0].isspace():
            problems.append(
                "%s line %d: continuation lines are not supported; keep one "
                "key per line" % (label, number))
            continue
        key, separator, value = raw.partition(":")
        if not separator:
            problems.append("%s line %d: no key/value separator" % (label, number))
            continue
        key = key.strip()
        value = value.strip()
        if not KEY_RE.match(key):
            problems.append("%s line %d: malformed key %r" % (label, number, key))
            continue
        if key in values:
            problems.append(
                "%s line %d: duplicate key %r; a later value would silently "
                "replace the first" % (label, number, key))
            continue
        if not value:
            problems.append("%s line %d: key %r has no value" % (label, number, key))
            continue
        values[key] = value
        order.append(key)

    return Frontmatter(values, order, problems)


def unquote(value):
    if QUOTED_RE.match(value):
        return value[1:-1]
    return value


def check_quoting(label, key, value, problems):
    """A value carrying a colon must be quoted or the block is not parseable."""
    if QUOTED_RE.match(value):
        return
    if ":" in value:
        problems.append(
            "%s: %s must be quoted because its value contains a colon" % (label, key))


def check_tool_list(label, key, value, problems):
    if value != value.strip():
        problems.append("%s: %s has stray whitespace" % (label, key))
    entries = [part.strip() for part in value.split(",")]
    if any(entry == "" for entry in entries):
        problems.append("%s: %s has an empty entry (a stray or trailing comma)"
                        % (label, key))
        return []
    for entry in entries:
        if not TOOL_RE.match(entry):
            problems.append("%s: %s names a malformed tool %r" % (label, key, entry))
    if value != ", ".join(entries):
        problems.append("%s: %s must be comma-and-space separated" % (label, key))
    return entries


def read_agent(root, role):
    path = root / AGENT_DIR / ("%s.md" % role)
    if not path.exists():
        return None, ["missing role definition %s/%s.md" % (AGENT_DIR, role)]
    label = "%s/%s.md" % (AGENT_DIR, role)
    parsed = parse_frontmatter(label, path.read_text())
    problems = list(parsed.problems)

    for key in AGENT_KEYS:
        if key not in parsed.values:
            problems.append("%s: missing required key %r" % (label, key))

    name = unquote(parsed.get("name"))
    if name and not NAME_RE.match(name):
        problems.append("%s: malformed name %r" % (label, name))
    elif name and name != role:
        problems.append("%s: name %r does not match its filename" % (label, name))

    description = parsed.get("description")
    if description:
        check_quoting(label, "description", description, problems)
        if len(unquote(description)) < 40:
            problems.append("%s: description is too short to route on" % label)

    if parsed.get("model") and unquote(parsed.get("model")) != "inherit":
        problems.append("%s: model must be inherit" % label)

    return parsed, problems


def expected_tools_line(role):
    if role == profiles.CHIEF_ROLE:
        return ", ".join(profiles.CHIEF_TOOLS + profiles.SERVICE_TOOLS)
    if role == "implementer":
        return ", ".join(profiles.IMPLEMENTER_TOOLS)
    if role == "test-runner":
        return ", ".join(profiles.TEST_RUNNER_TOOLS)
    return ", ".join(profiles.STAFF_TOOLS + profiles.STAFF_SERVICE_TOOLS)


def check_roles(root):
    problems = []
    for role in REQUIRED_ROLES:
        parsed, found = read_agent(root, role)
        problems.extend(found)
        if parsed is None:
            continue
        label = "%s/%s.md" % (AGENT_DIR, role)

        tools = parsed.get("tools")
        if not tools:
            continue
        entries = check_tool_list(label, "tools", tools, problems)
        if parsed.get("disallowedTools"):
            check_tool_list(label, "disallowedTools",
                            parsed.get("disallowedTools"), problems)

        expected = expected_tools_line(role)
        if tools != expected:
            problems.append(
                "%s: tools must equal the registry in cabinet_runtime.profiles\n"
                "      expected: %s\n      actual:   %s" % (label, expected, tools))

        is_staff = role in profiles.STAFF_AGENT_TYPES and role != profiles.CHIEF_ROLE
        if is_staff:
            for entry in entries:
                for prefix in BROAD_TOOL_PREFIXES:
                    if entry.startswith(prefix):
                        problems.append(
                            "%s: staff role may not hold %s" % (label, entry))

        if role in profiles.WORKER_TYPES:
            for entry in entries:
                if entry.startswith("mcp__cabinet__"):
                    problems.append(
                        "%s: a worker holds no Cabinet service tool (%s)"
                        % (label, entry))

    return problems


def check_service_tool_names(root):
    """Every Cabinet tool an agent names must exist in the service registry."""
    problems = []
    known = set(service.TOOL_NAMES)
    pattern = re.compile(r"mcp__cabinet__(cabinet_[a-z_]+)")
    for path in sorted((root / AGENT_DIR).glob("*.md")):
        label = "%s/%s" % (AGENT_DIR, path.name)
        for name in sorted(set(pattern.findall(path.read_text()))):
            if name not in known:
                problems.append(
                    "%s: names mcp__cabinet__%s, which the service does not expose"
                    % (label, name))
    return problems


def check_skill(root):
    problems = []
    path = root / SKILL_PATH
    if not path.exists():
        return ["missing workflow skill at %s" % SKILL_PATH]
    text = path.read_text()

    parsed = parse_frontmatter(SKILL_PATH, text)
    problems.extend(parsed.problems)
    if unquote(parsed.get("name")) != "coordination-rules":
        problems.append("%s: name must stay coordination-rules" % SKILL_PATH)
    if parsed.get("description"):
        check_quoting(SKILL_PATH, "description", parsed.get("description"), problems)

    for step in TEN_STEPS:
        if step not in text:
            problems.append("%s: missing execution step %r" % (SKILL_PATH, step))
    for row in EVENT_ROWS:
        if row not in text:
            problems.append("%s: missing event routing row %r" % (SKILL_PATH, row))

    for name in REFERENCES:
        reference = root / REFERENCE_DIR / ("%s.md" % name)
        if not reference.exists():
            problems.append("missing reference file %s/%s.md" % (REFERENCE_DIR, name))
        if "references/%s.md" % name not in text:
            problems.append("%s: does not link references/%s.md" % (SKILL_PATH, name))

    return problems


def check_commands(root):
    problems = []
    directory = root / COMMAND_DIR
    if not directory.is_dir():
        return ["missing command directory %s" % COMMAND_DIR]
    for path in sorted(directory.glob("*.md")):
        label = "%s/%s" % (COMMAND_DIR, path.name)
        text = path.read_text()
        parsed = parse_frontmatter(label, text)
        problems.extend(parsed.problems)
        if not parsed.get("description"):
            problems.append("%s: missing description" % label)
        else:
            check_quoting(label, "description", parsed.get("description"), problems)
        if "argument-hint" in parsed.values:
            hint = parsed.get("argument-hint")
            if not QUOTED_RE.match(hint):
                problems.append(
                    "%s: argument-hint must be quoted; an unquoted hint with a "
                    "colon or bracket does not parse" % label)
        if SKILL_MARKER not in text:
            problems.append(
                "%s: does not load the workflow skill; every command must carry "
                "%s" % (label, SKILL_MARKER))
    return problems


def check_manifests(root):
    problems = []
    claude_path = root / PLUGIN / ".claude-plugin/plugin.json"
    codex_path = root / PLUGIN / ".codex-plugin/plugin.json"
    readme = root / "README.md"
    try:
        claude = json.loads(claude_path.read_text())
    except (OSError, ValueError) as error:
        return ["%s does not parse: %s" % (claude_path.name, error)]
    if codex_path.exists():
        try:
            codex = json.loads(codex_path.read_text())
        except ValueError as error:
            return ["%s does not parse: %s" % (codex_path.name, error)]
        if codex.get("version") != claude.get("version"):
            problems.append("manifest versions disagree: %s vs %s"
                            % (claude.get("version"), codex.get("version")))
        if codex.get("description") != claude.get("description"):
            problems.append("manifest descriptions disagree")

    rows = [line for line in readme.read_text().splitlines()
            if line.startswith("| [cabinet]")]
    if not rows:
        problems.append("README.md has no cabinet row")
    else:
        version = rows[0].split("|")[2].strip()
        if version != claude.get("version"):
            problems.append("README.md lists cabinet %s; the manifest says %s"
                            % (version, claude.get("version")))
    return problems


def check_all(root):
    problems = []
    problems.extend(check_roles(root))
    problems.extend(check_service_tool_names(root))
    problems.extend(check_skill(root))
    problems.extend(check_commands(root))
    problems.extend(check_manifests(root))
    return problems


# --- self-test -------------------------------------------------------------

COPIED = (PLUGIN, "README.md")


def _fixture_root(stack):
    temporary = Path(tempfile.mkdtemp(prefix="cabinet-check-"))
    stack.append(temporary)
    for relative in COPIED:
        source = REPO / relative
        target = temporary / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    return temporary


def _mutate(path, old, new):
    text = path.read_text()
    if old not in text:
        raise AssertionError("self-test fixture text not found in %s" % path)
    path.write_text(text.replace(old, new, 1))


def self_test():
    """Prove the negative cases fail. A check nothing can fail is not a check."""
    stack = []
    failures = []
    try:
        clean = _fixture_root(stack)
        if check_all(clean):
            failures.append("the unmodified tree should pass but did not")

        # 1. A duplicate key: real YAML takes the last one and hides the first.
        root = _fixture_root(stack)
        _mutate(root / AGENT_DIR / "qa.md", "model: inherit",
                "model: inherit\nmodel: opus")
        found = check_all(root)
        if not any("duplicate key" in problem for problem in found):
            failures.append("a duplicate frontmatter key was not rejected")

        # 2. A broad tool on a staff role voids the money invariant.
        root = _fixture_root(stack)
        _mutate(root / AGENT_DIR / "product.md",
                "tools: Read, Grep", "tools: Bash, Read, Grep")
        found = check_all(root)
        if not any("may not hold Bash" in problem for problem in found):
            failures.append("a staff role holding Bash was not rejected")

        # 3. A missing core role.
        root = _fixture_root(stack)
        (root / AGENT_DIR / "engineering.md").unlink()
        found = check_all(root)
        if not any("missing role definition" in problem for problem in found):
            failures.append("a missing core role was not rejected")

        # 4. An unquoted argument hint.
        root = _fixture_root(stack)
        _mutate(root / COMMAND_DIR / "ask.md",
                'argument-hint: "<role> <question>"',
                "argument-hint: <role>: <question>")
        found = check_all(root)
        if not any("argument-hint must be quoted" in problem for problem in found):
            failures.append("an unquoted argument hint was not rejected")

        # 5. A Cabinet tool name the service does not expose.
        root = _fixture_root(stack)
        _mutate(root / AGENT_DIR / "chief-of-staff.md",
                "mcp__cabinet__cabinet_backup", "mcp__cabinet__cabinet_bakcup")
        found = check_all(root)
        if not any("the service does not expose" in problem for problem in found):
            failures.append("an unknown service tool name was not rejected")

        # 6. The workflow skill losing an execution step.
        root = _fixture_root(stack)
        _mutate(root / SKILL_PATH, TEN_STEPS[6], "7. Start whenever it seems fine.")
        found = check_all(root)
        if not any("missing execution step" in problem for problem in found):
            failures.append("a missing execution step was not rejected")

        # 7. A command that no longer loads the workflow.
        root = _fixture_root(stack)
        _mutate(root / COMMAND_DIR / "check.md", SKILL_MARKER, "the usual rules")
        found = check_all(root)
        if not any("does not load the workflow skill" in problem
                   for problem in found):
            failures.append("a command not loading the skill was not rejected")
    finally:
        for temporary in stack:
            shutil.rmtree(temporary, ignore_errors=True)

    if failures:
        print("Cabinet structural check SELF-TEST FAILED:\n")
        for failure in failures:
            print("  - %s" % failure)
        return 1
    print("Cabinet structural check self-test passed (7 negative fixtures).")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()

    problems = check_all(REPO)
    if problems:
        print("Cabinet structural check FAILED:\n")
        for problem in problems:
            print("  - %s" % problem)
        print("\nThe role registry is cabinet_runtime.profiles; the workflow is "
              "%s." % SKILL_PATH)
        return 1

    roles = len(REQUIRED_ROLES)
    commands = len(list((REPO / COMMAND_DIR).glob("*.md")))
    print("Cabinet structural check passed (%d roles, %d commands, %d references)."
          % (roles, commands, len(REFERENCES)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
