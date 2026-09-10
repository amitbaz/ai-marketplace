"""Contract tests for the bounded service, the entrypoint and the launcher.

Three properties carry the task: an ordinary plugin-loaded connection can read
and nothing else; authority is decided before an executor is chosen, so a
forbidden kind fails with its F3 code rather than with "not built yet"; and
the per-launch capability never leaves the private file it is written to.

Run with:

    PYTHONPATH=plugins/cabinet/scripts:tests/cabinet \
      python3 -m unittest discover -s tests/cabinet -p test_service.py
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from support import (LAUNCH_SCRIPT, MCP_JSON, PLUGIN_ROOT, SERVICE_SCRIPT,
                     ServiceCase, action, batch, load_script, launch_context,
                     runtime_pythonpath, setup_scope)

from cabinet_runtime import profiles
from cabinet_runtime.errors import CabinetError
from cabinet_runtime.service import (CabinetService, MUTATION_TOOLS,
                                     READ_TOOLS, MAX_WAIT_SECONDS)

SESSION_ID = "6f1d0f1a-0c1a-4a8e-9a5f-9a2b3c4d5e6f"


def forbidden_action(kind="finance.pay", key="pay-1"):
    envelope = action(key)
    envelope["kind"] = kind
    return envelope


class OrdinaryConnectionTest(ServiceCase):
    """The plugin's own `.mcp.json` connection, with no launcher context."""

    restricted = False

    def test_every_mutation_needs_the_restricted_launch_context(self):
        for name in MUTATION_TOOLS:
            with self.subTest(tool=name):
                method = name[len("cabinet_"):]
                self.assertEqual(self.refuse(method, self.arguments(method)),
                                 "RESTRICTED_SESSION_REQUIRED")

    def test_reads_work(self):
        self.assertTrue(self.call("doctor")["checks"])
        self.assertEqual(self.call("snapshot")["company"]["repo"], self.repo)
        self.assertIn("documents", self.call("context"))
        self.assertIn("events", self.call("wait_events", {"after_seq": 0}))

    def test_only_the_read_tools_are_listed(self):
        listed = sorted(tool["name"] for tool in self.service.tools())
        self.assertEqual(listed, sorted(READ_TOOLS))

    def test_the_mutation_names_are_still_callable_so_the_refusal_is_reachable(self):
        self.assertTrue(self.service.has_tool("cabinet_propose_batch"))

    def test_the_doctor_reports_the_session_as_ordinary(self):
        statuses = {check["check"]: check["status"]
                    for check in self.call("doctor")["checks"]}
        self.assertEqual(statuses["launch"], "ordinary")

    def test_a_refused_launch_is_reported_rather_than_hidden(self):
        service = CabinetService(
            self.store, self.github, self.superset, self.clock, self.elicitor,
            profiles.build_profile, launch=None,
            launch_refusal={"code": "LAUNCH_HOST_MISMATCH",
                            "message": "started by process 42"})
        checks = {check["check"]: check
                  for check in service.call("cabinet_doctor", {})["checks"]}
        self.assertEqual(checks["launch"]["status"], "refused")
        self.assertIn("LAUNCH_HOST_MISMATCH", checks["launch"]["detail"])

    @staticmethod
    def arguments(method):
        """Well-formed arguments, so the refusal is about authority only."""

        return {
            "setup": {"scope": setup_scope()},
            "propose_batch": {"body": batch()},
            "request_owner_approval": {"batch_id": "B001", "revision": 1},
            "record_handoff": {"envelope": {"handoff_id": "H001"}},
            "update_handoff": {"handoff_id": "H001", "transition": "sent"},
            "prepare_action": {"envelope": action()},
            "execute_action": {"action_id": "A001"},
            "register_session": {"assignment_id": "W001",
                                 "registration": {"role": "implementer",
                                                  "native_address": "w1"}},
            "register_staff": {"role": "qa", "native_address": "qa"},
            "record_verdict": {"assignment_id": "W001", "revision_sha": "a" * 40,
                               "reviewer_role": "qa", "outcome": "pass"},
            "pause": {"reason": "owner asked"},
            "reconcile": {"observations": {}},
            "checkpoint": {"kind": "session_open", "summary": "s"},
            "acquire_lead": {},
            "export_company": {},
            "backup": {},
        }[method]


