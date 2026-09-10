"""Structural contract tests for the Cabinet plugin's distribution metadata.

Repository-only checks (see AGENTS.md: the `scripts/` and `tests/` trees are
not shipped to users). Python 3 standard library only, plain `unittest`.

Run:
    python3 -m unittest discover -s tests/cabinet -p test_distribution.py -v
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "plugins/cabinet/agents"
COMMANDS = ROOT / "plugins/cabinet/commands"
CONTRACTS = ROOT / "docs/superpowers/plans/2026-09-09-cabinet-contracts.md"
SKILL = ROOT / "plugins/cabinet/skills/coordination-rules/SKILL.md"
REFERENCES = SKILL.parent / "references"
CHECKER = ROOT / "scripts/check-cabinet.py"

sys.path.insert(0, str(ROOT / "plugins/cabinet/scripts"))

from cabinet_runtime import profiles  # noqa: E402


def tools_line(role):
    """The `tools:` value of one packaged agent, as the frontmatter states it."""
    text = (AGENTS / ("%s.md" % role)).read_text()
    line = next(x for x in text.splitlines() if x.startswith("tools:"))
    return line[len("tools:"):].strip()


class ManifestContract(unittest.TestCase):
    """The advertised version must be the version that is actually shipped."""

    def test_cabinet_table_matches_manifest(self):
        manifest = json.loads(
            (ROOT / "plugins/cabinet/.claude-plugin/plugin.json").read_text()
        )
        row = next(
            line
            for line in (ROOT / "README.md").read_text().splitlines()
            if line.startswith("| [cabinet]")
        )
        version = row.split("|")[2].strip()
        self.assertEqual(version, manifest["version"])

    def test_cabinet_manifests_agree(self):
        claude = json.loads(
            (ROOT / "plugins/cabinet/.claude-plugin/plugin.json").read_text()
        )
        codex = json.loads(
            (ROOT / "plugins/cabinet/.codex-plugin/plugin.json").read_text()
        )
        self.assertEqual(claude["version"], codex["version"])
        self.assertEqual(claude["description"], codex["description"])


class CompanyStaff(unittest.TestCase):
    """The packaged roles are the company's staff, not an advisory panel."""

    def test_all_core_roles_are_packaged(self):
        expected = {"chief-of-staff", "product", "delivery-lead", "engineering", "qa"}
        actual = {p.stem for p in (ROOT / "plugins/cabinet/agents").glob("*.md")}
        self.assertTrue(expected <= actual)

    def test_product_has_no_execution_or_publishing_tools(self):
        text = (ROOT / "plugins/cabinet/agents/product.md").read_text()
        tools = next(line for line in text.splitlines() if line.startswith("tools:"))
        for forbidden in ("Bash", "Write", "Edit", "WebFetch", "mcp__github__*"):
            self.assertNotIn(forbidden, tools)

    def test_every_worker_type_is_packaged(self):
        actual = {p.stem for p in AGENTS.glob("*.md")}
        self.assertTrue(set(profiles.WORKER_TYPES) <= actual)

    def test_no_staff_role_holds_a_broad_tool(self):
        """A staff role that can run a shell or write a file voids the money
        invariant, and one with its own web access can research a purchase."""
        broad = ("Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch",
                 "mcp__github__")
        for role in profiles.STAFF_AGENT_TYPES:
            if role == profiles.CHIEF_ROLE:
                continue
            line = tools_line(role)
            for forbidden in broad:
                self.assertNotIn(forbidden, line,
                                 "%s may not hold %s" % (role, forbidden))

    def test_staff_frontmatter_equals_the_registry(self):
        """The frontmatter is the enforcement surface for an in-process
        teammate, so it must equal the profile registry exactly."""
        expected = ", ".join(profiles.STAFF_TOOLS + profiles.STAFF_SERVICE_TOOLS)
        for role in profiles.STAFF_AGENT_TYPES:
            if role == profiles.CHIEF_ROLE:
                continue
            self.assertEqual(tools_line(role), expected, role)

    def test_chief_frontmatter_equals_the_registry(self):
        expected = ", ".join(profiles.CHIEF_TOOLS + profiles.SERVICE_TOOLS)
        self.assertEqual(tools_line(profiles.CHIEF_ROLE), expected)

    def test_every_staff_file_denies_the_same_six_tools(self):
        """A file keeping the key but dropping five denials would look fine."""
        expected = "Bash, Write, Edit, NotebookEdit, WebFetch, WebSearch"
        for role in profiles.STAFF_AGENT_TYPES:
            text = (AGENTS / ("%s.md" % role)).read_text()
            line = next(x for x in text.splitlines()
                        if x.startswith("disallowedTools:"))
            self.assertEqual(line[len("disallowedTools:"):].strip(), expected, role)

    def test_workers_hold_no_service_tool(self):
        expected = {"implementer": profiles.IMPLEMENTER_TOOLS,
                    "test-runner": profiles.TEST_RUNNER_TOOLS}
        for role, tools in expected.items():
            line = tools_line(role)
            self.assertEqual(line, ", ".join(tools), role)
            self.assertNotIn("mcp__cabinet__", line, role)


