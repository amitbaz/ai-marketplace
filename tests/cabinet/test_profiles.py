"""Contract tests for restricted launch profiles and the subprocess adapter.

Repository-only suite (see AGENTS.md). Python 3 standard library, plain
`unittest`, one temporary directory per test. Three guarantees are asserted
here rather than described anywhere else:

* a profile that would hand a role something it must not have is refused by
  `verify_profile` before any launcher could act on it,
* the command line that actually runs is checked against the profile it came
  from, so tampering with argv alone does not get past the refusals, and
* `run_argv` never inherits the parent environment, never uses a shell, and
  never turns an ambiguous timeout into a silent retry.

The temporary machine mirrors the real installed layout: the plugin under
`~/.claude/plugins/...`, the company's views and private runtime under
`~/.cabinet/repos/<slug>/`. An artificial layout would hide whether the chief
can be built at all.

Run:
    PYTHONPATH=plugins/cabinet/scripts:tests/cabinet \
        python3 -m unittest discover -s tests/cabinet -p test_profiles.py -v
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cabinet_runtime import contracts, processes, profiles
from cabinet_runtime.errors import CabinetError

REPO = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO / "plugins" / "cabinet"
HOOK = PLUGIN_ROOT / "scripts" / "cabinet-hook"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
CHIEF_AGENT = PLUGIN_ROOT / "agents" / "chief-of-staff.md"

SESSION_ID = "6f1d0f1a-0c1a-4a8e-9a5f-9a2b3c4d5e6f"
SLUG = "amitbaz-cabinet"


def load_hook():
    """Import the packaged hook as a module without running its entry point."""

    loader = importlib.machinery.SourceFileLoader("cabinet_hook", str(HOOK))
    spec = importlib.util.spec_from_loader("cabinet_hook", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeRunner:
    """Stand-in for `subprocess.run` that records exactly how it was called."""

    def __init__(self, returncode=0, stdout="", stderr="", raises=None):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.raises = raises
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": argv, "kwargs": kwargs})
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode,
                                           self.stdout, self.stderr)


class ProfileCase(unittest.TestCase):
    """A temporary machine laid out the way a real one is."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = root / "home"
        # An installed Claude Code plugin lives under the user's ~/.claude.
        self.plugin = (self.home / ".claude" / "plugins" / "marketplaces"
                       / "amitbaz" / "plugins" / "cabinet")
        self.claude_private = self.home / ".claude" / "projects"
        company = self.home / ".cabinet" / "repos" / SLUG
        self.views = company / "views"
        self.runtime = company / "runtime"
        self.worktree = root / "work" / "cabinet-W001"
        self.bin = self.home / ".superset" / "bin"
        for path in (self.plugin, self.claude_private, self.views,
                     self.runtime, self.worktree, self.bin):
            path.mkdir(parents=True)
        (self.plugin / "scripts").mkdir()
        self.claude = self.bin / "claude"
        self.claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.mcp_config = self.runtime / "cabinet.mcp.json"
        self.mcp_config.write_text("{}", encoding="utf-8")
        self.settings_path = self.runtime / "chief-settings.json"
        self.settings_path.write_text("{}", encoding="utf-8")
        self.registry = self.runtime / "peers.json"
        self.registry.write_text('{"peers": []}', encoding="utf-8")

    # --- profile construction helpers ------------------------------------

    def chief_workspace(self, **overrides):
        workspace = {
            "assignment": "amitbaz-cabinet",
            "path": str(self.worktree),
            "claude_path": str(self.claude),
            "plugin_root": str(self.plugin),
            "mcp_config": str(self.mcp_config),
            "settings_path": str(self.settings_path),
            "session_id": SESSION_ID,
            "peer_registry": str(self.registry),
        }
        workspace.update(overrides)
        return workspace

    def worker_workspace(self, **overrides):
        workspace = {
            "assignment": "W001",
            "path": str(self.worktree),
            "claude_path": str(self.claude),
            "plugin_root": str(self.plugin),
            "chief_name": "cabinet-chief-amitbaz-cabinet",
            "peer_registry": str(self.registry),
        }
        workspace.update(overrides)
        return workspace

    def check_profiles(self):
        return [{"profile_id": "local-unit",
                 "argv": ["python3", "-m", "unittest"],
                 "env": {"PYTHONHASHSEED": "0"}}]

    def chief(self, **overrides):
        options = {}
        for key in ("include_service_tools_in_tools_flag",):
            if key in overrides:
                options[key] = overrides.pop(key)
        return profiles.build_profile("chief-of-staff",
                                      self.chief_workspace(**overrides),
                                      str(self.views), [], home=str(self.home),
                                      **options)

    def staff(self, role="qa"):
        return profiles.build_profile(
            role, {"plugin_root": str(self.plugin)}, str(self.views), [],
            home=str(self.home))

    def worker(self, role="implementer", check_profiles=None, **overrides):
        if check_profiles is None:
            check_profiles = self.check_profiles() if role == "test-runner" else []
        return profiles.build_profile(role, self.worker_workspace(**overrides),
                                      str(self.views), check_profiles,
                                      home=str(self.home))

    def refuse(self, mutated, code):
        """Assert `verify_profile` refuses a plain profile with `code`."""

        with self.assertRaises(CabinetError) as caught:
            profiles.verify_profile(mutated)
        self.assertEqual(caught.exception.code, code)
        return caught.exception


# --- staff and chief tool sets ---------------------------------------------