class LaunchContextTest(ServiceCase):

    def test_a_context_naming_another_company_is_refused(self):
        other = launch_context("/tmp/some-other-company", repo=self.repo)
        with self.assertRaises(CabinetError) as caught:
            self.rebuild(other)
        self.assertEqual(caught.exception.code, "LAUNCH_CONTEXT_INVALID")

    def test_a_context_naming_another_repository_is_refused(self):
        other = launch_context(self.root, repo="someone/else")
        with self.assertRaises(CabinetError) as caught:
            self.rebuild(other)
        self.assertEqual(caught.exception.code, "LAUNCH_CONTEXT_INVALID")

    def test_a_context_carrying_a_capability_is_refused(self):
        carrying = launch_context(self.root, repo=self.repo)
        carrying["capability"] = "abc123"
        with self.assertRaises(CabinetError) as caught:
            self.rebuild(carrying)
        self.assertEqual(caught.exception.code, "LAUNCH_CONTEXT_INVALID")
        self.assertIn("capability", caught.exception.message)

    def test_a_context_missing_a_field_is_refused(self):
        short = launch_context(self.root, repo=self.repo)
        del short["profile_digest"]
        with self.assertRaises(CabinetError) as caught:
            self.rebuild(short)
        self.assertEqual(caught.exception.code, "LAUNCH_CONTEXT_INVALID")

    def test_a_mutation_needs_this_process_to_hold_the_lease(self):
        from cabinet_runtime.store import own_process_identity

        pid, marker = own_process_identity()
        # A second lead takes the company; this service's generation is stale.
        self.store.acquire_lease("S2", pid, marker)
        self.store._generation = 1
        self.assertEqual(self.refuse("checkpoint",
                                     {"kind": "session_open", "summary": "s"}),
                         "LEASE_REQUIRED")

    def rebuild(self, launch):
        return CabinetService(self.store, self.github, self.superset,
                              self.clock, self.elicitor, profiles.build_profile,
                              launch=launch)


class ActionAuthorityTest(ServiceCase):
    """Authority is decided before an executor is chosen."""

    def test_a_forbidden_kind_fails_with_its_policy_code(self):
        self.call("prepare_action", {"envelope": forbidden_action()})
        self.assertEqual(self.refuse("execute_action", {"action_id": "A001"}),
                         "OPERATION_FORBIDDEN")
        self.assertEqual(self.github.calls, [])
        self.assertEqual(self.superset.calls, [])

    def test_a_forbidden_kind_is_refused_even_with_a_live_grant(self):
        self.approve_batch_through_fake_ui()
        self.call("prepare_action", {"envelope": forbidden_action("git.push",
                                                                 "push-1")})
        self.assertEqual(self.refuse("execute_action", {"action_id": "A001"}),
                         "OPERATION_FORBIDDEN")

    def test_an_unknown_kind_is_refused(self):
        self.call("prepare_action",
                  {"envelope": forbidden_action("weather.forecast", "w-1")})
        self.assertEqual(self.refuse("execute_action", {"action_id": "A001"}),
                         "UNKNOWN_OPERATION")

    def test_an_allowed_kind_without_a_grant_is_refused_before_execution(self):
        self.call("prepare_action", {"envelope": action()})
        self.assertEqual(self.refuse("execute_action", {"action_id": "A001"}),
                         "BATCH_NOT_APPROVED")
        self.assertEqual(self.superset.calls, [])

    def test_an_authorized_kind_reports_its_missing_executor(self):
        self.approve_batch_through_fake_ui()
        self.call("prepare_action", {"envelope": action()})
        with self.assertRaises(CabinetError) as caught:
            self.call("execute_action", {"action_id": "A001"})
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED_YET")
        self.assertIn("workspace.create", caught.exception.message)
        self.assertEqual(self.superset.calls, [])

    def test_an_unknown_action_identifier_is_refused(self):
        self.assertEqual(self.refuse("execute_action", {"action_id": "A404"}),
                         "ACTION_NOT_FOUND")

    def test_preparing_is_not_permission_to_execute(self):
        prepared = self.call("prepare_action", {"envelope": action()})
        self.assertEqual(prepared["state"], "prepared")
        self.assertEqual(self.refuse("execute_action", {"action_id": "A001"}),
                         "BATCH_NOT_APPROVED")


