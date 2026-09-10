"""Automatic isolated workspaces, and the registration that makes one real.

Two things are under test here and they are deliberately not the same thing.

The first is *authority*: nothing may create a workspace or start a worker
without a live owner grant, a whole board, spare capacity and undisputed
ownership of the paths. Those tests call `execute_action` rather than an
adapter, because an adapter that refuses is a courtesy and a service that
refuses is the guarantee.

The second is *identity*: a worker exists when its own registration matches
what the provider observes, and not a moment earlier. A terminal that started
is not a worker; a name is not a session; and a registration nobody checked is
a claim. The tests below drive each mismatch separately, because each one is a
different way for a dispatch to look successful and be nothing.
"""

import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path

from cabinet_runtime import contracts, superset as workspace
from cabinet_runtime.errors import CabinetError
from cabinet_runtime.git import GitAdapter

from support import (CountingClock, FakeSuperset, FixtureBuilder, ServiceCase,
                     action, batch, fake_toolchain, load_script,
                     local_provider, repo_root)


class DispatchAuthorityTest(ServiceCase):
    """The two properties the brief names, in the brief's own words."""

    def setUp(self):
        super().setUp()
        self.approve_setup_through_fake_ui()

    def test_unapproved_batch_never_creates_workspace(self):
        item = self.service.prepare_action(action())
        with self.assertRaises(CabinetError):
            self.service.execute_action(item["action_id"])
        self.assertEqual(self.superset.calls, [])

    def test_timeout_after_create_reuses_exact_workspace(self):
        self.approve_batch_through_fake_ui()
        self.superset.timeout_after_creating = True
        item = self.service.prepare_action(action())
        self.service.execute_action(item["action_id"])
        self.assertEqual(self.store.get_action("A001")["state"], "uncertain")
        self.service.reconcile({})
        self.assertEqual(self.superset.workspace_create_count, 1)

    def test_the_reconciled_workspace_is_the_one_that_was_created(self):
        """Adoption is by stable name, not by taking the newest thing there."""

        self.approve_batch_through_fake_ui()
        self.superset.timeout_after_creating = True
        item = self.service.prepare_action(action())
        self.service.execute_action(item["action_id"])
        # Something unrelated also exists in the provider.
        self.superset.create_workspace("someone-elses", "other", "refs/heads/x")
        self.service.reconcile({})
        assignment = self.store.get_assignment("W012")
        created = self.superset.workspaces[
            workspace.workspace_name("B001", 1, "W012")]
        self.assertEqual(assignment["workspace_id"], created["workspace_id"])
        self.assertEqual(self.store.get_action("A001")["state"], "verified")

    def test_a_retry_reuses_the_stable_name_rather_than_minting_one(self):
        self.approve_batch_through_fake_ui()
        self.superset.fail_next_create = "PROVIDER_ERROR"
        item = self.service.prepare_action(action())
        with self.assertRaises(CabinetError):
            self.service.execute_action(item["action_id"])
        self.service.prepare_action(dict(action(key="create-12-again"),
                                         action_id="A002"))
        self.service.execute_action("A002")
        names = [call[1] for call in self.superset.calls
                 if call[0] == "create_workspace"]
        self.assertEqual(len(names), 2)
        self.assertEqual(names[0], names[1])


