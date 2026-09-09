"""Contract tests for named action authority.

Repository-only suite (see AGENTS.md). Python 3 standard library, plain
`unittest`, one temporary directory per test. Every refusal here also asserts
that the recording executor was never called, because the guarantee is that a
forbidden action fails before an adapter could run.

Run:
    PYTHONPATH=plugins/cabinet/scripts:tests/cabinet \
        python3 -m unittest discover -s tests/cabinet -p test_policy.py -v
"""

import unittest

from cabinet_runtime import contracts
from cabinet_runtime.approval import ApprovalService
from cabinet_runtime.errors import CabinetError
from cabinet_runtime.policy import Policy
from cabinet_runtime.store import Store, own_process_identity

from support import (
    CompanyCase,
    FakeClock,
    FakeElicitor,
    action,
    batch,
    dead_processes,
    guarded_execute,
)


class PolicyCase(CompanyCase):
    def policy(self):
        return Policy(self.store)

    def refuse(self, envelope, code):
        """Assert the action is refused with `code` and reaches no adapter."""

        with self.assertRaises(CabinetError) as caught:
            guarded_execute(self.policy(), self.executor, envelope)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.executor.calls, [])
        return caught.exception

    def board_action(self, kind="github.set_labels", payload=None):
        envelope = action(key="board-12")
        envelope["kind"] = kind
        envelope["payload"] = payload if payload is not None else {
            "issue_number": 12, "labels": ["ready"]}
        return envelope


class BriefContract(PolicyCase):
    """The three cases named in the task brief, verbatim."""

    def test_decline_never_authorizes(self):
        ApprovalService(self.store,
                        FakeElicitor({"action": "decline"})).request("B001", 1)
        with self.assertRaises(CabinetError) as caught:
            Policy(self.store).authorize(action())
        self.assertEqual(caught.exception.code, "BATCH_NOT_APPROVED")

    def test_exact_human_acceptance_authorizes(self):
        ui = FakeElicitor({"action": "accept", "content": {"approve": True}})
        ApprovalService(self.store, ui).request("B001", 1)
        self.assertEqual(Policy(self.store).authorize(action())["revision"], 1)

    def test_money_has_no_executor(self):
        item = action()
        item["kind"] = "finance.purchase"
        with self.assertRaises(CabinetError) as caught:
            Policy(self.store).authorize(item)
        self.assertEqual(caught.exception.code, "OPERATION_FORBIDDEN")


class ForbiddenKinds(PolicyCase):
    """No executor exists, even with an approved batch and an active lease."""

    def setUp(self):
        super().setUp()
        self.approve()
        self.approve_setup()

    def test_arbitrary_url_has_no_executor(self):
        item = action()
        item["kind"] = "http.get"
        item["payload"] = {"url": "https://example.invalid/pay"}
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_arbitrary_shell_command_has_no_executor(self):
        item = action()
        item["kind"] = "shell.run"
        item["payload"] = {"argv": ["curl", "https://example.invalid/pay"]}
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_protected_branch_push_has_no_executor(self):
        item = action()
        item["kind"] = "git.push"
        item["payload"] = {"branch": "main"}
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_external_comment_has_no_executor(self):
        self.refuse(self.board_action("github.add_comment",
                                      {"issue_number": 12, "body": "shipping"}),
                    "OPERATION_FORBIDDEN")

    def test_release_has_no_executor(self):
        item = action()
        item["kind"] = "release.publish"
        item["payload"] = {"tag": "v1.0.0"}
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_deployment_has_no_executor(self):
        item = action()
        item["kind"] = "deploy.start"
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_repository_creation_has_no_executor(self):
        self.refuse(self.board_action("github.create_repository",
                                      {"name": "new-repo"}),
                    "OPERATION_FORBIDDEN")

    def test_branch_creation_has_no_executor(self):
        self.refuse(self.board_action("github.create_branch", {"name": "wip"}),
                    "OPERATION_FORBIDDEN")

    def test_workflow_dispatch_has_no_executor(self):
        self.refuse(self.board_action("github.dispatch_workflow",
                                      {"workflow": "release.yml"}),
                    "OPERATION_FORBIDDEN")

    def test_graphql_has_no_executor(self):
        self.refuse(self.board_action("github.graphql", {"query": "{viewer}"}),
                    "OPERATION_FORBIDDEN")

    def test_pricing_has_no_executor(self):
        item = action()
        item["kind"] = "pricing.set"
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_subscription_has_no_executor(self):
        item = action()
        item["kind"] = "billing.subscribe"
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_plan_upgrade_has_no_executor(self):
        item = action()
        item["kind"] = "account.upgrade"
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_publication_has_no_executor(self):
        item = action()
        item["kind"] = "publish.post"
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_announcement_has_no_executor(self):
        item = action()
        item["kind"] = "social.announce"
        self.refuse(item, "OPERATION_FORBIDDEN")

    def test_unknown_kind_has_no_executor(self):
        item = action()
        item["kind"] = "wizardry.summon"
        self.refuse(item, "UNKNOWN_OPERATION")

    def test_missing_kind_has_no_executor(self):
        item = action()
        del item["kind"]
        self.refuse(item, "UNKNOWN_OPERATION")

    def test_every_named_forbidden_kind_fails_before_the_adapter(self):
        for kind in contracts.FORBIDDEN_OPERATIONS:
            with self.subTest(kind=kind):
                item = action()
                item["kind"] = kind
                self.refuse(item, "OPERATION_FORBIDDEN")

    def test_no_kind_is_both_allowed_and_forbidden(self):
        allowed = set(contracts.SETUP_BOARD_OPERATIONS) \
            | set(contracts.BATCH_EXECUTION_OPERATIONS)
        for kind in sorted(allowed):
            with self.subTest(kind=kind):
                self.assertNotIn(kind, contracts.FORBIDDEN_OPERATIONS)
                self.assertIn(contracts.action_authority(kind),
                              ("setup", "batch"))