class OperatingCommands(unittest.TestCase):
    """The four commands O1 owns are the owner's entry into the company.

    Each assertion here is about a property a reader cannot see by looking at
    one file: that the command exists under the name the contract gives it,
    that it loads the one workflow rather than restating it, that its
    frontmatter parses, that it hands over the *verified* launcher instead of
    inventing an argv, and that nothing in the command set teaches the owner a
    flag that would switch the permission layer off.
    """

    #: The commands task O1 owns. Others in the contract layout belong to
    #: later tasks and are deliberately not asserted present here.
    OWNED = ("company", "batch", "hire", "ask")

    #: Flags and settings that would hand a session authority the launcher and
    #: the profile exist to withhold. None of them belongs in a command.
    BYPASS_TOKENS = (
        "--dangerously-skip-permissions",
        "bypassPermissions",
        "--permission-mode bypass",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        "--permission-prompts none",
    )

    def command(self, name):
        return (COMMANDS / ("%s.md" % name)).read_text()

    def test_the_owned_commands_are_packaged(self):
        for name in self.OWNED:
            self.assertTrue((COMMANDS / ("%s.md" % name)).exists(),
                            "commands/%s.md is missing" % name)

    def test_the_owned_commands_load_the_workflow_skill(self):
        """A command carries native syntax; the workflow lives in the skill.

        `scripts/check-cabinet.py` enforces this across every command. It is
        asserted here too because these four are the ones being written now.
        """

        for name in self.OWNED:
            self.assertIn('Skill(skill: "cabinet:coordination-rules")',
                          self.command(name), name)

    def test_the_owned_commands_quote_their_argument_hint(self):
        """An unquoted hint is invalid YAML and the command silently vanishes."""

        for name in self.OWNED:
            line = next(x for x in self.command(name).splitlines()
                        if x.startswith("argument-hint:"))
            value = line[len("argument-hint:"):].strip()
            self.assertTrue(
                len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'",
                "%s: argument-hint is not quoted: %s" % (name, value))

    def test_company_and_batch_hand_over_the_verified_launcher(self):
        """Only `cabinet-launch` can create a session allowed to write.

        Both commands have to point at that script rather than describing a
        `claude` invocation of their own, because an argv written into prose
        cannot carry the capability handshake and would silently produce an
        ordinary session that then fails every mutation.
        """

        for name in ("company", "batch"):
            self.assertIn("scripts/cabinet-launch", self.command(name), name)

    def test_no_command_teaches_a_bypass_flag(self):
        for path in sorted(COMMANDS.glob("*.md")):
            text = path.read_text()
            for token in self.BYPASS_TOKENS:
                self.assertNotIn(token, text, "%s names %s" % (path.name, token))

    def test_owned_commands_match_the_contract_layout(self):
        """The contract's file list is the name each command must ship under.

        Parsed from the plan rather than restated, so a rename in one place
        without the other fails here instead of at install time.
        """

        block = CONTRACTS.read_text().split("commands/", 1)[1]
        listed = set()
        for line in block.splitlines()[:6]:
            for word in line.replace(",", " ").split():
                if word.endswith(".md"):
                    listed.add(word[:-len(".md")])
            if line.strip().startswith("scripts/"):
                break
        for name in self.OWNED:
            self.assertIn(name, listed,
                          "the contract layout does not name commands/%s.md"
                          % name)

    def test_ask_offers_the_whole_role_registry(self):
        """Every dispatchable staff type, not the six advisory roles alone."""

        text = self.command("ask")
        for role in profiles.STAFF_AGENT_TYPES:
            if role == profiles.CHIEF_ROLE:
                continue
            self.assertIn(role, text, role)

    def test_hire_migrates_through_the_runtime(self):
        """Setup is an owner grant obtained through a dialog, not a staff edit."""

        text = self.command("hire")
        for marker in ("cabinet_setup", "cabinet_doctor"):
            self.assertIn(marker, text, marker)