class ProviderSelectionTest(ServiceCase):
    """Which provider runs is a setup decision, never a default that guesses."""

    def setUp(self):
        super().setUp()
        self.local = FakeSuperset(name="local")
        self.service.providers = {"superset": self.superset, "local": self.local}

    def test_an_unauthenticated_superset_refuses_dispatch(self):
        self.superset.usable = False
        self.superset.reason = "not logged in"
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()
        self.service.prepare_action(action())
        code = self._refuse("A001")
        self.assertEqual(code, "WORKSPACE_PROVIDER_UNAVAILABLE")
        self.assertEqual(self.superset.calls, [])

    def test_a_configured_local_provider_runs_when_superset_cannot(self):
        self.superset.usable = False
        self.approve_setup_through_fake_ui(workspace_provider="local")
        self.approve_batch_through_fake_ui()
        item = self.service.prepare_action(action())
        self.service.execute_action(item["action_id"])
        self.assertEqual(self.local.workspace_create_count, 1)
        self.assertEqual(self.superset.calls, [])

    def test_a_provider_the_host_does_not_have_is_refused_not_swapped(self):
        self.service.providers = {"superset": self.superset}
        self.approve_setup_through_fake_ui(workspace_provider="local")
        self.approve_batch_through_fake_ui()
        self.service.prepare_action(action())
        self.assertEqual(self._refuse("A001"), "WORKSPACE_PROVIDER_UNAVAILABLE")

    def _refuse(self, action_id):
        try:
            self.service.execute_action(action_id)
        except CabinetError as problem:
            return problem.code
        raise AssertionError("execute_action did not refuse")


class SetupIsolationTest(ServiceCase):
    """A setup command that runs before the sandbox exists is not contained."""

    def test_uncontained_setup_refuses_before_any_workspace_is_created(self):
        self.superset.contained = False
        self.superset.containment_reason = (
            "the project's setup command could not be read")
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()
        self.service.prepare_action(action())
        try:
            self.service.execute_action("A001")
        except CabinetError as problem:
            self.assertEqual(problem.code, "SETUP_ISOLATION_UNAVAILABLE")
        else:
            raise AssertionError("an uncontained setup was not refused")
        self.assertEqual(self.superset.workspace_create_count, 0)
        self.assertEqual(self.store.get_action("A001")["state"], "blocked")


class CapacityAndOwnershipTest(ServiceCase):
    """Two live workers on one path set is a collision, not parallelism."""

    def setUp(self):
        super().setUp()
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()

    def test_a_second_worker_past_the_batch_capacity_is_refused(self):
        self.service.prepare_action(dict(
            action(), payload={"issue_number": 12, "assignment_id": "W012",
                               "owned_paths": ["app/web/"]}))
        self.service.execute_action("A001")
        # A different assignment on paths nobody else holds: the only thing
        # standing in its way is the batch's own worker ceiling.
        self.service.prepare_action(dict(
            action(key="create-12-second-worker"), action_id="A002",
            payload={"issue_number": 12, "assignment_id": "W112",
                     "owned_paths": ["app/api/"]}))
        try:
            self.service.execute_action("A002")
        except CabinetError as problem:
            self.assertEqual(problem.code, "CAPACITY_EXCEEDED")
        else:
            raise AssertionError("capacity was not enforced")
        self.assertEqual(self.superset.workspace_create_count, 1)

    def test_a_second_claim_on_the_same_paths_waits(self):
        self.service.prepare_action(action())
        self.service.execute_action("A001")
        self.service.prepare_action(dict(
            action(key="create-12-twice"), action_id="A002",
            payload={"issue_number": 12, "assignment_id": "W099"}))
        try:
            self.service.execute_action("A002")
        except CabinetError as problem:
            self.assertEqual(problem.code, "OWNERSHIP_CONFLICT")
        else:
            raise AssertionError("a conflicting claim was not refused")
        # Waiting, not failing: the action can be run again once the holder
        # finishes, so it must not be in a terminal state.
        self.assertEqual(self.store.get_action("A002")["state"], "blocked")


