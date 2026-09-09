"""Contract tests for the Cabinet transactional company store.

Repository-only suite (see AGENTS.md). Python 3 standard library, plain
`unittest`, one temporary directory per test.

Run:
    PYTHONPATH=plugins/cabinet/scripts:tests/cabinet \
        python3 -m unittest discover -s tests/cabinet -p test_store.py -v
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cabinet_runtime.errors import CabinetError
from cabinet_runtime.exports import VIEW_NAMES
from cabinet_runtime.migration import migrate_documents
from cabinet_runtime.store import Store

from support import (
    CountingClock,
    FakeClock,
    action,
    always_alive,
    batch,
    copy_legacy_company,
    dead_processes,
    file_state,
    runtime_pythonpath,
)


class StoreCase(unittest.TestCase):
    """One temporary company directory per test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = FakeClock()

    def open_store(self, root=None, **kwargs):
        store = Store(root or self.root, self.clock, **kwargs).open()
        self.addCleanup(store.close)
        return store


class StateContract(StoreCase):
    """The two cases named in the task brief, verbatim."""

    def test_proposed_revision_is_frozen_across_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d), FakeClock()).open()
            source = batch()
            saved = store.propose_batch(source)
            source["in_scope"].append("Payments")
            store.close()
            reopened = Store(Path(d), FakeClock()).open()
            actual = reopened.get_batch("B001", 1)
            self.assertEqual(actual["digest"], saved["digest"])
            self.assertEqual(actual["body"]["in_scope"], ["Invitation check"])
            reopened.close()

    def test_conflicting_retry_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d), FakeClock()).open()
            store.propose_batch(batch())
            first = store.prepare_action(action())
            self.assertEqual(store.prepare_action(action())["action_id"], first["action_id"])
            changed = action()
            changed["payload"]["issue_number"] = 13
            with self.assertRaises(CabinetError) as caught:
                store.prepare_action(changed)
            self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
            store.close()


class DigestContract(StoreCase):
    def test_digest_matches_the_canonical_formula(self):
        store = self.open_store()
        body = batch()
        saved = store.propose_batch(body)
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.assertEqual(saved["digest"], hashlib.sha256(raw).hexdigest())

    def test_key_order_does_not_change_the_digest(self):
        store = self.open_store()
        first = store.propose_batch(batch())
        reordered = dict(reversed(list(batch().items())))
        again = store.propose_batch(reordered)
        self.assertEqual(again["digest"], first["digest"])

    def test_a_changed_body_at_the_same_revision_is_a_conflict(self):
        store = self.open_store()
        store.propose_batch(batch())
        changed = batch()
        changed["goal"] = "Invite two testers"
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(changed)
        self.assertEqual(caught.exception.code, "REVISION_CONFLICT")


class ValidationContract(StoreCase):
    def test_unknown_field_is_refused(self):
        store = self.open_store()
        body = batch()
        body["deploy_now"] = True
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(body)
        self.assertEqual(caught.exception.code, "FIELD_UNKNOWN")

    def test_short_base_sha_is_refused(self):
        store = self.open_store()
        body = batch()
        body["base_sha"] = "abc"
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(body)
        self.assertEqual(caught.exception.code, "FIELD_INVALID")

    def test_uppercase_base_sha_is_refused(self):
        store = self.open_store()
        body = batch()
        body["base_sha"] = "A" * 40
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(body)
        self.assertEqual(caught.exception.code, "FIELD_INVALID")

    def test_owned_path_escaping_the_repository_is_refused(self):
        store = self.open_store()
        body = batch()
        body["owned_paths"] = ["../secrets/"]
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(body)
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")

    def test_absolute_owned_path_is_refused(self):
        store = self.open_store()
        body = batch()
        body["owned_paths"] = ["/etc/"]
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(body)
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")

    def test_missing_acceptance_is_refused(self):
        store = self.open_store()
        body = batch()
        del body["acceptance"]
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(body)
        self.assertEqual(caught.exception.code, "FIELD_MISSING")

    def test_action_envelope_rejects_an_unknown_field(self):
        store = self.open_store()
        store.propose_batch(batch())
        envelope = action()
        envelope["shell"] = "rm -rf /"
        with self.assertRaises(CabinetError) as caught:
            store.prepare_action(envelope)
        self.assertEqual(caught.exception.code, "FIELD_UNKNOWN")