class StaffProfileTest(ProfileCase):
    def test_chief_tool_set_and_argv_are_exact(self):
        profile = self.chief()
        self.assertEqual(profile["kind"], "chief")
        self.assertEqual(list(profile["tools"]),
                         ["Read", "Grep", "Glob", "Skill", "Agent",
                          "SendMessage", "ListAgents"])
        argv = list(profile["argv"])
        self.assertEqual(argv[0], str(self.claude))
        self.assertIn("--restricted", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--mcp-config") + 1], str(self.mcp_config))
        self.assertEqual(argv[argv.index("--settings") + 1], str(self.settings_path))
        self.assertEqual(argv[argv.index("--plugin-dir") + 1], str(self.plugin))
        self.assertEqual(argv[argv.index("--agent") + 1], "cabinet:chief-of-staff")
        self.assertEqual(argv[argv.index("--tools") + 1],
                         "Read,Grep,Glob,Skill,Agent,SendMessage,ListAgents")
        self.assertEqual(argv[argv.index("--session-id") + 1], SESSION_ID)
        self.assertEqual(argv[argv.index("--name") + 1],
                         "cabinet-chief-amitbaz-cabinet")
        self.assertTrue(all(isinstance(word, str) for word in argv))
        profiles.verify_profile(profile)

    def test_the_chief_can_be_built_for_the_installed_layout(self):
        # The plugin sits under ~/.claude and the views under ~/.cabinet. Both
        # trees hold private material, and the chief still has to read these.
        profile = self.chief()
        self.assertEqual(list(profile["add_dirs"]),
                         [str(self.views), str(self.plugin)])
        self.assertTrue(str(self.plugin).startswith(str(self.home / ".claude")))
        self.assertTrue(str(self.views).startswith(str(self.home / ".cabinet")))

    def test_chief_name_is_never_a_bare_role_name(self):
        # F1 recorded a name collision hazard: a bare name resolved to a
        # cross-session peer rather than the in-process agent.
        name = self.chief()["session_name"]
        self.assertNotIn(name, profiles.STAFF_AGENT_TYPES)
        self.assertTrue(name.startswith("cabinet-chief-"))

    def test_chief_holds_every_service_tool(self):
        profile = self.chief()
        self.assertEqual(tuple(profile["service_tools"]), profiles.SERVICE_TOOLS)
        for name in profile["service_tools"]:
            self.assertTrue(name.startswith("mcp__cabinet__cabinet_"))

    def test_every_staff_role_has_the_same_read_only_tool_set(self):
        for role in profiles.STAFF_AGENT_TYPES:
            if role == "chief-of-staff":
                continue
            with self.subTest(role=role):
                profile = self.staff(role)
                self.assertEqual(profile["kind"], "staff")
                self.assertEqual(list(profile["tools"]),
                                 ["Read", "Grep", "Glob", "Skill",
                                  "SendMessage", "ListAgents"])
                self.assertEqual(tuple(profile["service_tools"]),
                                 profiles.STAFF_SERVICE_TOOLS)
                self.assertEqual(tuple(profile["argv"]), ())
                self.assertEqual(tuple(profile["mcp_servers"]), ())
                profiles.verify_profile(profile)

    def test_staff_service_tools_are_the_read_only_slice(self):
        for name in profiles.STAFF_SERVICE_TOOLS:
            self.assertIn(name, profiles.SERVICE_TOOLS)
        for name in ("mcp__cabinet__cabinet_execute_action",
                     "mcp__cabinet__cabinet_request_owner_approval",
                     "mcp__cabinet__cabinet_propose_batch"):
            self.assertNotIn(name, profiles.STAFF_SERVICE_TOOLS)

    def test_staff_may_not_dispatch_its_own_workers(self):
        self.assertNotIn("Agent", self.staff("engineering")["tools"])

    def test_staff_profile_carrying_a_code_tool_is_refused(self):
        for tool in ("Bash", "Edit", "Write", "NotebookEdit", "WebFetch",
                     "WebSearch", "Browser", "BillingUpdate", "Deploy",
                     "mcp__github__issue_write"):
            with self.subTest(tool=tool):
                mutated = profiles.plain(self.staff())
                mutated["tools"] = list(mutated["tools"]) + [tool]
                self.refuse(mutated, "PROFILE_TOOLS_FORBIDDEN")

    def test_staff_profile_carrying_a_writing_service_tool_is_refused(self):
        mutated = profiles.plain(self.staff())
        mutated["service_tools"] = list(profiles.STAFF_SERVICE_TOOLS) + [
            "mcp__cabinet__cabinet_execute_action"]
        self.refuse(mutated, "PROFILE_TOOLS_FORBIDDEN")

    def test_unknown_role_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            profiles.build_profile("general-purpose", self.worker_workspace(),
                                   str(self.views), [], home=str(self.home))
        self.assertEqual(caught.exception.code, "ROLE_UNKNOWN")

    def test_service_tools_can_be_added_to_the_tools_flag(self):
        # F4b's live smoke decides whether --tools also gates MCP tool names.
        default = self.chief()
        widened = self.chief(include_service_tools_in_tools_flag=True)
        argv = list(widened["argv"])
        value = argv[argv.index("--tools") + 1]
        self.assertTrue(value.startswith(
            "Read,Grep,Glob,Skill,Agent,SendMessage,ListAgents,"))
        for name in profiles.SERVICE_TOOLS:
            self.assertIn(name, value.split(","))
        self.assertNotEqual(default["digest"], widened["digest"])
        profiles.verify_profile(widened)


# --- worker isolation -------------------------------------------------------

class WorkerProfileTest(ProfileCase):
    def test_implementer_edits_only_inside_its_worktree(self):
        profile = self.worker("implementer")
        self.assertEqual(profile["kind"], "worker")
        self.assertEqual(list(profile["tools"]),
                         ["Read", "Edit", "Write", "Grep", "Glob",
                          "SendMessage", "ListAgents"])
        self.assertEqual(list(profile["add_dirs"]), [str(self.worktree)])
        self.assertNotIn("Bash", profile["tools"])
        profiles.verify_profile(profile)

    def test_test_runner_has_bash_and_carries_its_approved_checks(self):
        profile = self.worker("test-runner")
        self.assertIn("Bash", profile["tools"])
        self.assertEqual([item["profile_id"] for item in profile["check_profiles"]],
                         ["local-unit"])
        profiles.verify_profile(profile)

    def test_worker_never_sees_the_service_or_any_mcp_server(self):
        profile = self.worker()
        self.assertEqual(tuple(profile["service_tools"]), ())
        self.assertEqual(tuple(profile["mcp_servers"]), ())
        argv = list(profile["argv"])
        self.assertIn("--strict-mcp-config", argv)
        self.assertNotIn("--mcp-config", argv)

    def test_worker_exposing_a_service_tool_is_refused(self):
        mutated = profiles.plain(self.worker())
        mutated["service_tools"] = ["mcp__cabinet__cabinet_execute_action"]
        self.refuse(mutated, "PROFILE_TOOLS_FORBIDDEN")

    def test_worker_declaring_an_outside_mcp_server_is_refused(self):
        mutated = profiles.plain(self.worker())
        mutated["mcp_servers"] = ["github"]
        self.refuse(mutated, "PROFILE_MCP_FORBIDDEN")

    def test_chief_may_declare_only_the_cabinet_server(self):
        self.assertEqual(tuple(self.chief()["mcp_servers"]), ("cabinet",))
        mutated = profiles.plain(self.chief())
        mutated["mcp_servers"] = ["cabinet", "github"]
        self.refuse(mutated, "PROFILE_MCP_FORBIDDEN")

    def test_worker_denies_edits_to_plugin_files_and_public_context(self):
        profile = self.worker()
        deny = list(profile["deny"])
        for tool in ("Edit", "Write", "NotebookEdit"):
            self.assertIn("%s(%s/**)" % (tool, self.plugin), deny)
            self.assertIn("%s(%s/**)" % (tool, self.views), deny)
        mutated = profiles.plain(profile)
        mutated["deny"] = [rule for rule in deny if str(self.plugin) not in rule]
        mutated["settings"]["permissions"]["deny"] = list(mutated["deny"])
        mutated["argv"] = list(profiles.build_argv(mutated))
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")


# --- what a session may read ------------------------------------------------

class CredentialBoundaryTest(ProfileCase):
    def test_the_company_runtime_is_never_a_readable_directory(self):
        mutated = profiles.plain(self.worker())
        mutated["add_dirs"] = [str(self.runtime)]
        self.refuse(mutated, "PROFILE_CREDENTIALS_EXPOSED")

    def test_a_runtime_under_any_company_slug_is_covered(self):
        other = self.home / ".cabinet" / "repos" / "someone-else" / "runtime"
        other.mkdir(parents=True)
        mutated = profiles.plain(self.worker())
        mutated["add_dirs"] = [str(other / "backups")]
        self.refuse(mutated, "PROFILE_CREDENTIALS_EXPOSED")

    def test_the_private_parts_of_claude_home_are_refused(self):
        for name in (".claude/projects", ".claude/sessions",
                     ".claude/.credentials.json", ".claude/shell-snapshots",
                     ".ssh", ".aws", ".config/gh"):
            with self.subTest(name=name):
                exposed = self.home / name
                exposed.parent.mkdir(parents=True, exist_ok=True)
                mutated = profiles.plain(self.worker())
                mutated["add_dirs"] = list(mutated["add_dirs"]) + [str(exposed)]
                self.refuse(mutated, "PROFILE_CREDENTIALS_EXPOSED")

    def test_the_docker_socket_is_refused(self):
        mutated = profiles.plain(self.worker())
        mutated["add_dirs"] = list(mutated["add_dirs"]) + ["/var/run/docker.sock"]
        self.refuse(mutated, "PROFILE_CREDENTIALS_EXPOSED")

    def test_claude_home_is_denied_whole_when_the_plugin_is_elsewhere(self):
        elsewhere = Path(self.tmp.name) / "checkout" / "plugins" / "cabinet"
        elsewhere.mkdir(parents=True)
        paths = profiles.credential_paths(str(self.home), str(elsewhere))
        self.assertIn(str(self.home / ".claude"), paths)
        paths = profiles.credential_paths(str(self.home), str(self.plugin))
        self.assertNotIn(str(self.home / ".claude"), paths)
        self.assertIn(str(self.home / ".claude" / "projects"), paths)

    def test_deny_rules_cover_the_runtime_and_every_credential_path(self):
        deny = list(self.worker()["deny"])
        creds = profiles.credential_paths(str(self.home), str(self.plugin))
        self.assertIn("%s/.cabinet/**/runtime" % self.home, creds)
        for path in creds:
            with self.subTest(path=path):
                for tool in ("Read", "Edit", "Write", "NotebookEdit"):
                    # The bare form is the only one that can match a file; the
                    # glob form is the only one that can match a directory's
                    # contents. Every credential path carries both.
                    self.assertIn("%s(%s)" % (tool, path), deny)
                    self.assertIn("%s(%s/**)" % (tool, path), deny)

    def test_a_credential_file_is_denied_by_a_rule_that_can_match_it(self):
        # A rule written `Read(<file>/**)` matches nothing, so a file listed
        # only in that form is denied by no rule at all. The sessions that
        # carry no sandbox are the ones this has to hold for.
        for profile in (self.chief(), self.staff()):
            deny = list(profile["deny"])
            for name in profiles.CLAUDE_PRIVATE_FILES:
                with self.subTest(role=profile["role"], name=name):
                    path = "%s/%s" % (self.home, name)
                    self.assertIn(path, profile["credential_paths"])
                    self.assertIn("Read(%s)" % path, deny)
                    self.assertIn("Write(%s)" % path, deny)

    def test_the_owner_oauth_credentials_are_denied_for_every_role(self):
        path = "%s/.claude/.credentials.json" % self.home
        for profile in (self.chief(), self.staff(), self.worker("implementer"),
                        self.worker("test-runner")):
            with self.subTest(role=profile["role"]):
                self.assertIn("Read(%s)" % path, list(profile["deny"]))

    def test_a_private_directory_carries_both_deny_forms(self):
        deny = list(self.chief()["deny"])
        for name in profiles.CLAUDE_PRIVATE_DIRS:
            with self.subTest(name=name):
                path = "%s/%s" % (self.home, name)
                self.assertIn("Read(%s)" % path, deny)
                self.assertIn("Read(%s/**)" % path, deny)

    def test_no_private_file_is_listed_as_a_directory(self):
        self.assertEqual(
            set(profiles.CLAUDE_PRIVATE_FILES) & set(profiles.CLAUDE_PRIVATE_DIRS),
            set())
        for name in profiles.CLAUDE_PRIVATE_FILES:
            self.assertRegex(name, r"\.(json|jsonl)$")

    def test_company_views_stay_readable(self):
        creds = profiles.credential_paths(str(self.home), str(self.plugin))
        for pattern in creds:
            self.assertFalse(profiles.covers(pattern, str(self.views)),
                             "%s hides the company views" % pattern)

    def test_the_pattern_matcher_walks_segments(self):
        self.assertTrue(profiles.covers("/a/**/runtime", "/a/b/c/runtime/x"))
        self.assertFalse(profiles.covers("/a/**/runtime", "/a/b/views"))
        self.assertTrue(profiles.covers("/a/b", "/a/b"))
        self.assertFalse(profiles.covers("/a/b", "/a/bc"))
        self.assertTrue(profiles.covers("/a/*/c", "/a/b/c"))


# --- hooks, elicitation and policy widening ---------------------------------

class ProfileRefusalTest(ProfileCase):
    def test_a_worker_registers_the_dispatch_check_in_its_own_settings(self):
        settings = profiles.plain(self.worker())["settings"]
        entries = settings["hooks"]["PreToolUse"]
        self.assertEqual(entries[0]["matcher"], "Agent|SendMessage")
        command = entries[0]["hooks"][0]["command"]
        self.assertIn("%s/scripts/cabinet-hook" % self.plugin, command)

    def test_a_worker_without_the_dispatch_check_is_refused(self):
        mutated = profiles.plain(self.worker())
        del mutated["settings"]["hooks"]
        mutated["argv"] = list(profiles.build_argv(mutated))
        self.refuse(mutated, "PROFILE_HOOK_MISSING")

    def test_chief_and_staff_carry_no_hooks_of_their_own(self):
        # They load the packaged hooks.json through --plugin-dir instead.
        for profile in (self.chief(), self.staff()):
            self.assertNotIn("hooks", profiles.plain(profile)["settings"])

    def test_an_elicitation_hook_is_refused(self):
        for event in ("Elicitation", "ElicitationResult"):
            with self.subTest(event=event):
                mutated = profiles.plain(self.chief())
                mutated["settings"]["hooks"] = {
                    event: [{"hooks": [{"type": "command", "command": "true"}]}]}
                error = self.refuse(mutated, "PROFILE_HOOKS_FORBIDDEN")
                self.assertIn(event, error.message)

    def test_any_other_hook_is_refused(self):
        for hooks in ({"PreToolUse": [{"hooks": [{"type": "command",
                                                  "command": "true"}]}]},
                      {"SessionStart": [{"hooks": [{"type": "command",
                                                    "command": "true"}]}]}):
            with self.subTest(hooks=sorted(hooks)):
                mutated = profiles.plain(self.worker())
                mutated["settings"]["hooks"] = hooks
                mutated["argv"] = list(profiles.build_argv(mutated))
                self.refuse(mutated, "PROFILE_HOOKS_FORBIDDEN")

    def test_permission_bypass_modes_are_refused(self):
        for mode in ("bypassPermissions", "auto", "dontAsk"):
            with self.subTest(mode=mode):
                mutated = profiles.plain(self.worker())
                mutated["settings"]["permissions"]["defaultMode"] = mode
                mutated["argv"] = list(profiles.build_argv(mutated))
                self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_accept_edits_is_a_worker_setting_only(self):
        mutated = profiles.plain(self.chief())
        mutated["settings"]["permissions"]["defaultMode"] = "acceptEdits"
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")
        self.assertEqual(
            profiles.plain(self.worker())["settings"]["permissions"]["defaultMode"],
            "acceptEdits")

    def test_a_permission_allowlist_in_settings_is_refused(self):
        mutated = profiles.plain(self.worker())
        mutated["settings"]["permissions"]["allow"] = ["Bash(rm:*)"]
        mutated["argv"] = list(profiles.build_argv(mutated))
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_dropping_the_bypass_lock_is_refused(self):
        mutated = profiles.plain(self.worker())
        del mutated["settings"]["permissions"]["disableBypassPermissionsMode"]
        mutated["argv"] = list(profiles.build_argv(mutated))
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_an_unknown_settings_key_is_refused(self):
        for key, value in (("apiKeyHelper", "/bin/echo"),
                           ("enableAllProjectMcpServers", True),
                           ("mcpServers", {"github": {}})):
            with self.subTest(key=key):
                mutated = profiles.plain(self.worker())
                mutated["settings"][key] = value
                mutated["argv"] = list(profiles.build_argv(mutated))
                self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_cross_session_inbound_is_an_explicit_consent_value(self):
        # F1: a worker cannot receive chief messages unattended without this.
        self.assertEqual(
            profiles.plain(self.worker())["settings"]["crossSessionInbound"],
            "accept")
        mutated = profiles.plain(self.worker())
        mutated["settings"]["crossSessionInbound"] = "anything-else"
        mutated["argv"] = list(profiles.build_argv(mutated))
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")


# --- the environment the dispatch check reads -------------------------------

class ProfileEnvironmentTest(ProfileCase):
    def test_a_worker_carries_the_variables_the_check_needs(self):
        env = profiles.plain(self.worker())["env"]
        self.assertEqual(env["CABINET_PROFILE_KIND"], "worker")
        self.assertEqual(env["CABINET_CHIEF_NAME"], "cabinet-chief-amitbaz-cabinet")
        self.assertEqual(env["CABINET_PEER_REGISTRY"], str(self.registry))

    def test_the_chief_names_itself_as_the_chief(self):
        profile = self.chief()
        self.assertEqual(profile["env"]["CABINET_PROFILE_KIND"], "chief")
        self.assertEqual(profile["env"]["CABINET_CHIEF_NAME"],
                         profile["session_name"])

    def test_a_staff_subagent_has_no_environment_of_its_own(self):
        self.assertEqual(profiles.plain(self.staff())["env"], {})
        mutated = profiles.plain(self.staff())
        mutated["env"] = {"CABINET_PROFILE_KIND": "staff"}
        self.refuse(mutated, "ENV_INVALID")

    def test_a_wrong_or_missing_profile_kind_is_refused(self):
        for env in ({}, {"CABINET_PROFILE_KIND": "chief",
                         "CABINET_CHIEF_NAME": "cabinet-chief-x"},
                    {"CABINET_PROFILE_KIND": "worker"},
                    {"CABINET_PROFILE_KIND": "worker",
                     "CABINET_CHIEF_NAME": "c", "SOMETHING_ELSE": "x"}):
            with self.subTest(env=sorted(env)):
                mutated = profiles.plain(self.worker())
                mutated["env"] = env
                self.refuse(mutated, "ENV_INVALID")

    def test_the_registry_path_must_be_a_safe_absolute_path(self):
        mutated = profiles.plain(self.worker())
        mutated["env"]["CABINET_PEER_REGISTRY"] = "peers.json"
        self.refuse(mutated, "PROFILE_PATH_UNSAFE")

    def test_launch_returns_the_environment_beside_the_argv(self):
        launch = profiles.worker_launch(self.worker(), self.prompt(), SESSION_ID)
        self.assertEqual(launch["env"]["CABINET_PROFILE_KIND"], "worker")
        self.assertEqual(launch["env"]["CABINET_CHIEF_NAME"],
                         "cabinet-chief-amitbaz-cabinet")

    def prompt(self, text="Implement AC1."):
        path = self.runtime / "prompt-W001.md"
        path.write_text(text, encoding="utf-8")
        return str(path)


# --- the command line that actually runs ------------------------------------

class ArgvIntegrityTest(ProfileCase):
    def tampered(self, profile, change):
        mutated = profiles.plain(profile)
        change(mutated["argv"])
        return mutated

    def test_a_skip_permissions_flag_is_refused(self):
        for flag in ("--dangerously-skip-permissions",
                     "--dangerously-bypass-approvals-and-sandbox",
                     "--permission-mode", "--allowedTools",
                     "--disallowedTools", "--setting-sources", "--agents"):
            with self.subTest(flag=flag):
                mutated = self.tampered(self.worker(),
                                        lambda argv: argv.append(flag))
                self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_a_tool_appended_to_the_tools_flag_is_refused(self):
        def append_bash(argv):
            argv[argv.index("--tools") + 1] += ",Bash"
        self.refuse(self.tampered(self.worker(), append_bash),
                    "PROFILE_ARGV_MISMATCH")

    def test_settings_carried_on_the_command_line_must_be_the_verified_ones(self):
        def weaken(argv, key, value):
            index = argv.index("--settings") + 1
            carried = json.loads(argv[index])
            carried["sandbox"]["enabled"] = value if key == "sandbox" else \
                carried["sandbox"]["enabled"]
            if key == "mode":
                carried["permissions"]["defaultMode"] = "bypassPermissions"
            argv[index] = json.dumps(carried)

        for key in ("sandbox", "mode"):
            with self.subTest(key=key):
                mutated = self.tampered(
                    self.worker(), lambda argv: weaken(argv, key, False))
                self.refuse(mutated, "PROFILE_ARGV_MISMATCH")

    def test_unreadable_settings_on_the_command_line_are_refused(self):
        def corrupt(argv):
            argv[argv.index("--settings") + 1] = "{not json"
        self.refuse(self.tampered(self.worker(), corrupt),
                    "PROFILE_ARGV_MISMATCH")

    def test_the_chief_settings_file_must_be_the_profile_s_own(self):
        def repoint(argv):
            argv[argv.index("--settings") + 1] = "/tmp/other-settings.json"
        self.refuse(self.tampered(self.chief(), repoint),
                    "PROFILE_ARGV_MISMATCH")

    def test_an_extra_readable_directory_on_the_command_line_is_refused(self):
        def widen(argv):
            argv.extend(["--add-dir", str(self.home)])
        self.refuse(self.tampered(self.worker(), widen),
                    "PROFILE_ARGV_MISMATCH")

    def test_dropping_restricted_mode_is_refused(self):
        def drop(argv):
            argv.remove("--restricted")
        self.refuse(self.tampered(self.worker(), drop),
                    "PROFILE_ARGV_MISMATCH")

    def test_worker_launch_refuses_a_tampered_command_line(self):
        # The reviewer's reproduction: mutate only argv, leave the settings and
        # sandbox fields untouched, and ask for a launch.
        def tamper(argv):
            argv.append("--dangerously-skip-permissions")
            argv[argv.index("--tools") + 1] += ",Bash"
        mutated = self.tampered(self.worker(), tamper)
        with self.assertRaises(CabinetError) as caught:
            profiles.worker_launch(mutated, self.prompt(), SESSION_ID)
        self.assertEqual(caught.exception.code, "PROFILE_SETTINGS_WIDENING")

    def test_a_built_argv_always_matches_its_profile(self):
        for profile in (self.chief(), self.staff(), self.worker("implementer"),
                        self.worker("test-runner")):
            with self.subTest(role=profile["role"]):
                self.assertEqual(list(profile["argv"]),
                                 list(profiles.build_argv(profile)))

    def prompt(self, text="Implement AC1."):
        path = self.runtime / "prompt-W001.md"
        path.write_text(text, encoding="utf-8")
        return str(path)


# --- the mandatory worker sandbox ------------------------------------------

class SandboxTest(ProfileCase):
    def test_worker_sandbox_block_is_mandatory_and_closed(self):
        for role in profiles.WORKER_TYPES:
            with self.subTest(role=role):
                sandbox = profiles.plain(self.worker(role))["settings"]["sandbox"]
                self.assertIs(sandbox["enabled"], True)
                self.assertIs(sandbox["failIfUnavailable"], True)
                self.assertIs(sandbox["allowUnsandboxedCommands"], False)
                self.assertEqual(sandbox["excludedCommands"], [])
                self.assertIs(sandbox["filesystem"]["disabled"], False)
                self.assertIs(sandbox["network"]["strictAllowlist"], True)
                self.assertEqual(sandbox["network"]["allowedDomains"], [])

    def test_chief_and_staff_carry_no_sandbox_block(self):
        for profile in (self.chief(), self.staff()):
            self.assertIsNone(profile["sandbox"])

    def weaken(self, role, path, value):
        mutated = profiles.plain(self.worker(role))
        target = mutated["settings"]["sandbox"]
        mirror = mutated["sandbox"]
        for key in path[:-1]:
            target = target[key]
            mirror = mirror[key]
        target[path[-1]] = value
        mirror[path[-1]] = value
        mutated["argv"] = list(profiles.build_argv(mutated))
        return mutated

    def test_every_weakening_of_the_worker_sandbox_is_refused(self):
        weakenings = [
            (("enabled",), False),
            (("failIfUnavailable",), False),
            (("allowUnsandboxedCommands",), True),
            (("excludedCommands",), ["npm test"]),
            (("filesystem", "disabled"), True),
            (("network", "allowedDomains"), ["registry.example.com"]),
            (("network", "strictAllowlist"), False),
        ]
        for path, value in weakenings:
            with self.subTest(path=path):
                self.refuse(self.weaken("test-runner", path, value),
                            "PROFILE_SANDBOX_REQUIRED")

    def test_a_worker_with_no_sandbox_block_is_refused(self):
        mutated = profiles.plain(self.worker())
        mutated["sandbox"] = None
        del mutated["settings"]["sandbox"]
        mutated["argv"] = list(profiles.build_argv(mutated))
        self.refuse(mutated, "PROFILE_SANDBOX_REQUIRED")

    def test_the_sandbox_denies_reading_every_credential_path(self):
        sandbox = profiles.plain(self.worker())["settings"]["sandbox"]
        creds = profiles.credential_paths(str(self.home), str(self.plugin))
        for path in creds:
            self.assertIn(path, sandbox["filesystem"]["denyRead"])


# --- path handling ----------------------------------------------------------

class PathSafetyTest(ProfileCase):
    def test_relative_and_traversing_paths_are_refused(self):
        for value in ("work/cabinet-W001", "/tmp/../etc", "~/work", ""):
            with self.subTest(value=value):
                with self.assertRaises(CabinetError) as caught:
                    self.worker(path=value)
                self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_shell_metacharacters_in_a_path_are_refused(self):
        for value in ("/tmp/a;rm -rf /", "/tmp/$(id)", "/tmp/`id`", "/tmp/a\nb",
                      "/tmp/a|b", "/tmp/a&b", "/tmp/a>b"):
            with self.subTest(value=value):
                with self.assertRaises(CabinetError) as caught:
                    self.worker(path=value)
                self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_a_ticket_string_cannot_become_a_session_name(self):
        for value in ("W001; rm -rf /", "../../etc", "W001 W002", ""):
            with self.subTest(value=value):
                with self.assertRaises(CabinetError) as caught:
                    self.worker(assignment=value)
                self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_a_chief_name_cannot_carry_shell_syntax(self):
        with self.assertRaises(CabinetError) as caught:
            self.worker(chief_name="chief; rm -rf /")
        self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_a_check_profile_command_cannot_carry_metacharacters(self):
        bad = [{"profile_id": "local-unit",
                "argv": ["python3", "-m", "unittest; curl http://x"],
                "env": {}}]
        with self.assertRaises(CabinetError) as caught:
            self.worker("test-runner", check_profiles=bad)
        self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_a_check_profile_program_must_be_a_name_or_absolute_path(self):
        bad = [{"profile_id": "local-unit", "argv": ["./run.sh"], "env": {}}]
        with self.assertRaises(CabinetError) as caught:
            self.worker("test-runner", check_profiles=bad)
        self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_only_a_test_runner_may_carry_check_profiles(self):
        with self.assertRaises(CabinetError) as caught:
            self.worker("implementer", check_profiles=self.check_profiles())
        self.assertEqual(caught.exception.code, "FIELD_INVALID")

    def test_an_unknown_workspace_field_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            self.worker(permission_mode="bypassPermissions")
        self.assertEqual(caught.exception.code, "FIELD_UNKNOWN")

    def test_a_workspace_field_the_kind_never_uses_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            profiles.build_profile("qa", {"plugin_root": str(self.plugin),
                                          "claude_path": str(self.claude)},
                                   str(self.views), [], home=str(self.home))
        self.assertEqual(caught.exception.code, "FIELD_UNKNOWN")

    def test_a_worker_without_a_chief_cannot_be_built(self):
        workspace = self.worker_workspace()
        del workspace["chief_name"]
        with self.assertRaises(CabinetError) as caught:
            profiles.build_profile("implementer", workspace, str(self.views),
                                   [], home=str(self.home))
        self.assertEqual(caught.exception.code, "FIELD_MISSING")


# --- immutability and digest ------------------------------------------------

class ProfileShapeTest(ProfileCase):
    def test_a_built_profile_cannot_be_edited(self):
        profile = self.chief()
        with self.assertRaises(TypeError):
            profile["tools"] = ["Bash"]
        with self.assertRaises(TypeError):
            profile["settings"]["permissions"]["defaultMode"] = "bypassPermissions"
        with self.assertRaises(AttributeError):
            profile["tools"].append("Bash")

    def test_the_digest_freezes_the_whole_profile(self):
        profile = self.chief()
        body = profiles.plain(profile)
        body.pop("digest")
        self.assertEqual(profile["digest"], contracts.digest(body))
        self.assertEqual(self.chief()["digest"], profile["digest"])
        self.assertEqual(profiles.digest_of(profile), profile["digest"])

    def test_a_changed_tool_set_changes_the_digest(self):
        self.assertNotEqual(self.worker("implementer")["digest"],
                            self.worker("test-runner")["digest"])

    def test_settings_json_is_canonical(self):
        profile = self.worker()
        text = profiles.settings_json(profile)
        self.assertEqual(json.loads(text),
                         profiles.plain(profile)["settings"])
        self.assertEqual(text, contracts.canonical_json(
            profiles.plain(profile)["settings"]))


# --- worker launch ----------------------------------------------------------

class WorkerLaunchTest(ProfileCase):
    def prompt(self, text="Implement AC1 in the assigned worktree."):
        path = self.runtime / "prompt-W001.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_launch_builds_argv_without_running_anything(self):
        launch = profiles.worker_launch(self.worker(), self.prompt(), SESSION_ID)
        argv = launch["argv"]
        self.assertIsInstance(argv, list)
        self.assertTrue(all(isinstance(word, str) for word in argv))
        self.assertEqual(argv[0], str(self.claude))
        self.assertIn("--restricted", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--tools") + 1],
                         "Read,Edit,Write,Grep,Glob,SendMessage,ListAgents")
        self.assertEqual(argv[argv.index("--add-dir") + 1], str(self.worktree))
        self.assertEqual(argv[argv.index("--session-id") + 1], SESSION_ID)
        self.assertEqual(argv[-1], "Implement AC1 in the assigned worktree.")

    def test_launch_carries_the_inbound_consent_setting(self):
        launch = profiles.worker_launch(self.worker(), self.prompt(), SESSION_ID)
        argv = launch["argv"]
        settings = json.loads(argv[argv.index("--settings") + 1])
        self.assertEqual(settings["crossSessionInbound"], "accept")
        self.assertEqual(settings, launch["settings"])

    def test_worker_session_name_is_namespaced_away_from_role_names(self):
        launch = profiles.worker_launch(self.worker(), self.prompt(), SESSION_ID)
        name = launch["argv"][launch["argv"].index("--name") + 1]
        self.assertEqual(name, "cabinet-worker-W001")
        self.assertNotIn(name, profiles.STAFF_AGENT_TYPES)
        self.assertNotIn(name, profiles.WORKER_TYPES)
        self.assertEqual(name, launch["session_name"])

    def test_launch_refuses_a_non_worker_profile(self):
        with self.assertRaises(CabinetError) as caught:
            profiles.worker_launch(self.chief(), self.prompt(), SESSION_ID)
        self.assertEqual(caught.exception.code, "ROLE_UNKNOWN")

    def test_launch_refuses_an_unsafe_prompt_path(self):
        with self.assertRaises(CabinetError) as caught:
            profiles.worker_launch(self.worker(), "runtime/prompt.md", SESSION_ID)
        self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_launch_refuses_a_symlinked_prompt_file(self):
        target = self.prompt()
        link = self.runtime / "link.md"
        link.symlink_to(target)
        with self.assertRaises(CabinetError) as caught:
            profiles.worker_launch(self.worker(), str(link), SESSION_ID)
        self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_launch_refuses_a_bad_session_id(self):
        with self.assertRaises(CabinetError) as caught:
            profiles.worker_launch(self.worker(), self.prompt(), "not-a-uuid")
        self.assertEqual(caught.exception.code, "FIELD_INVALID")

    def test_launch_verifies_the_profile_it_is_given(self):
        mutated = profiles.plain(self.worker())
        mutated["settings"]["sandbox"]["enabled"] = False
        mutated["sandbox"]["enabled"] = False
        mutated["argv"] = list(profiles.build_argv(mutated))
        with self.assertRaises(CabinetError) as caught:
            profiles.worker_launch(mutated, self.prompt(), SESSION_ID)
        self.assertEqual(caught.exception.code, "PROFILE_SANDBOX_REQUIRED")


# --- the bounded subprocess adapter ----------------------------------------

class ProcessAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = self.tmp.name

    def env(self):
        return processes.build_env(allow=(), extra={"PYTHONHASHSEED": "0"})

    def test_argv_reaches_the_runner_as_a_list_with_no_shell(self):
        runner = FakeRunner(stdout="ok")
        result = processes.run_argv(["/bin/echo", "hello world"], self.cwd,
                                    self.env(), 5, runner=runner)
        call = runner.calls[0]
        self.assertEqual(call["argv"], ["/bin/echo", "hello world"])
        self.assertIsInstance(call["argv"], list)
        self.assertIs(call["kwargs"]["shell"], False)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"], "ok")
        self.assertIs(result["timed_out"], False)
        self.assertEqual(result["classification"], processes.COMPLETED)

    def test_a_string_command_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            processes.run_argv("/bin/echo hello", self.cwd, self.env(), 5,
                               runner=FakeRunner())
        self.assertEqual(caught.exception.code, "ARGV_INVALID")

    def test_a_non_string_argument_is_refused(self):
        for argv in ([], ["/bin/echo", 5], ["/bin/echo", None],
                     ["/bin/echo", "a\x00b"]):
            with self.subTest(argv=argv):
                with self.assertRaises(CabinetError) as caught:
                    processes.run_argv(argv, self.cwd, self.env(), 5,
                                       runner=FakeRunner())
                self.assertEqual(caught.exception.code, "ARGV_INVALID")

    def test_the_parent_environment_is_never_inherited(self):
        with self.assertRaises(CabinetError) as caught:
            processes.run_argv(["/bin/echo"], self.cwd, None, 5,
                               runner=FakeRunner())
        self.assertEqual(caught.exception.code, "ENV_INVALID")

    def test_build_env_copies_only_the_named_variables(self):
        environ = {"PATH": "/usr/bin", "GITHUB_TOKEN": "ghp_secret",
                   "HOME": "/home/x"}
        env = processes.build_env(allow=("PATH",), extra={"LC_ALL": "C"},
                                  environ=environ)
        self.assertEqual(env, {"PATH": "/usr/bin", "LC_ALL": "C"})
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("HOME", env)

    def test_build_env_skips_a_named_variable_that_is_not_set(self):
        env = processes.build_env(allow=("PATH", "NOT_SET_ANYWHERE"),
                                  environ={"PATH": "/usr/bin"})
        self.assertEqual(env, {"PATH": "/usr/bin"})

    def test_build_env_refuses_a_malformed_name_or_value(self):
        for allow, extra in ((("BAD NAME",), None), ((), {"A=B": "x"}),
                             ((), {"OK": "a\x00b"}), ((), {"OK": 5})):
            with self.subTest(allow=allow, extra=extra):
                with self.assertRaises(CabinetError) as caught:
                    processes.build_env(allow=allow, extra=extra, environ={})
                self.assertEqual(caught.exception.code, "ENV_INVALID")

    def test_the_result_never_carries_the_environment(self):
        runner = FakeRunner(stdout="ok")
        result = processes.run_argv(["/bin/echo"], self.cwd, self.env(), 5,
                                    runner=runner)
        self.assertNotIn("env", result)
        self.assertEqual(set(result),
                         {"returncode", "stdout", "stderr", "timed_out",
                          "duration", "classification"})

    def test_secret_looking_output_is_redacted(self):
        leaked = ("GITHUB_TOKEN=ghp_0123456789abcdefghijklmnopqrstuvwx\n"
                  "api_key: sk-ant-api03-abcdef\n"
                  "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.body.sig\n")
        runner = FakeRunner(stdout=leaked, stderr=leaked)
        result = processes.run_argv(["/bin/echo"], self.cwd, self.env(), 5,
                                    runner=runner)
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                self.assertNotIn("ghp_0123456789abcdefghijklmnopqrstuvwx",
                                 result[stream])
                self.assertNotIn("sk-ant-api03-abcdef", result[stream])
                self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", result[stream])
                self.assertIn(processes.REDACTED, result[stream])

    def test_output_is_bounded_in_bytes_with_a_visible_marker(self):
        runner = FakeRunner(stdout="x" * 50, stderr="y" * 50)
        result = processes.run_argv(["/bin/echo"], self.cwd, self.env(), 5,
                                    runner=runner, output_limit=20)
        self.assertTrue(result["stdout"].startswith("x" * 20))
        self.assertIn("truncated", result["stdout"])
        self.assertIn("truncated", result["stderr"])

    def test_multibyte_output_is_bounded_by_bytes_not_characters(self):
        runner = FakeRunner(stdout="é" * 100)
        result = processes.run_argv(["/bin/echo"], self.cwd, self.env(), 5,
                                    runner=runner, output_limit=20)
        kept = result["stdout"].split("\n[cabinet")[0]
        self.assertLessEqual(len(kept.encode("utf-8")), 20)

    def test_a_timeout_is_uncertain_and_is_never_retried(self):
        runner = FakeRunner(raises=subprocess.TimeoutExpired(
            ["/bin/sleep"], 5, output="partial", stderr="partial-err"))
        result = processes.run_argv(["/bin/sleep", "60"], self.cwd, self.env(),
                                    5, runner=runner)
        self.assertIs(result["timed_out"], True)
        self.assertIsNone(result["returncode"])
        self.assertEqual(result["classification"], processes.UNCERTAIN)
        self.assertEqual(len(runner.calls), 1)
        self.assertIn("partial", result["stdout"])

    def test_a_timeout_with_no_captured_output_still_classifies(self):
        runner = FakeRunner(raises=subprocess.TimeoutExpired(["/bin/sleep"], 5))
        result = processes.run_argv(["/bin/sleep", "60"], self.cwd, self.env(),
                                    5, runner=runner)
        self.assertEqual(result["stdout"], "")
        self.assertEqual(result["classification"], processes.UNCERTAIN)

    def test_a_relative_or_traversing_working_directory_is_refused(self):
        for cwd in ("relative/dir", "/tmp/../etc", ""):
            with self.subTest(cwd=cwd):
                with self.assertRaises(CabinetError) as caught:
                    processes.run_argv(["/bin/echo"], cwd, self.env(), 5,
                                       runner=FakeRunner())
                self.assertEqual(caught.exception.code, "UNSAFE_PATH")

    def test_a_missing_or_negative_timeout_is_refused(self):
        for timeout in (None, 0, -1, "5"):
            with self.subTest(timeout=timeout):
                with self.assertRaises(CabinetError) as caught:
                    processes.run_argv(["/bin/echo"], self.cwd, self.env(),
                                       timeout, runner=FakeRunner())
                self.assertEqual(caught.exception.code, "FIELD_INVALID")

    def test_a_real_command_runs_with_the_given_environment_only(self):
        script = ("import os,sys;"
                  "sys.stdout.write(repr(sorted(k for k in os.environ "
                  "if k in ('CABINET_PROBE','GITHUB_TOKEN'))))")
        os.environ["GITHUB_TOKEN"] = "ghp_should_not_be_inherited"
        self.addCleanup(os.environ.pop, "GITHUB_TOKEN", None)
        env = processes.build_env(allow=("PATH",),
                                  extra={"CABINET_PROBE": "1"})
        result = processes.run_argv([sys.executable, "-c", script], self.cwd,
                                    env, 30)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"], "['CABINET_PROBE']")


# --- the packaged PreToolUse hook ------------------------------------------

class HookTest(unittest.TestCase):
    def setUp(self):
        self.hook = load_hook()

    def decide(self, event, kind="chief", **env):
        environment = {"CABINET_PROFILE_KIND": kind} if kind else {}
        environment.update(env)
        return self.hook.decide(event, environment)

    def agent_event(self, subagent_type, **extra):
        tool_input = {"description": "d", "prompt": "p"}
        if subagent_type is not None:
            tool_input["subagent_type"] = subagent_type
        tool_input.update(extra)
        return {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                "session_id": "s1", "tool_input": tool_input}

    def message_event(self, to):
        return {"hook_event_name": "PreToolUse", "tool_name": "SendMessage",
                "session_id": "s1", "tool_input": {"to": to, "message": "m"}}

    # registry

    def test_the_hook_registry_matches_the_packaged_profiles(self):
        self.assertEqual(tuple(self.hook.STAFF_AGENT_TYPES),
                         profiles.STAFF_AGENT_TYPES)
        self.assertEqual(tuple(self.hook.WORKER_TYPES), profiles.WORKER_TYPES)

    def test_the_hook_environment_names_match_the_profile_field(self):
        self.assertEqual(sorted(profiles.ENV_NAMES),
                         ["CABINET_CHIEF_NAME", "CABINET_PEER_REGISTRY",
                          "CABINET_PROFILE_KIND"])

    # Agent dispatch

    def test_a_packaged_staff_type_is_allowed_in_either_spelling(self):
        for name in ("cabinet:qa", "qa", "cabinet:delivery-lead"):
            with self.subTest(name=name):
                decision, _ = self.decide(self.agent_event(name))
                self.assertEqual(decision, "allow")

    def test_an_unknown_or_general_purpose_type_is_denied(self):
        for name in ("general-purpose", "Explore", "claude", "fork",
                     "cabinet:general-purpose", None, ""):
            with self.subTest(name=name):
                decision, reason = self.decide(self.agent_event(name))
                self.assertEqual(decision, "deny")
                self.assertTrue(reason)

    def test_a_worker_type_is_denied_as_a_child(self):
        for name in ("implementer", "test-runner", "cabinet:implementer"):
            with self.subTest(name=name):
                decision, reason = self.decide(self.agent_event(name))
                self.assertEqual(decision, "deny")
                self.assertIn("isolated session", reason)

    def test_only_the_chief_may_dispatch_staff(self):
        for kind in ("staff", "worker"):
            with self.subTest(kind=kind):
                decision, _ = self.decide(self.agent_event("qa"), kind=kind)
                self.assertEqual(decision, "deny")

    def test_a_permission_bypass_option_is_denied(self):
        for extra in ({"mode": "bypassPermissions"},
                      {"permission_mode": "bypassPermissions"},
                      {"permissionMode": "acceptEdits"},
                      {"dangerouslySkipPermissions": True},
                      {"settings": {"permissions": {"defaultMode": "auto"}}},
                      {"tools": "*"}, {"isolation": "remote"},
                      {"isolation": "worktree"}):
            with self.subTest(extra=extra):
                decision, reason = self.decide(self.agent_event("qa", **extra))
                self.assertEqual(decision, "deny")
                self.assertTrue(reason)

    # SendMessage recipients

    def test_without_a_registry_only_packaged_peers_are_reachable(self):
        decision, _ = self.decide(self.message_event("qa"))
        self.assertEqual(decision, "allow")
        decision, reason = self.decide(self.message_event("some-other-session"))
        self.assertEqual(decision, "deny")
        self.assertIn("some-other-session", reason)

    def test_the_chief_can_always_reach_its_own_name(self):
        decision, _ = self.decide(self.message_event("cabinet-chief-acme"),
                                  kind="staff",
                                  CABINET_CHIEF_NAME="cabinet-chief-acme")
        self.assertEqual(decision, "allow")

    def test_a_worker_may_register_with_its_fixed_chief(self):
        decision, _ = self.decide(self.message_event("cabinet-chief-acme"),
                                  kind="worker",
                                  CABINET_CHIEF_NAME="cabinet-chief-acme")
        self.assertEqual(decision, "allow")
        decision, _ = self.decide(self.message_event("cabinet-chief-other"),
                                  kind="worker",
                                  CABINET_CHIEF_NAME="cabinet-chief-acme")
        self.assertEqual(decision, "deny")

    def test_a_registered_peer_from_the_registry_file_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "peers.json"
            path.write_text(json.dumps({"peers": ["cabinet-worker-W001"]}),
                            encoding="utf-8")
            decision, _ = self.decide(self.message_event("cabinet-worker-W001"),
                                      CABINET_PEER_REGISTRY=str(path))
            self.assertEqual(decision, "allow")
            decision, _ = self.decide(self.message_event("stranger"),
                                      CABINET_PEER_REGISTRY=str(path))
            self.assertEqual(decision, "deny")

    def test_an_unreadable_registry_denies_rather_than_opening_up(self):
        decision, reason = self.decide(
            self.message_event("cabinet-worker-W001"),
            CABINET_PEER_REGISTRY="/nonexistent/peers.json")
        self.assertEqual(decision, "deny")
        self.assertTrue(reason)

    # inert cases

    def test_an_ordinary_owner_session_is_untouched(self):
        decision, _ = self.decide(self.agent_event("general-purpose"), kind=None)
        self.assertEqual(decision, "noop")

    def test_other_tools_and_other_events_are_untouched(self):
        other_tool = {"hook_event_name": "PreToolUse", "tool_name": "Read",
                      "tool_input": {"file_path": "/tmp/x"}}
        other_event = {"hook_event_name": "PostToolUse", "tool_name": "Agent",
                       "tool_input": {"subagent_type": "general-purpose"}}
        for event in (other_tool, other_event):
            with self.subTest(event=event["hook_event_name"]):
                self.assertEqual(self.decide(event)[0], "noop")

    def test_malformed_input_is_inert_rather_than_fail_open(self):
        for event in (None, [], "text", {}, {"tool_name": "Agent"}):
            with self.subTest(event=event):
                self.assertEqual(self.decide(event)[0], "noop")

    def test_an_unreadable_tool_input_is_denied_not_waved_through(self):
        for tool in ("Agent", "SendMessage"):
            for bad in (None, "text", []):
                with self.subTest(tool=tool, tool_input=bad):
                    event = {"hook_event_name": "PreToolUse",
                             "tool_name": tool, "tool_input": bad}
                    decision, reason = self.decide(event)
                    self.assertEqual(decision, "deny")
                    self.assertTrue(reason)

    def test_an_unexpected_failure_denies_instead_of_passing(self):
        def explode(event, env):
            raise RuntimeError("registry backend on fire")
        original = self.hook.decide
        self.hook.decide = explode
        self.addCleanup(setattr, self.hook, "decide", original)
        decision, reason = self.hook.safe_decide(
            self.agent_event("qa"), {"CABINET_PROFILE_KIND": "chief"})
        self.assertEqual(decision, "deny")
        self.assertIn("on fire", reason)
        self.assertEqual(self.hook.safe_decide(self.agent_event("qa"), {})[0],
                         "noop")

    # end to end

    def test_the_hook_self_test_passes(self):
        result = subprocess.run([sys.executable, str(HOOK), "--self-test"],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_denied_dispatch_exits_two_with_a_reason(self):
        event = json.dumps(self.agent_event("general-purpose"))
        result = subprocess.run(
            [sys.executable, str(HOOK)], input=event, capture_output=True,
            text=True, timeout=60,
            env={"PATH": os.environ.get("PATH", "/usr/bin"),
                 "CABINET_PROFILE_KIND": "chief"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("general-purpose", result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]
                         ["permissionDecision"], "deny")

    def test_an_allowed_dispatch_exits_zero_and_says_nothing(self):
        event = json.dumps(self.agent_event("cabinet:qa"))
        result = subprocess.run(
            [sys.executable, str(HOOK)], input=event, capture_output=True,
            text=True, timeout=60,
            env={"PATH": os.environ.get("PATH", "/usr/bin"),
                 "CABINET_PROFILE_KIND": "chief"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_broken_stdin_is_inert_with_a_diagnostic(self):
        result = subprocess.run(
            [sys.executable, str(HOOK)], input="{not json", capture_output=True,
            text=True, timeout=60,
            env={"PATH": os.environ.get("PATH", "/usr/bin"),
                 "CABINET_PROFILE_KIND": "chief"})
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stderr.strip())


# --- packaged plugin files --------------------------------------------------

class PackagedFilesTest(unittest.TestCase):
    def test_hooks_json_registers_the_pretooluse_check(self):
        body = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        entries = body["hooks"]["PreToolUse"]
        commands = [hook["command"]
                    for entry in entries for hook in entry["hooks"]]
        self.assertTrue(any("${CLAUDE_PLUGIN_ROOT}" in command
                            and "scripts/cabinet-hook" in command
                            for command in commands), commands)
        matchers = [entry.get("matcher", "") for entry in entries]
        self.assertIn(profiles.HOOK_MATCHER, matchers)

    def test_the_packaged_registration_matches_the_one_a_worker_carries(self):
        packaged = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        carried = profiles.hook_entries("/opt/cabinet")
        self.assertEqual(sorted(packaged), sorted(carried))
        self.assertEqual(packaged["PreToolUse"][0]["matcher"],
                         carried["PreToolUse"][0]["matcher"])
        self.assertEqual(packaged["PreToolUse"][0]["hooks"][0]["timeout"],
                         carried["PreToolUse"][0]["hooks"][0]["timeout"])

    def test_the_hook_is_executable(self):
        self.assertTrue(os.access(HOOK, os.X_OK))

    def test_the_chief_agent_declares_exactly_the_contract_tools(self):
        text = CHIEF_AGENT.read_text(encoding="utf-8")
        front = text.split("---")[1]
        fields = {}
        for line in front.strip().splitlines():
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        self.assertEqual(fields["name"], "chief-of-staff")
        self.assertEqual(fields["model"], "inherit")
        declared = [item.strip() for item in fields["tools"].split(",")]
        self.assertEqual(declared[:7],
                         ["Read", "Grep", "Glob", "Skill", "Agent",
                          "SendMessage", "ListAgents"])
        self.assertEqual(declared[7:], list(profiles.SERVICE_TOOLS))
        disallowed = [item.strip() for item in fields["disallowedTools"].split(",")]
        self.assertEqual(disallowed,
                         ["Bash", "Write", "Edit", "NotebookEdit", "WebFetch",
                          "WebSearch"])

    def test_the_chief_agent_loads_the_shared_rules_and_checks_identity(self):
        text = CHIEF_AGENT.read_text(encoding="utf-8")
        self.assertIn('Skill(skill: "cabinet:coordination-rules")', text)
        self.assertIn("cabinet_doctor", text)


if __name__ == "__main__":
    unittest.main()


class ModelPassthroughTest(ProfileCase):
    """`--model` is a flow-test convenience: validated, derived from the
    profile, and therefore covered by the argv re-derivation check."""

    def test_a_model_named_in_the_workspace_reaches_the_argv(self):
        profile = self.chief(model="haiku")
        argv = list(profiles.plain(profile)["argv"])
        self.assertEqual(argv[argv.index("--model") + 1], "haiku")
        profiles.verify_profile(profile)

    def test_no_model_means_no_model_flag(self):
        self.assertNotIn("--model", profiles.plain(self.chief())["argv"])

    def test_a_model_with_shell_characters_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            self.chief(model="haiku; rm -rf /")
        self.assertEqual(caught.exception.code, "PROFILE_PATH_UNSAFE")

    def test_a_model_added_only_to_the_argv_is_refused(self):
        mutated = profiles.plain(self.chief())
        mutated["argv"] = list(mutated["argv"]) + ["--model", "opus"]
        self.refuse(mutated, "PROFILE_ARGV_MISMATCH")