class PauseFenceTest(ServiceCase):
    """Pause commits first, then cancels what never started."""

    def setUp(self):
        super().setUp()
        self.register_role_addresses()
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()

    def test_pause_fences_new_dispatch(self):
        self.service.prepare_action(action())
        self.service.pause("owner asked")
        try:
            self.service.execute_action("A001")
        except CabinetError as problem:
            self.assertEqual(problem.code, "PAUSED")
        else:
            raise AssertionError("a paused company still dispatched")
        self.assertEqual(self.superset.calls, [])

    def test_pause_cancels_an_unstarted_reservation(self):
        self.service.prepare_action(dict(action(), kind="workspace.reserve"))
        self.service.execute_action("A001")
        self.assertEqual(self.store.get_assignment("W012")["state"], "reserved")
        result = self.service.pause("owner asked")
        self.assertIn("W012", result["cancelled_reservations"])
        self.assertEqual(self.store.get_assignment("W012")["state"], "cancelled")

    def test_pause_requests_a_stop_and_never_claims_one(self):
        builder = FixtureBuilder(self)
        builder.assignment(state="running", terminal_id="T1",
                           native_session_id="S-worker")
        result = self.service.pause("owner asked")
        self.assertEqual(result["stop_requested"], ["W001"])
        self.assertEqual(self.store.get_assignment("W001")["state"],
                         "cancel_requested")
        self.assertNotIn("cancelled", result["stop_requested"])
        recorded = [row for row in self.store.get_handoffs()
                    if row["to_role"] in ("implementer", "test-runner")]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["state"], "recorded")


class RegistrationTest(ServiceCase):
    """`running` means the worker said who it is and the provider agreed."""

    def setUp(self):
        super().setUp()
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()
        self.builder = FixtureBuilder(self)
        self.assignment = self.builder.assignment(state="starting",
                                                  terminal_id="T1")

    def _registration(self, **overrides):
        record = {
            "role": "implementer",
            "native_address": "cabinet-worker-W001",
            "assignment_id": "W001",
            "generation": self.assignment["generation"],
            "native_session_id": "S-worker",
            "terminal_id": "T1",
            "workspace_id": self.assignment["workspace_id"],
            "actual_base_sha": "a" * 40,
            "profile_digest": self.assignment["profile_digest"],
        }
        record.update(overrides)
        return record

    def test_a_matching_registration_makes_the_assignment_running(self):
        self.superset.live("T1", "S-worker", "a" * 40)
        self.service.register_session("W001", self._registration())
        stored = self.store.get_assignment("W001")
        self.assertEqual(stored["state"], "running")
        self.assertEqual(stored["native_session_id"], "S-worker")

    def test_a_registration_naming_another_terminal_is_not_running(self):
        self.superset.live("T1", "S-worker", "a" * 40)
        with self.assertRaises(CabinetError) as caught:
            self.service.register_session("W001",
                                          self._registration(terminal_id="T9"))
        self.assertEqual(caught.exception.code, "REGISTRATION_MISMATCH")
        self.assertEqual(self.store.get_assignment("W001")["state"], "starting")

    def test_a_registration_the_provider_cannot_see_is_not_running(self):
        # Nothing is live at the provider: the worker's claim is unwitnessed.
        with self.assertRaises(CabinetError) as caught:
            self.service.register_session("W001", self._registration())
        self.assertEqual(caught.exception.code, "REGISTRATION_MISMATCH")
        self.assertEqual(self.store.get_assignment("W001")["state"], "starting")

    def test_a_registration_at_a_stale_generation_is_refused(self):
        self.superset.live("T1", "S-worker", "a" * 40)
        with self.assertRaises(CabinetError) as caught:
            self.service.register_session("W001", self._registration(
                generation=self.assignment["generation"] - 1))
        self.assertEqual(caught.exception.code, "GENERATION_STALE")

    def test_a_registration_on_another_base_is_refused(self):
        self.superset.live("T1", "S-worker", "a" * 40)
        with self.assertRaises(CabinetError) as caught:
            self.service.register_session("W001",
                                          self._registration(actual_base_sha="b" * 40))
        self.assertEqual(caught.exception.code, "REGISTRATION_MISMATCH")

    def test_a_partial_registration_cannot_start_a_worker(self):
        self.superset.live("T1", "S-worker", "a" * 40)
        partial = self._registration()
        del partial["profile_digest"]
        with self.assertRaises(CabinetError) as caught:
            self.service.register_session("W001", partial)
        self.assertEqual(caught.exception.code, "FIELD_MISSING")
        self.assertEqual(self.store.get_assignment("W001")["state"], "starting")

    def test_no_registration_inside_the_window_is_a_startup_failure(self):
        self.clock.advance(workspace.STARTUP_WINDOW_SECONDS + 60)
        report = self.service.reconcile({})
        outcomes = {row["assignment_id"]: row for row in report["assignments"]}
        self.assertEqual(outcomes["W001"]["code"], "STARTUP_FAILED")
        self.assertEqual(self.store.get_assignment("W001")["state"], "blocked")

    def test_a_running_worker_the_provider_lost_is_marked_lost(self):
        self.superset.live("T1", "S-worker", "a" * 40)
        self.service.register_session("W001", self._registration())
        self.superset.gone()
        report = self.service.reconcile({})
        outcomes = {row["assignment_id"]: row for row in report["assignments"]}
        self.assertEqual(outcomes["W001"]["outcome"], "lost")
        self.assertEqual(self.store.get_assignment("W001")["state"], "lost")