class IdentityContract(StoreCase):
    def test_identity_file_is_written_with_private_permissions(self):
        store = self.open_store()
        store.propose_batch(batch())
        identity = self.root / "runtime" / "identity.json"
        recorded = json.loads(identity.read_text())
        self.assertEqual(recorded["repo"], "demo/company")
        self.assertEqual(recorded["slug"], "demo-company")
        self.assertEqual(oct(identity.stat().st_mode & 0o777), "0o600")
        runtime = self.root / "runtime"
        self.assertEqual(oct(runtime.stat().st_mode & 0o777), "0o700")
        database = runtime / "cabinet.sqlite3"
        self.assertEqual(oct(database.stat().st_mode & 0o777), "0o600")

    def test_hyphen_slug_collision_is_refused(self):
        store = Store(self.root, self.clock, repo="a-b/c").open()
        self.assertEqual(store.identity["slug"], "a-b-c")
        store.close()
        with self.assertRaises(CabinetError) as caught:
            Store(self.root, self.clock, repo="a/b-c").open()
        self.assertEqual(caught.exception.code, "IDENTITY_CONFLICT")

    def test_a_batch_for_another_repository_is_refused(self):
        store = self.open_store(repo="demo/company")
        body = batch()
        body["repo"] = "other/company"
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(body)
        self.assertEqual(caught.exception.code, "IDENTITY_CONFLICT")

    def test_malformed_repository_name_is_refused(self):
        with self.assertRaises(CabinetError) as caught:
            Store(self.root, self.clock, repo="not-a-repo").open()
        self.assertEqual(caught.exception.code, "REPO_INVALID")

    def test_symlinked_private_directory_is_refused(self):
        elsewhere = Path(self.tmp.name).parent / (Path(self.tmp.name).name + "-elsewhere")
        elsewhere.mkdir()
        self.addCleanup(lambda: os.rmdir(elsewhere) if elsewhere.exists() else None)
        os.symlink(elsewhere, self.root / "runtime")
        with self.assertRaises(CabinetError) as caught:
            Store(self.root, self.clock).open()
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")

    def test_symlinked_database_file_is_refused(self):
        (self.root / "runtime").mkdir(mode=0o700)
        outside = Path(self.tmp.name) / "outside.sqlite3"
        outside.write_bytes(b"")
        os.symlink(outside, self.root / "runtime" / "cabinet.sqlite3")
        with self.assertRaises(CabinetError) as caught:
            Store(self.root, self.clock).open()
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")


class EventContract(StoreCase):
    def test_events_are_append_only(self):
        store = self.open_store()
        store.propose_batch(batch())
        store.close()
        raw = sqlite3.connect(str(self.root / "runtime" / "cabinet.sqlite3"))
        self.addCleanup(raw.close)
        with self.assertRaises(sqlite3.DatabaseError):
            raw.execute("UPDATE events SET kind = 'tampered'")
        with self.assertRaises(sqlite3.DatabaseError):
            raw.execute("DELETE FROM events")

    def test_cursor_follows_sequence_not_time(self):
        store = Store(self.root, CountingClock()).open()
        self.addCleanup(store.close)
        first = store.append_event("note.recorded", "N1", 1, {"n": 1})
        second = store.append_event("note.recorded", "N2", 1, {"n": 2})
        third = store.append_event("note.recorded", "N3", 1, {"n": 3})
        self.assertLess(first["seq"], second["seq"])
        self.assertLess(second["seq"], third["seq"])
        self.assertGreater(first["time"], third["time"])
        later = store.get_events(after_seq=first["seq"])
        self.assertEqual([row["entity_id"] for row in later], ["N2", "N3"])

    def test_state_change_adds_an_event_rather_than_editing_one(self):
        store = self.open_store()
        store.propose_batch(batch())
        before = store.max_event_seq()
        store.set_batch_state("B001", 1, "approved")
        after = store.get_events(after_seq=before)
        self.assertEqual([row["kind"] for row in after], ["batch.state_changed"])
        self.assertEqual(store.get_batch("B001", 1)["state"], "approved")

    def test_illegal_batch_transition_is_refused(self):
        store = self.open_store()
        store.propose_batch(batch())
        with self.assertRaises(CabinetError) as caught:
            store.set_batch_state("B001", 1, "completed")
        self.assertEqual(caught.exception.code, "INVALID_TRANSITION")