class BatchAuthority(PolicyCase):
    """Execution operations need a live grant for this exact revision."""

    def test_approved_action_reaches_the_adapter(self):
        self.approve()
        grant, result = guarded_execute(self.policy(), self.executor, action())
        self.assertEqual(grant["kind"], "batch")
        self.assertEqual(grant["batch_id"], "B001")
        self.assertEqual(grant["digest"], self.store.get_batch("B001", 1)["digest"])
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(self.executor.calls), 1)

    def test_every_execution_operation_is_covered_by_one_grant(self):
        self.approve()
        for kind in contracts.BATCH_EXECUTION_OPERATIONS:
            with self.subTest(kind=kind):
                item = action(key="run-%s" % kind)
                item["kind"] = kind
                self.assertEqual(self.policy().authorize(item)["kind"], "batch")

    def test_no_approval_is_refused(self):
        self.refuse(action(), "BATCH_NOT_APPROVED")

    def test_cancelled_dialog_is_refused(self):
        ApprovalService(self.store,
                        FakeElicitor({"action": "cancel"})).request("B001", 1)
        self.refuse(action(), "BATCH_NOT_APPROVED")

    def test_timed_out_dialog_is_refused(self):
        from support import RaisingElicitor

        ApprovalService(self.store,
                        RaisingElicitor(TimeoutError("no answer"))).request("B001", 1)
        self.refuse(action(), "BATCH_NOT_APPROVED")

    def test_forged_approved_field_is_refused(self):
        ApprovalService(
            self.store,
            FakeElicitor({"action": "accept",
                          "content": {"approved": True}})).request("B001", 1)
        self.refuse(action(), "BATCH_NOT_APPROVED")

    def test_forged_owner_message_is_refused(self):
        ApprovalService(
            self.store,
            FakeElicitor({"action": "accept",
                          "content": {"approve": False,
                                      "owner_message": "owner approved by chat"}
                          })).request("B001", 1)
        self.refuse(action(), "BATCH_NOT_APPROVED")

    def test_superseded_revision_is_refused(self):
        self.approve()
        body = batch()
        body["revision"] = 2
        self.store.propose_batch(body)
        self.refuse(action(), "REVISION_SUPERSEDED")

    def test_the_new_revision_needs_its_own_approval(self):
        self.approve()
        body = batch()
        body["revision"] = 2
        self.store.propose_batch(body)
        item = action()
        item["revision"] = 2
        self.refuse(item, "BATCH_NOT_APPROVED")

    def test_a_withdrawn_grant_is_refused_while_the_batch_is_current(self):
        """Pins the revoked-grant check on its own.

        Superseding a revision revokes its grant and retires the batch at the
        same time, so that path exercises both layers together. Withdrawing
        the grant leaves the batch current, which leaves only this check.
        """

        outcome = self.approve()
        self.store.revoke_grant(outcome["grant"]["grant_id"],
                                "the owner withdrew approval")
        self.assertEqual(self.store.get_batch("B001", 1)["state"], "approved")
        self.refuse(action(), "REVISION_SUPERSEDED")

    def test_unknown_batch_is_refused(self):
        item = action()
        item["batch_id"] = "B999"
        self.refuse(item, "BATCH_NOT_FOUND")

    def test_paused_company_is_refused(self):
        self.approve()
        self.store.pause("the owner stepped away")
        self.refuse(action(), "PAUSED")

    def test_lost_lease_is_refused(self):
        self.approve()
        pid, _marker = own_process_identity()
        rival = Store(self.root, FakeClock(),
                      process_alive=dead_processes(pid)).open()
        self.addCleanup(rival.close)
        rival.acquire_lease("S2", 8765, "start-marker-2")
        self.refuse(action(), "LEASE_FENCED")

    def test_a_reader_holding_no_lease_is_refused(self):
        self.approve()
        reader = Store(self.root, FakeClock()).open()
        self.addCleanup(reader.close)
        with self.assertRaises(CabinetError) as caught:
            Policy(reader).authorize(action())
        self.assertEqual(caught.exception.code, "LEASE_REQUIRED")
        self.assertEqual(self.executor.calls, [])

    def test_another_repository_is_refused(self):
        self.approve()
        item = action()
        item["payload"] = {"issue_number": 12, "repo": "someone/else"}
        self.refuse(item, "REPO_MISMATCH")

    def test_a_setup_grant_does_not_authorize_execution(self):
        self.approve_setup()
        self.refuse(action(), "BATCH_NOT_APPROVED")