class TerminalClosureTest(ServiceCase):
    """A close is scoped to the assignment that owns the terminal."""

    def setUp(self):
        super().setUp()
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()
        self.builder = FixtureBuilder(self)
        self.builder.assignment(state="running", terminal_id="T1",
                                native_session_id="S-worker")

    def test_closing_another_terminal_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            self.service.close_worker("W001", terminal_id="T-somebody-else")
        self.assertEqual(caught.exception.code, "TERMINAL_NOT_REGISTERED")
        self.assertEqual(self.superset.closed, [])

    def test_closing_the_registered_terminal_preserves_the_worktree(self):
        self.service.close_worker("W001", terminal_id="T1")
        self.assertEqual(self.superset.closed, [("W-B001-r1-W001", "T1")])
        self.assertEqual(self.superset.removed_worktrees, [])


# --- adapters ---------------------------------------------------------------


class RecordingRun:
    """Captures every argv a provider builds, and answers with canned JSON."""

    def __init__(self, replies=None):
        self.argv = []
        self.cwds = []
        self.replies = list(replies or [])
        self.default = {"returncode": 0, "stdout": "{}", "stderr": "",
                        "timed_out": False, "duration": 0.0,
                        "classification": "completed"}

    def __call__(self, argv, cwd=None, timeout=None):
        self.argv.append(list(argv))
        self.cwds.append(cwd)
        if self.replies:
            return self.replies.pop(0)
        return dict(self.default)

    def flag(self, index, name):
        argv = self.argv[index]
        return argv[argv.index(name) + 1]


def _ok(payload):
    return {"returncode": 0, "stdout": json.dumps(payload), "stderr": "",
            "timed_out": False, "duration": 0.0, "classification": "completed"}


def _text(out, code=0):
    return {"returncode": code, "stdout": out, "stderr": "", "timed_out": False,
            "duration": 0.0, "classification": "completed"}