class LeaseContract(StoreCase):
    def test_live_lead_blocks_a_second_acquisition(self):
        store = self.open_store(process_alive=always_alive)
        store.acquire_lease("S1", 4321, "start-marker-1")
        other = self.open_store(process_alive=always_alive)
        with self.assertRaises(CabinetError) as caught:
            other.acquire_lease("S2", 8765, "start-marker-2")
        self.assertEqual(caught.exception.code, "LEAD_ACTIVE")

    def test_expired_heartbeat_alone_does_not_hand_over_the_lease(self):
        store = self.open_store(process_alive=always_alive)
        store.acquire_lease("S1", 4321, "start-marker-1")
        store.set_lease_last_seen("1999-01-01T00:00:00Z")
        other = self.open_store(process_alive=always_alive)
        with self.assertRaises(CabinetError) as caught:
            other.acquire_lease("S2", 8765, "start-marker-2")
        self.assertEqual(caught.exception.code, "LEAD_ACTIVE")

    def test_dead_lead_releases_the_lease_and_bumps_the_generation(self):
        store = self.open_store(process_alive=always_alive)
        first = store.acquire_lease("S1", 4321, "start-marker-1")
        other = self.open_store(process_alive=dead_processes(4321))
        second = other.acquire_lease("S2", 8765, "start-marker-2")
        self.assertEqual(first["generation"], 1)
        self.assertEqual(second["generation"], 2)

    def test_reused_pid_with_a_different_start_marker_is_not_the_old_lead(self):
        seen = []

        def probe(pid, process_start):
            seen.append((pid, process_start))
            return process_start == "start-marker-2"

        store = self.open_store(process_alive=always_alive)
        store.acquire_lease("S1", 4321, "start-marker-1")
        other = self.open_store(process_alive=probe)
        second = other.acquire_lease("S2", 4321, "start-marker-2")
        self.assertEqual(seen, [(4321, "start-marker-1")])
        self.assertEqual(second["generation"], 2)

    def test_fenced_generation_cannot_mutate(self):
        store = self.open_store(process_alive=always_alive)
        store.acquire_lease("S1", 4321, "start-marker-1")
        other = self.open_store(process_alive=dead_processes(4321))
        other.acquire_lease("S2", 8765, "start-marker-2")
        with self.assertRaises(CabinetError) as caught:
            store.propose_batch(batch())
        self.assertEqual(caught.exception.code, "LEASE_FENCED")
        self.assertEqual(other.propose_batch(batch())["revision"], 1)

    def test_pause_fences_new_actions(self):
        store = self.open_store(process_alive=always_alive)
        store.acquire_lease("S1", 4321, "start-marker-1")
        store.propose_batch(batch())
        store.pause("Owner asked for a stop")
        with self.assertRaises(CabinetError) as caught:
            store.prepare_action(action())
        self.assertEqual(caught.exception.code, "PAUSED")
        store.resume()
        self.assertEqual(store.prepare_action(action())["state"], "prepared")

    def test_pause_without_a_lease_is_refused(self):
        store = self.open_store()
        with self.assertRaises(CabinetError) as caught:
            store.pause("no lead")
        self.assertEqual(caught.exception.code, "LEASE_REQUIRED")

    def test_this_live_process_blocks_a_second_lead_with_the_real_probe(self):
        from cabinet_runtime.store import process_start_marker

        store = self.open_store()
        store.acquire_lease("S1", os.getpid(), process_start_marker())
        other = self.open_store()
        with self.assertRaises(CabinetError) as caught:
            other.acquire_lease("S2", os.getpid(), process_start_marker())
        self.assertEqual(caught.exception.code, "LEAD_ACTIVE")

    def test_process_start_marker_is_stable_for_this_process(self):
        from cabinet_runtime.store import process_start_marker

        marker = process_start_marker()
        self.assertTrue(marker)
        self.assertEqual(marker, process_start_marker(os.getpid()))

    def test_default_liveness_probe_sees_this_process(self):
        from cabinet_runtime.store import default_process_alive, process_start_marker

        self.assertTrue(default_process_alive(os.getpid(), process_start_marker()))
        self.assertFalse(default_process_alive(os.getpid(), "not-the-real-marker"))