class WorkflowSkill(unittest.TestCase):
    """The single workflow entrypoint has to carry the operating contract."""

    def test_skill_carries_the_ten_step_execution_order(self):
        text = SKILL.read_text()
        for step in (
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
        ):
            self.assertIn(step, text)

    def test_skill_carries_the_event_routing_table(self):
        text = SKILL.read_text()
        for event in (
            "Company starts or a goal/charter changes",
            "Batch proposed",
            "Batch approved",
            "Board changes or a handoff stalls",
            "Worker reports a candidate",
            "Batch completes",
            "New customer evidence arrives",
            "Relevant financial/privacy/design threshold appears",
        ):
            self.assertIn(event, text)

    def test_skill_carries_the_active_handoff_lifecycle(self):
        """An advisory panel routes an observation to a notebook and waits for
        the next run. Staff record, send, and require an acknowledgment."""
        text = SKILL.read_text()
        # Match the state diagram itself. Bare substrings would survive its
        # deletion: "sent" also occurs inside "present" and "sentence".
        self.assertIn("recorded → sent → acknowledged → resolved", text)
        for terminal in ("↘ failed", "↘ superseded"):
            self.assertIn(terminal, text)
        self.assertIn("cabinet_record_handoff", text)
        self.assertIn("SendMessage", text)

    def test_notebook_routing_is_not_the_only_handoff_mechanism(self):
        """`## FOR <role>` was the whole of the advisory return channel. It may
        survive as an observation channel; it may not be the handoff."""
        text = SKILL.read_text()
        self.assertIn("## HANDOFFS", text)
        self.assertIn("## VERDICT", text)
        if "## FOR <role>" in text:
            self.assertLess(text.index("## HANDOFFS"), text.index("## FOR <role>"))

    def test_owner_batch_approval_is_not_filtered_by_reversibility(self):
        """The one-way-door filter governs everything else a role raises. It
        must not be readable as a way past this boundary."""
        flat = " ".join(SKILL.read_text().split())
        self.assertIn("Owner batch approval is mandatory even when "
                      "implementation would be reversible.", flat)

    def test_skill_carries_the_disagreement_rule(self):
        text = SKILL.read_text().lower()
        for clause, owner in (("technical means", "engineering"),
                              ("desired behavior", "product"),
                              ("execution sequence", "delivery"),
                              ("evidence validity", "qa")):
            self.assertIn(clause, text)
            line = next(x for x in text.splitlines() if clause in x)
            self.assertIn(owner, line, clause)

    def test_reference_files_exist_and_are_linked(self):
        text = SKILL.read_text()
        for name in ("company", "batch", "communication", "recovery", "briefing"):
            path = REFERENCES / ("%s.md" % name)
            self.assertTrue(path.exists(), str(path))
            self.assertIn("references/%s.md" % name, text)


class AdvertisedEvidence(unittest.TestCase):
    """What the service checks, the schema and the prose must both name.

    A required claim that only appears when a caller is refused teaches the
    contract by failure. These tests make the three places move together.
    """

    def required(self):
        from cabinet_runtime.service import REQUIRED_EVIDENCE

        return REQUIRED_EVIDENCE

    def test_the_tool_schema_names_every_required_claim(self):
        from cabinet_runtime.service import TOOL_SPECS

        described = TOOL_SPECS["update_handoff"][1]["properties"]["evidence"]
        text = described["description"]
        for transition, fields in self.required().items():
            self.assertIn(transition, text)
            for field in fields:
                self.assertIn(field, text, "%s.%s" % (transition, field))

    def test_the_communication_reference_names_every_required_claim(self):
        text = (REFERENCES / "communication.md").read_text()
        for transition, fields in self.required().items():
            self.assertIn("`%s`" % transition, text)
            for field in fields:
                self.assertIn("`%s`" % field, text,
                              "%s.%s" % (transition, field))

    def test_the_chief_names_every_required_claim(self):
        text = (AGENTS / "chief-of-staff.md").read_text()
        for transition, fields in self.required().items():
            for field in fields:
                self.assertIn("`%s`" % field, text,
                              "%s.%s" % (transition, field))

    def test_recorded_is_not_advertised_as_a_callable_transition(self):
        from cabinet_runtime.service import HANDOFF_TRANSITIONS, TOOL_SPECS

        enumerated = TOOL_SPECS["update_handoff"][1]["properties"]
        self.assertNotIn("recorded", enumerated["transition"]["enum"])
        self.assertNotIn("recorded", HANDOFF_TRANSITIONS)


class RepositoryChecker(unittest.TestCase):
    """`scripts/check-cabinet.py` is the mechanism behind these claims."""

    def run_checker(self, *args):
        return subprocess.run([sys.executable, str(CHECKER), *args],
                              cwd=str(ROOT), capture_output=True, text=True)

    def test_checker_passes_on_this_tree(self):
        done = self.run_checker()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_checker_self_test_passes(self):
        done = self.run_checker("--self-test")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