class SupersetArgvTest(unittest.TestCase):
    """The command line is the brief's, verbatim, and it is not a shell."""

    def adapter(self, run):
        return workspace.SupersetAdapter(run, "PROJ", "HOST",
                                         superset_path="/bin/superset")

    def test_workspace_creation_uses_the_named_flags(self):
        run = RecordingRun([_ok({"workspaceId": "W-1", "path": "/w/one",
                                 "baseSha": "a" * 40})])
        adapter = self.adapter(run)
        adapter.create_workspace("cabinet-b001-r1-w012",
                                 "cabinet/b001/r1/w012",
                                 "refs/cabinet/b001/1")
        argv = run.argv[0]
        self.assertEqual(argv[:4],
                         ["/bin/superset", "workspaces", "create", "--project"])
        for flag, value in (("--project", "PROJ"),
                            ("--name", "cabinet-b001-r1-w012"),
                            ("--branch", "cabinet/b001/r1/w012"),
                            ("--base-branch", "refs/cabinet/b001/1")):
            self.assertEqual(run.flag(0, flag), value)
        self.assertIn("--skip-branch-prefix", argv)
        self.assertIn("--local", argv)
        self.assertIn("--json", argv)
        # `--agent` and `--prompt` would hand the launch flags to a preset
        # whose permissions nobody verified. The terminal path exists so the
        # restricted flags are ours.
        self.assertNotIn("--agent", argv)
        self.assertNotIn("--prompt", argv)

    def test_a_terminal_carries_a_quoted_command_that_round_trips(self):
        run = RecordingRun([_ok({"terminalId": "T-1"})])
        adapter = self.adapter(run)
        launch = ["/bin/claude", "--restricted", "--tools", "Read,Edit",
                  "You are an implementer; do not run `rm -rf /`."]
        adapter.create_terminal("W-1", launch, cwd="/w/one")
        command = run.flag(0, "--command")
        self.assertEqual(shlex.split(command), launch)
        self.assertEqual(run.flag(0, "--cwd"), "/w/one")

    def test_a_prompt_that_would_break_out_of_a_command_is_refused(self):
        run = RecordingRun()
        adapter = self.adapter(run)
        with self.assertRaises(CabinetError) as caught:
            adapter.create_terminal("W-1", ["/bin/claude", "hi\x00there"],
                                    cwd="/w/one")
        self.assertEqual(caught.exception.code, "ARGV_INVALID")
        self.assertEqual(run.argv, [])

    def test_a_timeout_after_creating_is_uncertain_rather_than_failed(self):
        run = RecordingRun([{"returncode": None, "stdout": "", "stderr": "",
                             "timed_out": True, "duration": 1.0,
                             "classification": "timeout_after_possible_dispatch"}])
        adapter = self.adapter(run)
        result = adapter.create_workspace("n", "b", "refs/cabinet/b001/1")
        self.assertEqual(result["outcome"], "uncertain")
        self.assertIsNone(result["workspace_id"])

    def test_probe_reports_the_real_authentication_state(self):
        run = RecordingRun([
            _text("1.27.0\n"),
            {"returncode": 1, "stdout": "", "stderr":
             "Error: Not logged in\nHint: Run: superset auth login",
             "timed_out": False, "duration": 0.0, "classification": "completed"},
        ])
        adapter = self.adapter(run)
        report = adapter.probe()
        self.assertEqual(report["provider"], "superset")
        self.assertEqual(report["version"], "1.27.0")
        self.assertFalse(report["authenticated"])
        self.assertFalse(report["usable"])
        self.assertIn("Not logged in", report["reason"])

    def test_an_unauthenticated_superset_cannot_argue_its_setup_is_contained(self):
        run = RecordingRun([
            _text("1.27.0\n"),
            {"returncode": 1, "stdout": "", "stderr": "Error: Not logged in",
             "timed_out": False, "duration": 0.0, "classification": "completed"},
        ])
        adapter = self.adapter(run)
        audit = adapter.audit_setup_isolation()
        self.assertFalse(audit["contained"])
        self.assertIn("not logged in", audit["reason"].lower())

    def test_stable_names_do_not_change_between_attempts(self):
        first = workspace.workspace_name("B001", 1, "W012")
        second = workspace.workspace_name("B001", 1, "W012")
        self.assertEqual(first, second)
        self.assertEqual(workspace.branch_name("B001", 1, "W012"),
                         "cabinet/b001/r1/w012")
        self.assertEqual(workspace.base_ref_name("B001", 1),
                         "refs/cabinet/b001/1")
        self.assertNotEqual(workspace.workspace_name("B001", 2, "W012"), first)