class ActionContract(StoreCase):
    def test_prepared_action_is_readable_by_id(self):
        store = self.open_store()
        store.propose_batch(batch())
        prepared = store.prepare_action(action())
        stored = store.get_action(prepared["action_id"])
        self.assertEqual(stored["state"], "prepared")
        self.assertEqual(stored["payload"], {"issue_number": 12})

    def test_unknown_action_is_reported(self):
        store = self.open_store()
        with self.assertRaises(CabinetError) as caught:
            store.get_action("A999")
        self.assertEqual(caught.exception.code, "ACTION_NOT_FOUND")

    def test_action_state_moves_through_the_recorded_machine(self):
        store = self.open_store()
        store.propose_batch(batch())
        store.prepare_action(action())
        store.update_action("A001", "running")
        store.update_action("A001", "uncertain", external_ref={"workspace_id": "W-1"})
        stored = store.get_action("A001")
        self.assertEqual(stored["state"], "uncertain")
        self.assertEqual(stored["external_ref"], {"workspace_id": "W-1"})

    def test_action_cannot_skip_to_verified(self):
        store = self.open_store()
        store.propose_batch(batch())
        store.prepare_action(action())
        with self.assertRaises(CabinetError) as caught:
            store.update_action("A001", "verified")
        self.assertEqual(caught.exception.code, "INVALID_TRANSITION")

    def test_action_for_an_unknown_batch_is_refused(self):
        store = self.open_store(repo="demo/company")
        with self.assertRaises(CabinetError) as caught:
            store.prepare_action(action())
        self.assertEqual(caught.exception.code, "BATCH_NOT_FOUND")


class AssignmentContract(StoreCase):
    def test_two_concurrent_claims_yield_one_assignment(self):
        store = self.open_store()
        store.propose_batch(batch())
        rival = self.open_store()
        first = store.reserve_assignment("W001", "B001", 1, "implementer",
                                         work_key="B001:r1:issue12", issue_number=12)
        self.assertEqual(first["state"], "reserved")
        with self.assertRaises(CabinetError) as caught:
            rival.reserve_assignment("W002", "B001", 1, "implementer",
                                     work_key="B001:r1:issue12", issue_number=12)
        self.assertEqual(caught.exception.code, "ASSIGNMENT_CONFLICT")
        self.assertEqual(len(store.get_assignments()), 1)

    def test_unknown_assignment_is_reported(self):
        store = self.open_store()
        with self.assertRaises(CabinetError) as caught:
            store.get_assignment("W404")
        self.assertEqual(caught.exception.code, "ASSIGNMENT_NOT_FOUND")

    def test_a_released_work_item_can_be_claimed_again(self):
        store = self.open_store()
        store.propose_batch(batch())
        store.reserve_assignment("W001", "B001", 1, "implementer",
                                 work_key="B001:r1:issue12", issue_number=12)
        store.set_assignment_state("W001", "cancelled")
        again = store.reserve_assignment("W002", "B001", 1, "implementer",
                                         work_key="B001:r1:issue12", issue_number=12)
        self.assertEqual(again["assignment_id"], "W002")