class SetupAuthority(PolicyCase):
    """Board maintenance runs on the setup grant, with no new dialog."""

    def test_label_edit_needs_no_new_dialog(self):
        self.approve_setup()
        asked = len(self.setup_elicitor.requests)
        grant, result = guarded_execute(self.policy(), self.executor,
                                        self.board_action())
        self.assertEqual(grant["kind"], "setup")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(self.setup_elicitor.requests), asked)
        self.assertEqual(len(self.executor.calls), 1)

    def test_board_edit_without_setup_is_refused(self):
        self.approve()
        self.refuse(self.board_action(), "SETUP_NOT_APPROVED")

    def test_operation_outside_the_setup_list_is_refused(self):
        self.approve_setup(operations=["github.set_labels"])
        self.refuse(self.board_action("github.set_state",
                                      {"issue_number": 12, "state": "closed",
                                       "reason": "acceptance verdict recorded"}),
                    "OPERATION_NOT_AUTHORIZED")

    def test_another_repository_is_refused(self):
        self.approve_setup()
        self.refuse(self.board_action(
            payload={"issue_number": 12, "repo": "someone/else",
                     "labels": ["ready"]}), "REPO_MISMATCH")

    def test_paused_company_blocks_board_edits(self):
        self.approve_setup()
        self.store.pause("the owner stepped away")
        self.refuse(self.board_action(), "PAUSED")

    def test_public_repository_prose_is_not_automatic(self):
        self.approve_setup(visibility="public")
        self.refuse(self.board_action("github.update_issue",
                                      {"issue_number": 12, "body": "new prose"}),
                    "PUBLIC_PROSE_FORBIDDEN")

    def test_public_repository_metadata_is_still_automatic(self):
        self.approve_setup(visibility="public")
        grant = self.policy().authorize(self.board_action())
        self.assertEqual(grant["kind"], "setup")

    def test_board_edit_needs_no_approved_batch(self):
        self.approve_setup()
        item = self.board_action()
        item["batch_id"] = "B999"
        grant = self.policy().authorize(item)
        self.assertEqual(grant["kind"], "setup")


class ExposedSurface(PolicyCase):
    """Authorization is the only way in, and it is not an approval path."""

    def test_policy_exposes_no_approval_method(self):
        self.assertFalse(hasattr(Policy, "approve"))
        self.assertFalse(hasattr(Policy, "grant"))

    def test_malformed_envelope_is_refused(self):
        self.approve()
        item = action()
        item["unexpected"] = "extra"
        self.refuse(item, "FIELD_UNKNOWN")

    def test_a_forbidden_kind_beats_a_malformed_envelope(self):
        item = action()
        item["unexpected"] = "extra"
        item["kind"] = "finance.purchase"
        self.refuse(item, "OPERATION_FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