class EntrypointToolchainTest(ServiceCase):
    """The service must survive being built, or the chief gets no tools at all.

    A crash anywhere in `build_service` takes the whole MCP server down, and
    what the chief sees is `No such tool available` — a message that points at
    the tool registry rather than at the real fault. That happened live: a
    property was called as a method, and the only symptom was a chief with no
    Cabinet tools.
    """

    def test_the_toolchain_is_built_from_the_launch_profile(self):
        entrypoint = load_script(
            Path(repo_root()) / "plugins/cabinet/scripts/cabinet-service",
            "cabinet_service_entrypoint")
        body = {"claude_path": "/bin/claude", "plugin_root": "/plugin",
                "public_context": "/views", "session_name": "cabinet-chief-x"}
        profile_body = Path(self.tmp.name) / "profile.json"
        profile_body.write_text(json.dumps(body))
        os.chmod(str(profile_body), 0o600)
        toolchain = entrypoint.build_worker_toolchain(
            {"profile_body_path": str(profile_body)}, self.store)
        self.assertEqual(toolchain["claude_path"], "/bin/claude")
        self.assertEqual(toolchain["chief_name"], "cabinet-chief-x")
        self.assertEqual(toolchain["chief_address"], "cabinet-chief-x")
        self.assertIsInstance(toolchain["peer_registry"], str)
        self.assertTrue(toolchain["peer_registry"].endswith(".json"))


class ChiefAddressTest(unittest.TestCase):
    """Who reaches the chief how, and why the two answers are opposite."""

    def test_a_teammate_reaches_the_chief_at_main(self):
        from cabinet_runtime.service import chief_address_for

        self.assertEqual(chief_address_for("staff", "cabinet-chief-x"), "main")

    def test_a_launched_worker_reaches_the_chief_by_session_name(self):
        """Observed live: a worker sending to `main` addresses itself.

        The harness answered `You are the main conversation — "main" addresses
        you. Send to a named agent instead.` The dispatch hook already assumed
        the session name, so a context file saying `main` was telling the
        worker to do the one thing that cannot work.
        """

        from cabinet_runtime.service import chief_address_for

        self.assertEqual(chief_address_for("worker", "cabinet-chief-x"),
                         "cabinet-chief-x")


class WorkerEnvironmentTest(unittest.TestCase):
    """What a launched worker inherits, and what it must never inherit."""

    def test_the_binary_gets_what_it_needs_to_authenticate(self):
        """`USER` is required: without it the worker starts and cannot log in.

        Found live rather than reasoned about. A worker launched with only
        PATH, HOME and the locale variables came up, printed its banner and
        reported `Not logged in`, which is the worst kind of failure — a
        session that exists, answers `claude agents`, and can do nothing.
        """

        self.assertIn("USER", workspace.PROVIDER_ENVIRONMENT)
        self.assertIn("HOME", workspace.PROVIDER_ENVIRONMENT)
        self.assertIn("PATH", workspace.PROVIDER_ENVIRONMENT)

    def test_no_credential_variable_is_inherited(self):
        forbidden = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
                     "GH_TOKEN", "GITHUB_TOKEN", "SUPERSET_API_KEY",
                     "SSH_AUTH_SOCK", "AWS_SECRET_ACCESS_KEY")
        for name in forbidden:
            self.assertNotIn(name, workspace.PROVIDER_ENVIRONMENT)

    def test_the_child_environment_is_built_from_the_allowlist(self):
        from cabinet_runtime import processes

        env = processes.build_env(workspace.PROVIDER_ENVIRONMENT,
                                  environ={"PATH": "/bin", "USER": "someone",
                                           "ANTHROPIC_API_KEY": "sk-ant-nope",
                                           "SSH_AUTH_SOCK": "/tmp/agent"})
        self.assertEqual(sorted(env), ["PATH", "USER"])