class FaultContract(StoreCase):
    def test_failure_between_event_and_projection_rolls_both_back(self):
        store = self.open_store()

        def explode(event):
            raise RuntimeError("injected fault between the two writes")

        store.after_event_hook = explode
        with self.assertRaises(RuntimeError):
            store.propose_batch(batch())
        store.after_event_hook = None
        self.assertEqual(store.get_events(after_seq=0), [])
        with self.assertRaises(CabinetError) as caught:
            store.get_batch("B001", 1)
        self.assertEqual(caught.exception.code, "BATCH_NOT_FOUND")
        self.assertEqual(store.propose_batch(batch())["revision"], 1)

    def test_commit_survives_process_termination(self):
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from cabinet_runtime.store import Store\n"
            "from support import batch, FakeClock\n"
            "import os\n"
            "store = Store(Path(sys.argv[1]), FakeClock()).open()\n"
            "store.propose_batch(batch())\n"
            "sys.stdout.flush()\n"
            "os._exit(0)\n"
        )
        env = dict(os.environ, PYTHONPATH=runtime_pythonpath())
        finished = subprocess.run([sys.executable, "-c", script, str(self.root)],
                                  env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        store = self.open_store()
        self.assertEqual(store.get_batch("B001", 1)["state"], "proposed")
        self.assertEqual([row["kind"] for row in store.get_events(0)], ["batch.proposed"])

    def test_newer_schema_opens_read_only(self):
        store = self.open_store()
        store.propose_batch(batch())
        store.close()
        raw = sqlite3.connect(str(self.root / "runtime" / "cabinet.sqlite3"))
        raw.execute("PRAGMA user_version = 99")
        raw.close()
        reopened = self.open_store()
        self.assertTrue(reopened.read_only)
        self.assertEqual(reopened.get_batch("B001", 1)["state"], "proposed")
        with self.assertRaises(CabinetError) as caught:
            reopened.propose_batch(batch())
        self.assertEqual(caught.exception.code, "SCHEMA_TOO_NEW")


class BackupContract(StoreCase):
    def test_backup_is_consistent_while_a_write_lands(self):
        store = self.open_store()
        store.propose_batch(batch())
        writer = self.open_store()
        state = {"written": False}

        def interfere(status, remaining, total):
            if not state["written"]:
                state["written"] = True
                writer.append_event("note.recorded", "N1", 1, {"during": "backup"})

        destination = self.root / "backups" / "one"
        manifest = store.backup(destination, progress=interfere)
        self.assertTrue(state["written"])
        self.assertEqual(manifest["repo"], "demo/company")
        self.assertTrue((destination / "manifest.json").exists())

        restored = self.root / "restored"
        report = Store.restore(destination, restored)
        self.assertEqual(report["max_event_seq"], manifest["max_event_seq"])
        raw = sqlite3.connect(str(restored / "runtime" / "cabinet.sqlite3"))
        self.addCleanup(raw.close)
        self.assertEqual(raw.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        highest = raw.execute("SELECT MAX(seq) FROM events").fetchone()[0]
        self.assertEqual(highest, manifest["max_event_seq"])

    def test_backup_records_a_hash_for_every_copied_file(self):
        store = self.open_store()
        store.propose_batch(batch())
        destination = self.root / "backups" / "two"
        manifest = store.backup(destination)
        self.assertTrue(manifest["files"])
        for entry in manifest["files"]:
            copied = destination / entry["path"]
            self.assertEqual(hashlib.sha256(copied.read_bytes()).hexdigest(),
                             entry["sha256"])

    def test_backup_refuses_an_existing_directory(self):
        store = self.open_store()
        store.propose_batch(batch())
        destination = self.root / "backups" / "three"
        destination.mkdir(parents=True)
        with self.assertRaises(CabinetError) as caught:
            store.backup(destination)
        self.assertEqual(caught.exception.code, "BACKUP_DESTINATION_EXISTS")

    def test_restore_refuses_to_overwrite_active_state(self):
        store = self.open_store()
        store.propose_batch(batch())
        destination = self.root / "backups" / "four"
        store.backup(destination)
        with self.assertRaises(CabinetError) as caught:
            Store.restore(destination, self.root)
        self.assertEqual(caught.exception.code, "RESTORE_DESTINATION_EXISTS")


class MigrationContract(StoreCase):
    def setUp(self):
        super().setUp()
        copy_legacy_company(self.root)
        self.before = file_state(self.root)

    def test_legacy_documents_are_imported_with_hashes(self):
        store = self.open_store(repo="demo/company")
        report = migrate_documents(store)
        self.assertEqual(sorted(report["imported"]),
                         ["company.md", "decisions.md", "money.md",
                          "proposals.md", "qa.md"])
        charter = store.get_document("company.md")
        self.assertEqual(charter["revision"], 1)
        self.assertIn("Company charter", charter["content"])
        self.assertEqual(charter["source"]["kind"], "legacy_markdown")
        self.assertEqual(
            charter["source"]["sha256"],
            hashlib.sha256((self.root / "company.md").read_bytes()).hexdigest())

    def test_original_files_are_untouched(self):
        store = self.open_store(repo="demo/company")
        migrate_documents(store)
        self.assertEqual(file_state(self.root), self.before)

    def test_rerunning_the_migration_changes_nothing(self):
        store = self.open_store(repo="demo/company")
        migrate_documents(store)
        seq = store.max_event_seq()
        report = migrate_documents(store)
        self.assertEqual(report["imported"], [])
        self.assertEqual(sorted(report["unchanged"]),
                         ["company.md", "decisions.md", "money.md",
                          "proposals.md", "qa.md"])
        self.assertEqual(store.max_event_seq(), seq)
        self.assertEqual(store.get_document("company.md")["revision"], 1)

    def test_an_edited_document_becomes_a_new_revision(self):
        store = self.open_store(repo="demo/company")
        migrate_documents(store)
        (self.root / "proposals.md").write_text("# Proposals\n\n- One new line.\n")
        report = migrate_documents(store)
        self.assertEqual(report["imported"], ["proposals.md"])
        latest = store.get_document("proposals.md")
        self.assertEqual(latest["revision"], 2)
        self.assertEqual(latest["supersedes"], 1)
        self.assertEqual(store.get_document("proposals.md", 1)["revision"], 1)

    def test_decision_numbers_are_preserved(self):
        store = self.open_store(repo="demo/company")
        migrate_documents(store)
        decisions = store.get_document("decisions.md")
        self.assertEqual(decisions["source"]["decision_ids"], ["D0007", "D0008", "D0009"])
        self.assertIn("D0009", decisions["content"])

    def test_migration_creates_no_batch_grant_action_or_assignment(self):
        store = self.open_store(repo="demo/company")
        migrate_documents(store)
        self.assertEqual(store.get_batches(), [])
        self.assertEqual(store.get_assignments(), [])
        self.assertEqual([row["kind"] for row in store.get_events(0)],
                         ["document.imported"] * 5)

    def test_a_charter_naming_another_repository_is_refused(self):
        (self.root / "company.md").write_text(
            "# Company charter\n\nRepository: other/company\n")
        store = self.open_store(repo="demo/company")
        with self.assertRaises(CabinetError) as caught:
            migrate_documents(store)
        self.assertEqual(caught.exception.code, "IDENTITY_CONFLICT")

    def test_snapshot_copies_are_kept_beside_the_database(self):
        store = self.open_store(repo="demo/company")
        report = migrate_documents(store)
        snapshot = Path(report["snapshot"])
        self.assertTrue(snapshot.is_dir())
        self.assertEqual(
            hashlib.sha256((snapshot / "company.md").read_bytes()).hexdigest(),
            hashlib.sha256((self.root / "company.md").read_bytes()).hexdigest())


class ExportContract(StoreCase):
    def test_views_are_written_atomically(self):
        copy_legacy_company(self.root)
        store = self.open_store(repo="demo/company")
        migrate_documents(store)
        store.propose_batch(batch())
        report = store.export_company()
        views = self.root / "views"
        self.assertEqual(sorted(p.name for p in views.glob("*.md")),
                         sorted(VIEW_NAMES))
        self.assertEqual(list(views.glob("*.tmp*")), [])
        context = (views / "company-context.md").read_text()
        self.assertIn("demo/company", context)
        self.assertIn("Company charter", context)
        self.assertEqual(len(report["views"]), len(VIEW_NAMES))

    def test_views_never_carry_private_runtime_internals(self):
        copy_legacy_company(self.root)
        store = self.open_store(repo="demo/company", process_alive=always_alive)
        store.acquire_lease("SESSION-PRIVATE-XYZ", 4321, "START-MARKER-PRIVATE")
        migrate_documents(store)
        store.propose_batch(batch())
        store.export_company()
        for view in (self.root / "views").glob("*.md"):
            text = view.read_text()
            self.assertNotIn("SESSION-PRIVATE-XYZ", text)
            self.assertNotIn("START-MARKER-PRIVATE", text)
            self.assertNotIn("cabinet.sqlite3", text)

    def test_rewriting_a_view_replaces_it_in_place(self):
        store = self.open_store(repo="demo/company")
        first = store.export_company()
        again = store.export_company()
        self.assertEqual(first["views"], again["views"])
        self.assertEqual(len(list((self.root / "views").glob("*"))), len(VIEW_NAMES))


if __name__ == "__main__":
    unittest.main()
