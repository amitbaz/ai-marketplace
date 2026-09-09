"""Contract tests for restricted launch profiles and the subprocess adapter.

Repository-only suite (see AGENTS.md). Python 3 standard library, plain
`unittest`, one temporary directory per test. Two guarantees are asserted here
rather than described anywhere else:

* a profile that would hand a role something it must not have is refused by
  `verify_profile` before any launcher could act on it, and
* `run_argv` never inherits the parent environment, never uses a shell, and
  never turns an ambiguous timeout into a silent retry.

Run:
    PYTHONPATH=plugins/cabinet/scripts:tests/cabinet \
        python3 -m unittest discover -s tests/cabinet -p test_profiles.py -v
"""

import copy
import importlib.machinery
import importlib.util
import json
import os
import re
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
    """A temporary machine: a home, a worktree, a plugin root and a views dir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.worktree = root / "work" / "cabinet-W001"
        self.plugin = root / "plugins" / "cabinet"
        self.views = root / "views"
        self.bin = root / "bin"
        for path in (self.home, self.worktree, self.plugin, self.views, self.bin):
            path.mkdir(parents=True)
        self.claude = self.bin / "claude"
        self.claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.mcp_config = root / "runtime" / "cabinet.mcp.json"
        self.mcp_config.parent.mkdir(parents=True)
        self.mcp_config.write_text("{}", encoding="utf-8")
        self.settings_path = root / "runtime" / "chief-settings.json"
        self.settings_path.write_text("{}", encoding="utf-8")

    # --- profile construction helpers ------------------------------------

    def chief_workspace(self, **overrides):
        workspace = {
            "assignment": "acme-widgets",
            "path": str(self.worktree),
            "claude_path": str(self.claude),
            "plugin_root": str(self.plugin),
            "mcp_config": str(self.mcp_config),
            "settings_path": str(self.settings_path),
            "session_id": SESSION_ID,
        }
        workspace.update(overrides)
        return workspace

    def worker_workspace(self, **overrides):
        workspace = {
            "assignment": "W001",
            "path": str(self.worktree),
            "claude_path": str(self.claude),
            "plugin_root": str(self.plugin),
        }
        workspace.update(overrides)
        return workspace

    def check_profiles(self):
        return [{"profile_id": "local-unit",
                 "argv": ["python3", "-m", "unittest"],
                 "env": {"PYTHONHASHSEED": "0"}}]

    def chief(self, **overrides):
        return profiles.build_profile("chief-of-staff",
                                      self.chief_workspace(**overrides),
                                      str(self.views), [], home=str(self.home))

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
        self.assertEqual(argv[argv.index("--name") + 1], "cabinet-chief-acme-widgets")
        self.assertIn(str(self.views), argv)
        self.assertTrue(all(isinstance(word, str) for word in argv))
        profiles.verify_profile(profile)

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
                self.assertEqual(tuple(profile["service_tools"]), ())
                self.assertEqual(tuple(profile["argv"]), ())
                self.assertEqual(tuple(profile["mcp_servers"]), ())
                profiles.verify_profile(profile)

    def test_staff_may_not_dispatch_its_own_workers(self):
        self.assertNotIn("Agent", self.staff("engineering")["tools"])

    def test_staff_profile_carrying_a_code_tool_is_refused(self):
        for tool in ("Bash", "Edit", "Write", "NotebookEdit", "WebFetch",
                     "WebSearch", "Browser", "BillingUpdate", "Deploy"):
            with self.subTest(tool=tool):
                mutated = profiles.plain(self.staff())
                mutated["tools"] = list(mutated["tools"]) + [tool]
                self.refuse(mutated, "PROFILE_TOOLS_FORBIDDEN")

    def test_staff_profile_carrying_a_service_tool_is_refused(self):
        mutated = profiles.plain(self.staff())
        mutated["service_tools"] = [profiles.SERVICE_TOOLS[0]]
        self.refuse(mutated, "PROFILE_TOOLS_FORBIDDEN")

    def test_unknown_role_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            profiles.build_profile("general-purpose", self.worker_workspace(),
                                   str(self.views), [], home=str(self.home))
        self.assertEqual(caught.exception.code, "ROLE_UNKNOWN")


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

    def test_worker_readable_directories_may_not_be_credential_stores(self):
        for name in (".claude", ".ssh", ".config/gh", ".cabinet"):
            with self.subTest(name=name):
                exposed = self.home / name
                exposed.mkdir(parents=True, exist_ok=True)
                mutated = profiles.plain(self.worker())
                mutated["add_dirs"] = list(mutated["add_dirs"]) + [str(exposed)]
                self.refuse(mutated, "PROFILE_CREDENTIALS_EXPOSED")

    def test_worker_readable_directories_may_not_be_a_docker_socket(self):
        mutated = profiles.plain(self.worker())
        mutated["add_dirs"] = list(mutated["add_dirs"]) + ["/var/run/docker.sock"]
        self.refuse(mutated, "PROFILE_CREDENTIALS_EXPOSED")

    def test_worker_denies_edits_to_plugin_files_and_public_context(self):
        profile = self.worker()
        deny = list(profile["deny"])
        for tool in ("Edit", "Write", "NotebookEdit"):
            self.assertIn("%s(%s/**)" % (tool, self.plugin), deny)
            self.assertIn("%s(%s/**)" % (tool, self.views), deny)
        mutated = profiles.plain(profile)
        mutated["deny"] = [rule for rule in deny if str(self.plugin) not in rule]
        mutated["settings"]["permissions"]["deny"] = list(mutated["deny"])
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_worker_denies_reads_of_every_credential_path(self):
        deny = list(self.worker()["deny"])
        for path in profiles.credential_paths(str(self.home)):
            self.assertIn("Read(%s/**)" % path, deny)


# --- hooks, elicitation and policy widening ---------------------------------

class ProfileRefusalTest(ProfileCase):
    def test_no_profile_carries_hooks_at_all(self):
        for profile in (self.chief(), self.staff(), self.worker()):
            self.assertNotIn("hooks", profiles.plain(profile)["settings"])

    def test_an_elicitation_hook_is_refused(self):
        for event in ("Elicitation", "ElicitationResult"):
            with self.subTest(event=event):
                mutated = profiles.plain(self.chief())
                mutated["settings"]["hooks"] = {
                    event: [{"hooks": [{"type": "command", "command": "true"}]}]}
                error = self.refuse(mutated, "PROFILE_HOOKS_FORBIDDEN")
                self.assertIn(event, error.message)

    def test_any_unregistered_hook_is_refused(self):
        mutated = profiles.plain(self.worker())
        mutated["settings"]["hooks"] = {
            "PreToolUse": [{"hooks": [{"type": "command", "command": "true"}]}]}
        self.refuse(mutated, "PROFILE_HOOKS_FORBIDDEN")

    def test_permission_bypass_modes_are_refused(self):
        for mode in ("bypassPermissions", "auto", "dontAsk"):
            with self.subTest(mode=mode):
                mutated = profiles.plain(self.worker())
                mutated["settings"]["permissions"]["defaultMode"] = mode
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
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_dropping_the_bypass_lock_is_refused(self):
        mutated = profiles.plain(self.worker())
        del mutated["settings"]["permissions"]["disableBypassPermissionsMode"]
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_an_unknown_settings_key_is_refused(self):
        for key, value in (("apiKeyHelper", "/bin/echo"),
                           ("enableAllProjectMcpServers", True),
                           ("mcpServers", {"github": {}})):
            with self.subTest(key=key):
                mutated = profiles.plain(self.worker())
                mutated["settings"][key] = value
                self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")

    def test_cross_session_inbound_is_an_explicit_consent_value(self):
        # F1: a worker cannot receive chief messages unattended without this.
        self.assertEqual(
            profiles.plain(self.worker())["settings"]["crossSessionInbound"],
            "accept")
        mutated = profiles.plain(self.worker())
        mutated["settings"]["crossSessionInbound"] = "anything-else"
        self.refuse(mutated, "PROFILE_SETTINGS_WIDENING")


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

    def test_every_weakening_of_the_worker_sandbox_is_refused(self):
        weakenings = [
            ("enabled", False),
            ("failIfUnavailable", False),
            ("allowUnsandboxedCommands", True),
            ("excludedCommands", ["npm test"]),
        ]
        for key, value in weakenings:
            with self.subTest(key=key):
                mutated = profiles.plain(self.worker("test-runner"))
                mutated["settings"]["sandbox"][key] = value
                mutated["sandbox"][key] = value
                self.refuse(mutated, "PROFILE_SANDBOX_REQUIRED")

    def test_disabling_filesystem_isolation_is_refused(self):
        mutated = profiles.plain(self.worker("test-runner"))
        mutated["settings"]["sandbox"]["filesystem"]["disabled"] = True
        mutated["sandbox"]["filesystem"]["disabled"] = True
        self.refuse(mutated, "PROFILE_SANDBOX_REQUIRED")

    def test_any_external_egress_is_refused(self):
        for key, value in (("allowedDomains", ["registry.example.com"]),
                           ("strictAllowlist", False)):
            with self.subTest(key=key):
                mutated = profiles.plain(self.worker("test-runner"))
                mutated["settings"]["sandbox"]["network"][key] = value
                mutated["sandbox"]["network"][key] = value
                self.refuse(mutated, "PROFILE_SANDBOX_REQUIRED")

    def test_a_worker_with_no_sandbox_block_is_refused(self):
        mutated = profiles.plain(self.worker())
        mutated["sandbox"] = None
        del mutated["settings"]["sandbox"]
        self.refuse(mutated, "PROFILE_SANDBOX_REQUIRED")


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
        path = Path(self.tmp.name) / "runtime" / "prompt-W001.md"
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
        link = Path(self.tmp.name) / "runtime" / "link.md"
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

    def test_output_is_bounded_with_a_visible_marker(self):
        runner = FakeRunner(stdout="x" * 50, stderr="y" * 50)
        result = processes.run_argv(["/bin/echo"], self.cwd, self.env(), 5,
                                    runner=runner, output_limit=20)
        self.assertTrue(result["stdout"].startswith("x" * 20))
        self.assertIn("truncated", result["stdout"])
        self.assertIn("truncated", result["stderr"])
        self.assertLess(len(result["stdout"]), 50 + 120)

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

    # Agent dispatch

    def test_a_packaged_staff_type_is_allowed_in_either_spelling(self):
        for name in ("cabinet:qa", "qa", "cabinet:delivery-lead"):
            with self.subTest(name=name):
                decision, _ = self.decide(self.agent_event(name))
                self.assertEqual(decision, "allow")

    def test_an_unknown_or_general_purpose_type_is_denied(self):
        for name in ("general-purpose", "Explore", "claude", "fork",
                     "cabinet:general-purpose", "implementer", None, ""):
            with self.subTest(name=name):
                decision, reason = self.decide(self.agent_event(name))
                self.assertEqual(decision, "deny")
                self.assertTrue(reason)

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
        matchers = " ".join(entry.get("matcher", "") for entry in entries)
        self.assertIn("Agent", matchers)
        self.assertIn("SendMessage", matchers)

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