class GitAdapterTest(unittest.TestCase):
    """Every git call names its hooks path and never names a remote."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hooks = Path(self.tmp.name) / "hooks"
        self.hooks.mkdir()

    def adapter(self, run):
        return GitAdapter(run, self.tmp.name, str(self.hooks),
                          git_path="/usr/bin/git")

    def test_every_command_disables_hooks(self):
        run = RecordingRun([_text("a" * 40 + "\n")])
        self.adapter(run).rev_parse("refs/cabinet/b001/1")
        argv = run.argv[0]
        self.assertEqual(argv[0], "/usr/bin/git")
        self.assertIn("-c", argv)
        self.assertIn("core.hooksPath=%s" % self.hooks, argv)

    def test_a_hooks_directory_with_a_hook_in_it_is_refused(self):
        (self.hooks / "post-checkout").write_text("#!/bin/sh\necho no\n")
        run = RecordingRun()
        with self.assertRaises(CabinetError) as caught:
            self.adapter(run).rev_parse("HEAD")
        self.assertEqual(caught.exception.code, "SETUP_ISOLATION_UNAVAILABLE")
        self.assertEqual(run.argv, [])

    def test_pinning_a_ref_verifies_it_resolves_to_the_approved_sha(self):
        run = RecordingRun([_text(""), _text("b" * 40 + "\n")])
        with self.assertRaises(CabinetError) as caught:
            self.adapter(run).pin_base("refs/cabinet/b001/1", "a" * 40)
        self.assertEqual(caught.exception.code, "BASE_SHA_MISMATCH")

    def test_no_enumerated_operation_can_reach_the_network(self):
        for name in ("fetch", "push", "pull", "clone", "remote"):
            self.assertFalse(hasattr(GitAdapter, name),
                             "%s must not exist on the bounded adapter" % name)


class LocalProviderTest(unittest.TestCase):
    """The verified automatic path on a machine with no Superset session."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.spaces = Path(self.tmp.name) / "workspaces"
        self.hooks = Path(self.tmp.name) / "hooks"
        self.hooks.mkdir()

    def provider(self, run):
        return local_provider(run, str(self.root), str(self.spaces),
                              str(self.hooks))

    def test_a_worktree_is_created_at_the_verified_base(self):
        run = RecordingRun([
            _text(""),                        # status --porcelain, clean
            _text("a" * 40 + "\n"),           # rev-parse of the fixed ref
            _text("Preparing worktree\n"),    # worktree add
            _text("a" * 40 + "\n"),           # rev-parse HEAD in the worktree
        ])
        result = self.provider(run).create_workspace(
            "cabinet-b001-r1-w012", "cabinet/b001/r1/w012",
            "refs/cabinet/b001/1")
        self.assertEqual(result["actual_base_sha"], "a" * 40)
        self.assertEqual(result["outcome"], "created")
        add = [argv for argv in run.argv if "worktree" in argv][0]
        self.assertEqual(add[-5:], ["add", "-b", "cabinet/b001/r1/w012",
                                    str(self.spaces / "cabinet-b001-r1-w012"),
                                    "refs/cabinet/b001/1"])

    def test_a_dirty_base_is_refused_before_anything_is_created(self):
        run = RecordingRun([_text(" M plugins/cabinet/scripts/x.py\n")])
        with self.assertRaises(CabinetError) as caught:
            self.provider(run).create_workspace("n", "b", "refs/cabinet/b001/1")
        self.assertEqual(caught.exception.code, "WORKTREE_DIRTY")
        self.assertEqual(len(run.argv), 1)

    def test_a_base_that_does_not_resolve_to_the_ref_is_refused(self):
        run = RecordingRun([_text(""), _text("")])
        with self.assertRaises(CabinetError) as caught:
            self.provider(run).create_workspace("n", "b", "refs/cabinet/b001/1")
        self.assertEqual(caught.exception.code, "BASE_SHA_MISMATCH")

    def test_the_launch_is_a_list_and_never_a_shell_string(self):
        run = RecordingRun([_text("started 7f31c2a1 cabinet-worker-W012\n")])
        provider = self.provider(run)
        provider.remember("W-1", "cabinet-b001-r1-w012",
                          str(self.spaces / "cabinet-b001-r1-w012"))
        launch = ["/bin/claude", "--restricted", "--tools", "Read,Edit",
                  "do the thing"]
        result = provider.create_terminal("W-1", launch)
        self.assertEqual(result["terminal_id"], "7f31c2a1")
        argv = run.argv[0]
        self.assertIsInstance(argv, list)
        self.assertIn("--bg", argv)
        # The prompt stays the last positional argument and is never joined
        # into a single command string.
        self.assertEqual(argv[-1], "do the thing")
        self.assertEqual(run.cwds[0], str(self.spaces / "cabinet-b001-r1-w012"))

    def test_listing_reading_and_closing_use_the_background_session_commands(self):
        run = RecordingRun([
            _ok([{"name": "cabinet-worker-W012", "sessionId": "S1",
                  "status": "running"}]),
            _text("worker output\n"),
            _text(""), _text(""),
        ])
        provider = self.provider(run)
        provider.remember("W-1", "cabinet-b001-r1-w012",
                          str(self.spaces / "cabinet-b001-r1-w012"))
        provider.list_terminals("W-1")
        provider.read_terminal("W-1", "7f31c2a1")
        provider.close_terminal("W-1", "7f31c2a1")
        self.assertEqual(run.argv[0][1:3], ["agents", "--json"])
        self.assertEqual(run.argv[1][1:], ["logs", "7f31c2a1"])
        self.assertEqual(run.argv[2][1:], ["stop", "7f31c2a1"])
        self.assertEqual(run.argv[3][1:], ["rm", "7f31c2a1"])

    def test_a_worktree_is_never_removed_by_the_provider(self):
        self.assertFalse(hasattr(workspace.LocalWorktreeProvider,
                                 "remove_workspace"))
        self.assertFalse(hasattr(workspace.LocalWorktreeProvider, "prune"))

    def test_the_containment_argument_names_the_disabled_hooks(self):
        run = RecordingRun()
        audit = self.provider(run).audit_setup_isolation()
        self.assertTrue(audit["contained"])
        self.assertEqual(audit["setup_commands"], [])
        self.assertIn(str(self.hooks), audit["hooks_path"])

    def test_a_repository_with_a_superset_setup_command_is_not_contained(self):
        config = self.root / ".superset"
        config.mkdir()
        (config / "config.json").write_text(
            json.dumps({"setupCommand": "npm install"}))
        run = RecordingRun()
        audit = self.provider(run).audit_setup_isolation()
        self.assertFalse(audit["contained"])
        self.assertIn("npm install", audit["reason"])