class DeferredOperationTest(ServiceCase):
    """Operations whose owners are later tasks refuse by a stable code."""

    def test_each_deferred_operation_names_its_owning_task(self):
        cases = {
            "reconcile": {"observations": {}},
        }
        for method, arguments in cases.items():
            with self.subTest(tool=method):
                with self.assertRaises(CabinetError) as caught:
                    self.call(method, arguments)
                self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED_YET")
                self.assertRegex(caught.exception.message, r"\b(O[1-5]|A[1-4])\b")


class ImplementedOperationTest(ServiceCase):

    def test_propose_batch_freezes_a_revision(self):
        body = batch()
        body["batch_id"] = "B002"
        stored = self.call("propose_batch", {"body": body})
        self.assertEqual(stored["state"], "proposed")
        self.assertEqual(len(stored["digest"]), 64)

    def test_acquire_lead_bumps_the_generation(self):
        before = self.store.get_lease()["generation"]
        result = self.call("acquire_lead", {"session_id": "S9"})
        self.assertEqual(result["generation"], before + 1)

    def test_pause_fences_new_actions(self):
        self.call("pause", {"reason": "owner asked"})
        self.assertTrue(self.call("snapshot")["company"]["paused"])
        self.assertEqual(self.refuse("prepare_action", {"envelope": action()}),
                         "PAUSED")

    def test_checkpoint_records_an_event(self):
        event = self.call("checkpoint", {"kind": "batch_end",
                                         "summary": "development verified"})
        self.assertEqual(event["kind"], "checkpoint")
        self.assertEqual(event["payload"]["kind"], "batch_end")

    def test_an_unnamed_checkpoint_kind_is_refused(self):
        self.assertEqual(self.refuse("checkpoint", {"kind": "release",
                                                    "summary": "s"}),
                         "FIELD_INVALID")

    def test_export_company_writes_the_views(self):
        result = self.call("export_company")
        for name in result["views"]:
            self.assertTrue((self.store.views_dir / name).exists())

    def test_backup_writes_a_manifest_under_the_company(self):
        manifest = self.call("backup")
        destination = Path(manifest["destination"])
        self.assertTrue(destination.is_dir())
        self.assertTrue(str(destination).startswith(str(self.store.backups_dir)))

    def test_two_backups_do_not_collide(self):
        first = self.call("backup")["destination"]
        second = self.call("backup")["destination"]
        self.assertNotEqual(first, second)

    def test_context_is_bounded(self):
        self.store.put_document("company.md", "x" * 5000, {"origin": "test"})
        result = self.call("context", {"max_bytes": 512})
        document = result["documents"][0]
        self.assertEqual(len(document["content"]), 512)
        self.assertTrue(document["truncated"])
        self.assertEqual(document["bytes"], 5000)

    def test_context_can_name_one_document(self):
        self.store.put_document("qa.md", "notes", {"origin": "test"})
        result = self.call("context", {"name": "qa.md"})
        self.assertEqual([item["name"] for item in result["documents"]],
                         ["qa.md"])

    def test_wait_events_returns_what_happened_after_a_cursor(self):
        cursor = self.store.max_event_seq()
        self.call("checkpoint", {"kind": "session_open", "summary": "s"})
        result = self.call("wait_events", {"after_seq": cursor})
        self.assertEqual([event["kind"] for event in result["events"]],
                         ["checkpoint"])
        self.assertGreater(result["max_event_seq"], cursor)

    def test_wait_events_caps_its_own_timeout(self):
        result = self.call("wait_events", {"after_seq": 0,
                                           "timeout_seconds": 600})
        self.assertEqual(result["timeout_seconds"], MAX_WAIT_SECONDS)

    def test_snapshot_carries_freshness_and_no_lease_identity(self):
        result = self.call("snapshot")
        self.assertIn("observed", result["freshness"])
        self.assertTrue(result["company"]["holds_lease"])
        self.assertNotIn("session_id", json.dumps(result["company"]))

    def test_setup_records_the_owner_grant(self):
        outcome = self.approve_setup_through_fake_ui()
        self.assertTrue(outcome["granted"])
        self.assertIsNotNone(self.store.active_setup_grant(self.repo))