class WorkerContextTest(ServiceCase):
    """The prompt is a file Cabinet wrote, and it says what it must say."""

    def setUp(self):
        super().setUp()
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()
        self.service.worker_toolchain = fake_toolchain(self.root)

    def test_the_context_file_carries_the_approved_outcome_and_bounds(self):
        self.service.prepare_action(dict(action(), kind="workspace.reserve"))
        self.service.execute_action("A001")
        self.service.prepare_action(dict(action(key="create-12b"),
                                         action_id="A002"))
        self.service.execute_action("A002")
        self.service.prepare_action(dict(action(key="launch-12"),
                                         action_id="A003",
                                         kind="worker.launch"))
        self.service.execute_action("A003")
        recorded = self.store.get_action("A003")["evidence"]
        text = Path(recorded["context_file"]).read_text()
        for expected in (batch()["outcome"], "AC1", "W012", "app/",
                         "a" * 40, "cabinet-chief-test"):
            self.assertIn(expected, text)
        # `main` addresses the sender's own conversation. A worker is its own
        # session, so a context telling it to register at `main` would tell it
        # to talk to itself — observed live before this line existed.
        self.assertNotIn("to `main`", text)
        self.assertEqual(oct(os.stat(recorded["context_file"]).st_mode)[-3:],
                         "400")

    def test_the_context_file_lives_outside_the_worktree(self):
        self.service.prepare_action(dict(action(), kind="workspace.reserve"))
        self.service.execute_action("A001")
        self.service.prepare_action(dict(action(key="create-12b"),
                                         action_id="A002"))
        self.service.execute_action("A002")
        self.service.prepare_action(dict(action(key="launch-12"),
                                         action_id="A003",
                                         kind="worker.launch"))
        self.service.execute_action("A003")
        recorded = self.store.get_action("A003")["evidence"]
        worktree = self.store.get_assignment("W012")["workspace_path"]
        self.assertFalse(recorded["context_file"].startswith(worktree + "/"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