class WaitLivenessTest(ServiceCase):
    """A parked wait must not stop the rest of the company being read."""

    def test_a_read_runs_while_a_wait_is_in_flight(self):
        self.service._sleep = time.sleep          # the fixture's is a no-op
        timings = {}

        def waiter():
            started = time.monotonic()
            # A cursor past every event, so nothing short-circuits the poll.
            self.call("wait_events", {"after_seq": 10 ** 9,
                                      "timeout_seconds": 2.0})
            timings["wait"] = time.monotonic() - started

        thread = threading.Thread(target=waiter)
        thread.start()
        self.addCleanup(thread.join, 10)
        time.sleep(0.3)                            # let the wait get parked

        started = time.monotonic()
        self.call("doctor")
        timings["read"] = time.monotonic() - started
        thread.join(timeout=10)

        self.assertLess(timings["read"], 0.5,
                        "a read waited %.2fs behind a parked wait_events"
                        % timings["read"])
        self.assertGreaterEqual(timings["wait"], 1.5)

    def test_a_write_runs_while_a_wait_is_in_flight(self):
        self.service._sleep = time.sleep
        thread = threading.Thread(
            target=lambda: self.call("wait_events",
                                     {"after_seq": 10 ** 9,
                                      "timeout_seconds": 2.0}))
        thread.start()
        self.addCleanup(thread.join, 10)
        time.sleep(0.3)
        started = time.monotonic()
        self.call("checkpoint", {"kind": "session_open", "summary": "s"})
        self.assertLess(time.monotonic() - started, 0.5)
        thread.join(timeout=10)


class ToolSchemaTest(ServiceCase):

    def test_the_exposed_names_match_the_profile_registry(self):
        self.assertEqual(sorted(self.service.tool_names()),
                         sorted("cabinet_%s" % name
                                for name in profiles.SERVICE_METHODS))

    def test_every_schema_is_closed(self):
        for tool in self.service.tools():
            with self.subTest(tool=tool["name"]):
                schema = tool["inputSchema"]
                self.assertIs(schema["additionalProperties"], False)
                self.assertEqual(schema["type"], "object")

    def test_an_unknown_argument_is_refused(self):
        self.assertEqual(self.refuse("pause", {"reason": "r", "force": True}),
                         "FIELD_UNKNOWN")

    def test_a_missing_required_argument_is_refused(self):
        self.assertEqual(self.refuse("pause", {}), "FIELD_MISSING")

    def test_a_wrongly_typed_argument_is_refused(self):
        self.assertEqual(self.refuse("request_owner_approval",
                                     {"batch_id": "B001", "revision": "1"}),
                         "FIELD_INVALID")

    def test_a_boolean_is_not_an_integer(self):
        self.assertEqual(self.refuse("request_owner_approval",
                                     {"batch_id": "B001", "revision": True}),
                         "FIELD_INVALID")

    def test_an_unknown_tool_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            self.service.call("cabinet_spend_money", {})
        self.assertEqual(caught.exception.code, "TOOL_UNKNOWN")

    def test_the_read_and_mutation_sets_cover_every_tool(self):
        self.assertEqual(sorted(set(READ_TOOLS) | set(MUTATION_TOOLS)),
                         sorted(self.service.tool_names()))
        self.assertEqual(set(READ_TOOLS) & set(MUTATION_TOOLS), set())


class SecrecyTest(ServiceCase):
    """No tool result and no exported view carries a launch capability."""

    def test_no_result_repeats_the_launch_context_secrets(self):
        self.approve_batch_through_fake_ui()
        self.call("checkpoint", {"kind": "session_open", "summary": "s"})
        results = [self.call("doctor"), self.call("snapshot"),
                   self.call("context"), self.call("export_company"),
                   self.call("wait_events", {"after_seq": 0})]
        text = json.dumps(results)
        for word in ("capability", "token", "secret", "password"):
            self.assertNotIn(word, text.lower())

    def test_the_exported_views_carry_no_capability(self):
        self.call("export_company")
        for view in sorted(self.store.views_dir.glob("*.md")):
            self.assertNotIn("capability", view.read_text().lower())


class EntrypointTest(unittest.TestCase):
    """`cabinet-service` resolves its company and verifies its launch."""

    def setUp(self):
        from cabinet_runtime.store import process_start_marker

        self.module = load_script(SERVICE_SCRIPT, "cabinet_service")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.private = self.home / "runtime" / "profiles"
        self.private.mkdir(parents=True)
        self.views = self.home / "views"
        self.views.mkdir()
        self.parent = os.getppid()
        self.parent_start = process_start_marker(self.parent)
        self.profile = profiles.build_profile(
            "chief-of-staff",
            {"assignment": "probe", "claude_path": sys.executable,
             "plugin_root": str(PLUGIN_ROOT),
             "mcp_config": str(self.private / "L1.mcp.json"),
             "settings_path": str(self.private / "L1.settings.json"),
             "session_id": SESSION_ID},
            str(self.views), home=str(self.home))

    def write(self, name, text, mode=0o600):
        path = self.private / name
        path.write_text(text)
        path.chmod(mode)
        return path

    def write_launch(self, capability="c" * 64, mode=0o600, settings=None,
                     profile=None, **overrides):
        """Write a complete, valid launch and return its environment."""

        body = profile if profile is not None else profiles.plain(self.profile)
        capability_file = self.write("L1.capability", capability, mode)
        self.write("L1.profile.json", json.dumps(body))
        self.write("L1.settings.json",
                   settings if settings is not None
                   else json.dumps(body["settings"]))
        record = {
            "kind": "restricted", "launch_id": "L1",
            "company_dir": str(self.home), "repo": "demo/company",
            "role": "chief-of-staff",
            "profile_path": str(self.private / "L1.settings.json"),
            "profile_body_path": str(self.private / "L1.profile.json"),
            "profile_digest": profiles.digest_of(body),
            "session_id": SESSION_ID,
            "host_pid": self.parent,
            "host_process_start": self.parent_start,
            "lease_generation": None,
            "capability_sha256": self.module.sha256_of(capability),
        }
        record.update(overrides)
        launch_file = self.write("L1.launch.json", json.dumps(record))
        return {"CABINET_LAUNCH_FILE": str(launch_file),
                "CABINET_CAPABILITY_FILE": str(capability_file)}

    def refuse(self, environ):
        with self.assertRaises(CabinetError) as caught:
            self.module.verify_launch(environ)
        return caught.exception.code

    # --- the capability ---------------------------------------------------

    def test_a_matching_launch_yields_a_context_without_the_secret(self):
        context = self.module.verify_launch(self.write_launch())
        self.assertEqual(context["kind"], "restricted")
        self.assertEqual(sorted(context),
                         sorted(field for field
                                in self.module.LAUNCH_CONTEXT_FIELDS
                                if field != "background"))
        for absent in ("capability", "capability_sha256", "host_pid",
                       "host_process_start", "lease_generation"):
            self.assertNotIn(absent, context)

    def test_a_mismatched_capability_is_refused(self):
        environ = self.write_launch()
        Path(environ["CABINET_CAPABILITY_FILE"]).write_text("guessed")
        self.assertEqual(self.refuse(environ), "CAPABILITY_INVALID")

    def test_a_readable_capability_file_is_refused(self):
        self.assertEqual(self.refuse(self.write_launch(mode=0o644)),
                         "UNSAFE_PATH")

    def test_a_symlinked_capability_file_is_refused(self):
        environ = self.write_launch()
        real = Path(environ["CABINET_CAPABILITY_FILE"])
        link = real.parent / "L1.link"
        link.symlink_to(real)
        environ["CABINET_CAPABILITY_FILE"] = str(link)
        self.assertEqual(self.refuse(environ), "UNSAFE_PATH")

    def test_a_record_naming_another_company_is_refused(self):
        self.assertEqual(self.refuse(self.write_launch(
            company_dir="/tmp/elsewhere")), "LAUNCH_CONTEXT_INVALID")

    def test_a_profile_outside_the_private_directory_is_refused(self):
        outside = self.home / "L1.profile.json"
        outside.write_text(json.dumps(profiles.plain(self.profile)))
        outside.chmod(0o600)
        self.assertEqual(self.refuse(self.write_launch(
            profile_body_path=str(outside))), "LAUNCH_CONTEXT_INVALID")

    def test_no_launcher_variables_means_no_context(self):
        self.assertIsNone(self.module.verify_launch({}))

    def test_half_a_launch_context_is_refused_rather_than_downgraded(self):
        environ = self.write_launch()
        del environ["CABINET_CAPABILITY_FILE"]
        self.assertEqual(self.refuse(environ), "LAUNCH_CONTEXT_INVALID")

    def test_a_record_missing_a_field_is_refused(self):
        environ = self.write_launch()
        record = json.loads(Path(environ["CABINET_LAUNCH_FILE"]).read_text())
        del record["profile_digest"]
        self.write("L1.launch.json", json.dumps(record))
        self.assertEqual(self.refuse(environ), "LAUNCH_CONTEXT_INVALID")

    # --- the profile binding ----------------------------------------------

    def test_a_wrong_profile_digest_is_refused(self):
        self.assertEqual(self.refuse(self.write_launch(
            profile_digest="d" * 64)), "LAUNCH_PROFILE_MISMATCH")

    def test_settings_swapped_under_the_profile_are_refused(self):
        self.assertEqual(self.refuse(self.write_launch(
            settings=json.dumps({"permissions": {"defaultMode": "auto"}}))),
            "LAUNCH_PROFILE_MISMATCH")

    def test_a_profile_widened_after_the_record_was_written_is_refused(self):
        body = profiles.plain(self.profile)
        body["tools"] = list(body["tools"]) + ["Bash"]
        environ = self.write_launch()
        self.write("L1.profile.json", json.dumps(body))
        # `verify_profile` refuses the shell before the digest is even reached.
        self.assertIn(self.refuse(environ),
                      ("PROFILE_TOOLS_FORBIDDEN", "LAUNCH_PROFILE_MISMATCH"))

    def test_a_profile_naming_another_session_is_refused(self):
        body = profiles.plain(self.profile)
        environ = self.write_launch(profile=body,
                                    session_id="00000000-0000-4000-8000-000000000000")
        self.assertEqual(self.refuse(environ), "LAUNCH_PROFILE_MISMATCH")

    def test_an_unparsable_profile_is_refused(self):
        environ = self.write_launch()
        self.write("L1.profile.json", "{not json")
        self.assertEqual(self.refuse(environ), "LAUNCH_PROFILE_MISMATCH")

    # --- the host binding --------------------------------------------------

    def test_a_record_written_by_another_process_is_refused(self):
        self.assertEqual(self.refuse(self.write_launch(
            host_pid=os.getpid())), "LAUNCH_HOST_MISMATCH")

    def test_a_reused_process_identifier_is_refused(self):
        self.assertEqual(self.refuse(self.write_launch(
            host_process_start="lstart:Thu Jan  1 00:00:00 1970")),
            "LAUNCH_HOST_MISMATCH")

    # --- the generation binding -------------------------------------------

    def test_an_unbound_record_passes_the_generation_check(self):
        self.module.check_generation({"lease_generation": None}, None)

    def test_a_record_bound_to_the_current_generation_passes(self):
        self.module.check_generation({"lease_generation": 2},
                                     _FakeLease(2))

    def test_a_record_another_lead_overtook_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            self.module.check_generation({"lease_generation": 2}, _FakeLease(3))
        self.assertEqual(caught.exception.code, "LAUNCH_GENERATION_STALE")

    def test_a_record_bound_to_a_company_with_no_lead_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            self.module.check_generation({"lease_generation": 2},
                                         _FakeLease(None))
        self.assertEqual(caught.exception.code, "LAUNCH_GENERATION_STALE")

    def test_renewal_binds_the_record_and_keeps_it_private(self):
        environ = self.write_launch()
        launch_file = environ["CABINET_LAUNCH_FILE"]
        record = self.module.renew_launch(launch_file, 7)
        self.assertEqual(record["lease_generation"], 7)
        self.assertEqual(
            json.loads(Path(launch_file).read_text())["lease_generation"], 7)
        self.assertEqual(stat.S_IMODE(os.stat(launch_file).st_mode), 0o600)
        # The renewed record still verifies, so a reconnect works.
        self.module.verify_launch(environ)

    # --- ordinary identity -------------------------------------------------

    def test_the_repository_is_read_from_the_origin_remote(self):
        for url, expected in (
                ("git@github.com:amitbaz/cabinet.git", "amitbaz/cabinet"),
                ("https://github.com/amitbaz/cabinet.git", "amitbaz/cabinet"),
                ("https://github.com/amitbaz/cabinet", "amitbaz/cabinet"),
                ("ssh://git@github.com/amitbaz/cabinet.git", "amitbaz/cabinet"),
                ("/local/path/only", None),
                ("", None)):
            with self.subTest(url=url):
                self.assertEqual(self.module.repo_from_origin(url), expected)

    def test_the_company_directory_uses_the_legacy_slug(self):
        directory = self.module.company_directory("amitbaz/cabinet",
                                                  {"CABINET_HOME": "/c"})
        self.assertEqual(str(directory), "/c/repos/amitbaz-cabinet")


class _FakeLease:
    """A store stand-in whose only fact is the current lease generation."""

    def __init__(self, generation):
        self._generation = generation

    def get_lease(self):
        if self._generation is None:
            return None
        return {"generation": self._generation}


class PackagedConnectionTest(unittest.TestCase):

    def test_the_plugin_declares_the_ordinary_stdio_connection(self):
        declared = json.loads(MCP_JSON.read_text())
        server = declared["mcpServers"]["cabinet"]
        self.assertEqual(server["command"], "python3")
        self.assertEqual(server["args"],
                         ["${CLAUDE_PLUGIN_ROOT}/scripts/cabinet-service"])
        self.assertEqual(list(declared["mcpServers"]), ["cabinet"])

    def test_both_entrypoints_are_executable(self):
        for script in (SERVICE_SCRIPT, LAUNCH_SCRIPT):
            with self.subTest(script=script.name):
                self.assertTrue(os.access(str(script), os.X_OK))

    def test_the_packaged_file_list_names_the_new_files(self):
        listed = (PLUGIN_ROOT / "FILES.md").read_text()
        for name in ("cabinet-service", "cabinet-launch", "rpc.py",
                     "service.py", ".mcp.json"):
            with self.subTest(name=name):
                self.assertIn(name, listed)


class LauncherTest(unittest.TestCase):
    """`cabinet-launch --dry-run`, run as the real process."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name)
        environ = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                   "HOME": str(cls.home),
                   "CABINET_HOME": str(cls.home / "cabinet"),
                   "PYTHONPATH": runtime_pythonpath()}
        cls.completed = subprocess.run(
            [sys.executable, str(LAUNCH_SCRIPT), "--dry-run",
             "--repo", "demo/company", "--assignment", "smoke",
             "--claude", sys.executable,
             "--plugin-root", str(PLUGIN_ROOT),
             "--session-id", SESSION_ID],
            capture_output=True, text=True, env=environ, timeout=60)
        cls.report = json.loads(cls.completed.stdout or "{}")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_dry_run_succeeds(self):
        self.assertEqual(self.completed.returncode, 0, self.completed.stderr)

    def test_the_printed_argv_is_the_profile_argv(self):
        launcher = load_script(LAUNCH_SCRIPT, "cabinet_launch")
        profile = profiles.build_profile(
            "chief-of-staff",
            {"assignment": "smoke", "claude_path": sys.executable,
             "plugin_root": str(PLUGIN_ROOT),
             "mcp_config": self.report["mcp_config"],
             "settings_path": self.report["settings_path"],
             "session_id": SESSION_ID,
             "peer_registry": self.report["peer_registry"]},
            self.report["public_context"],
            home=self.report["home"],
            include_service_tools_in_tools_flag=(
                launcher.INCLUDE_SERVICE_TOOLS_IN_TOOLS_FLAG))
        self.assertEqual(self.report["argv"], list(profile["argv"]))
        self.assertEqual(self.report["profile_digest"], profile["digest"])

    def test_the_capability_never_appears_in_the_output(self):
        capability = Path(self.report["capability_file"]).read_text().strip()
        self.assertGreaterEqual(len(capability), 32)
        self.assertNotIn(capability, self.completed.stdout)
        self.assertNotIn(capability, self.completed.stderr)
        self.assertNotIn(capability, json.dumps(self.report))

    def test_the_capability_is_not_in_the_command_line_or_the_environment(self):
        capability = Path(self.report["capability_file"]).read_text().strip()
        for value in self.report["argv"]:
            self.assertNotIn(capability, value)
        for value in self.report["env"].values():
            self.assertNotIn(capability, str(value))

    def test_the_private_files_are_owner_only(self):
        for key in ("settings_path", "mcp_config", "capability_file",
                    "launch_file", "peer_registry", "profile_body_path"):
            with self.subTest(file=key):
                mode = stat.S_IMODE(os.stat(self.report[key]).st_mode)
                self.assertEqual(mode, 0o600)

    def test_the_private_files_live_under_the_company_runtime(self):
        runtime = str(Path(self.report["company_dir"]) / "runtime" / "profiles")
        for key in ("settings_path", "mcp_config", "capability_file",
                    "launch_file", "profile_body_path"):
            with self.subTest(file=key):
                self.assertTrue(self.report[key].startswith(runtime))

    def test_the_mcp_config_names_the_service_and_carries_no_secret(self):
        declared = json.loads(Path(self.report["mcp_config"]).read_text())
        server = declared["mcpServers"]["cabinet"]
        self.assertTrue(server["args"][0].endswith("scripts/cabinet-service"))
        self.assertEqual(server["env"]["CABINET_LAUNCH_FILE"],
                         self.report["launch_file"])
        capability = Path(self.report["capability_file"]).read_text().strip()
        self.assertNotIn(capability, json.dumps(declared))

    def test_the_child_environment_carries_the_profile_variables(self):
        self.assertEqual(self.report["env"]["CABINET_PROFILE_KIND"], "chief")
        self.assertEqual(self.report["env"]["CABINET_CHIEF_NAME"],
                         "cabinet-chief-smoke")
        self.assertEqual(self.report["env"]["CABINET_PEER_REGISTRY"],
                         self.report["peer_registry"])

    def test_the_written_settings_are_the_verified_profile_settings(self):
        written = json.loads(Path(self.report["settings_path"]).read_text())
        self.assertEqual(written["permissions"]["defaultMode"], "manual")
        self.assertEqual(written["crossSessionInbound"], "accept")
        self.assertNotIn("hooks", written)

    def test_the_launch_record_holds_only_the_capability_digest(self):
        record = json.loads(Path(self.report["launch_file"]).read_text())
        capability = Path(self.report["capability_file"]).read_text().strip()
        self.assertNotIn(capability, json.dumps(record))
        self.assertEqual(len(record["capability_sha256"]), 64)

    def test_the_record_binds_the_process_that_would_have_run_claude(self):
        record = json.loads(Path(self.report["launch_file"]).read_text())
        self.assertEqual(record["host_pid"], self.report["host_pid"])
        self.assertTrue(record["host_process_start"])
        self.assertIsNone(record["lease_generation"])

    def test_the_profile_the_launcher_wrote_verifies_against_its_record(self):
        module = load_script(SERVICE_SCRIPT, "cabinet_service_launched")
        record = json.loads(Path(self.report["launch_file"]).read_text())
        body = module.check_profile(record)
        self.assertEqual(profiles.digest_of(body),
                         self.report["profile_digest"])

    def test_a_dry_run_record_cannot_start_a_writing_service(self):
        """A dry run never exec'd Claude, so nothing was bound to it.

        This is the host binding doing its job rather than a gap: the record
        names a launcher process that exited, and no live parent matches it.
        """

        module = load_script(SERVICE_SCRIPT, "cabinet_service_launched")
        with self.assertRaises(CabinetError) as caught:
            module.verify_launch(
                {"CABINET_LAUNCH_FILE": self.report["launch_file"],
                 "CABINET_CAPABILITY_FILE": self.report["capability_file"]})
        self.assertEqual(caught.exception.code, "LAUNCH_HOST_MISMATCH")


if __name__ == "__main__":
    unittest.main()
