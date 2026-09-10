"""The GitHub board adapter: paginated reads and verified scoped writes.

Two properties are what these tests exist to hold, and both are easy to lose:

* **A relationship is an edge between database identifiers, not numbers.** The
  number is what a person types; the identifier is what the provider stores.
  An adapter that sends one where the other belongs produces an edge on the
  wrong issue, or none at all, and the reply looks the same either way.
* **An incomplete read is not an empty one.** A failed page must arrive as a
  named error, because a board that quietly shrank is a board that authorizes
  the wrong dispatch.
"""

import json
import unittest
from unittest import mock

from cabinet_runtime import contracts, github
from cabinet_runtime.errors import CabinetError
from cabinet_runtime.github import GithubAdapter
from support import FakeGithubRun, ServiceCase, action, setup_scope


def issue_row(number, **overrides):
    """One row as the issues collection returns it, PRs included by default."""

    row = {"number": number, "id": 900000 + number,
           "node_id": "I_%d" % number, "title": "Issue %d" % number,
           "url": "https://api.github.com/repos/demo/company/issues/%d" % number,
           "html_url": "https://github.com/demo/company/issues/%d" % number,
           "state": "open", "state_reason": None, "labels": [],
           "assignees": [], "created_at": "2026-09-01T10:00:00Z",
           "updated_at": "2026-09-09T10:00:00Z",
           "sub_issues_summary": {"total": 0, "completed": 0,
                                  "percent_completed": 0},
           "issue_dependencies_summary": {"blocked_by": 0, "total_blocked_by": 0,
                                          "blocking": 0, "total_blocking": 0}}
    row.update(overrides)
    return row


class GithubCase(unittest.TestCase):
    """An adapter over a synthetic board with more than one page of issues."""

    repo = "demo/company"

    def setUp(self):
        self.fake = FakeGithubRun(self.repo)
        self.fake.collection("issues", [issue_row(n) for n in range(1, 151)])
        self.github = GithubAdapter(self.fake, self.repo,
                                    sleeper=self.fake.sleeper)

    def apply(self, operation, payload, expected_before=None):
        """Apply the way a caller must: observe the issue, then ask.

        `expected_before` is not optional on a field change, so a test that
        does not care about staleness still has to travel the path a real
        caller does. Passing it explicitly overrides this.
        """

        if expected_before is None and operation in github.EXPECTATION_OPERATIONS:
            expected_before = github.observe_expectations(
                self.github.read_issue(payload["issue_number"]), operation,
                payload)
        return self.github.apply(operation, payload,
                                 expected_before=expected_before)

    def refuse(self, operation, payload, **kwargs):
        """Apply expecting a CabinetError; return its code."""

        try:
            self.apply(operation, payload, **kwargs)
        except CabinetError as problem:
            return problem.code
        raise AssertionError("%s did not refuse" % operation)

    def refuse_raw(self, operation, payload, **kwargs):
        """Go straight to the adapter, for a refusal that must precede any read."""

        try:
            self.github.apply(operation, payload, **kwargs)
        except CabinetError as problem:
            return problem.code
        raise AssertionError("%s did not refuse" % operation)


# --- the two tests the brief names verbatim ---------------------------------

class EdgeDirectionTest(GithubCase):

    def test_blocker_uses_issue_database_id(self):
        self.fake.issue(12, {"number": 12, "id": 9012})
        self.fake.issue(14, {"number": 14, "id": 9014})
        self.apply("github.add_blocker", {"issue_number": 14,
                                                 "blocker_number": 12})
        request = self.fake.last_mutation()
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["path"],
                         "repos/demo/company/issues/14/dependencies/blocked_by")
        self.assertEqual(request["body"], {"issue_id": 9012})

    def test_partial_board_cannot_authorize_dispatch(self):
        self.fake.fail_page("issues", 2)
        board = self.github.read_board()
        self.assertFalse(board["complete"])
        self.assertEqual(board["errors"][0]["code"], "SOURCE_INCOMPLETE")


# --- reading the board ------------------------------------------------------

class ReadBoardTest(GithubCase):

    def test_every_page_is_followed(self):
        self.fake.collection("issues", [issue_row(n) for n in range(1, 551)])
        board = self.github.read_board()
        self.assertTrue(board["complete"])
        self.assertEqual(board["counts"]["open_issues"], 550)

    def test_more_than_a_hundred_branches_are_all_returned(self):
        self.fake.collection("branches",
                             [{"name": "feature/%d" % n} for n in range(1, 131)])
        board = self.github.read_board()
        self.assertEqual(board["counts"]["branches"], 130)
        self.assertEqual(len(set(board["branches"])), 130)

    def test_pull_requests_are_filtered_out_of_the_issues_collection(self):
        rows = [issue_row(n) for n in range(1, 5)]
        rows[1]["pull_request"] = {"url": "https://example.invalid/pulls/2"}
        rows[3]["pull_request"] = {"url": "https://example.invalid/pulls/4"}
        self.fake.collection("issues", rows)
        board = self.github.read_board()
        self.assertEqual([row["number"] for row in board["open_issues"]], [1, 3])

    def test_a_board_with_no_epic_label_reports_none_and_stays_complete(self):
        self.fake.collection("issues", [issue_row(n) for n in range(1, 5)])
        board = self.github.read_board()
        self.assertEqual(board["epics_index"], [])
        self.assertEqual(board["counts"]["epics"], 0)
        self.assertTrue(board["complete"])

    def test_an_epic_label_is_indexed(self):
        rows = [issue_row(1), issue_row(2, labels=[{"name": "epic"}])]
        self.fake.collection("issues", rows)
        board = self.github.read_board()
        self.assertEqual([row["number"] for row in board["epics_index"]], [2])

    def test_a_failed_page_keeps_the_pages_before_it(self):
        self.fake.fail_page("issues", 2)
        board = self.github.read_board()
        self.assertEqual(board["counts"]["open_issues"], 100)
        self.assertEqual(board["errors"][0]["collection"], "issues")
        self.assertEqual(board["errors"][0]["page"], 2)

    def test_a_missing_relationship_is_unknown_and_never_an_empty_list(self):
        rows = [issue_row(1)]
        del rows[0]["sub_issues_summary"]
        del rows[0]["issue_dependencies_summary"]
        self.fake.collection("issues", rows)
        board = self.github.read_board()
        row = board["open_issues"][0]
        self.assertEqual(row["parent"], "unknown")
        self.assertEqual(row["children"], "unknown")
        self.assertEqual(row["blocked_by"], "unknown")

    def test_a_reported_empty_relationship_is_an_empty_list(self):
        self.fake.collection("issues", [issue_row(1)])
        row = self.github.read_board()["open_issues"][0]
        self.assertEqual(row["blocked_by"], [])
        self.assertIsNone(row["parent"])

    def test_a_counted_relationship_the_list_call_cannot_name_is_unknown(self):
        rows = [issue_row(1, issue_dependencies_summary={
            "blocked_by": 1, "total_blocked_by": 2, "blocking": 0,
            "total_blocking": 0})]
        self.fake.collection("issues", rows)
        row = self.github.read_board()["open_issues"][0]
        self.assertEqual(row["blocked_by"], "unknown")
        self.assertEqual(row["blocked_by_count"], 2)


class ReadIssueTest(GithubCase):

    def test_the_database_id_is_not_the_number(self):
        self.fake.issue(12, {"id": 9012})
        read = self.github.read_issue(12)
        self.assertEqual(read["number"], 12)
        self.assertEqual(read["id"], 9012)

    def test_parent_and_blockers_are_included(self):
        self.fake.issue(11, {"id": 9011})
        self.fake.issue(12, {"id": 9012})
        self.fake.issue(14, {"id": 9014})
        self.apply("github.set_parent", {"issue_number": 14,
                                                "parent_number": 11})
        self.apply("github.add_blocker", {"issue_number": 14,
                                                 "blocker_number": 12})
        read = self.github.read_issue(14)
        self.assertEqual(read["parent"], 11)
        self.assertEqual(read["blocked_by"], [12])
        self.assertEqual(self.github.read_issue(11)["children"], [14])

    def test_a_missing_issue_is_not_found(self):
        with self.assertRaises(CabinetError) as caught:
            self.github.read_issue(99)
        self.assertEqual(caught.exception.code, "NOT_FOUND")

    def test_unauthenticated_and_forbidden_are_distinguished(self):
        for status, code in ((401, "AUTH_REQUIRED"), (403, "FORBIDDEN"),
                             (404, "NOT_FOUND")):
            with self.subTest(status=status):
                fake = _StatusRun(status)
                adapter = GithubAdapter(fake, self.repo, sleeper=fake.sleeper)
                with self.assertRaises(CabinetError) as caught:
                    adapter.read_issue(12)
                self.assertEqual(caught.exception.code, code)

    def test_a_failed_relationship_page_leaves_the_issue_incomplete(self):
        self.fake.issue(11, {"id": 9011})
        self.fake.issue(14, {"id": 9014})
        self.apply("github.set_parent", {"issue_number": 14,
                                                "parent_number": 11})
        self.fake.fail_page("sub_issues", 1)
        read = self.github.read_issue(11)
        self.assertFalse(read["complete"])
        self.assertEqual(read["children"], "unknown")
        self.assertEqual(read["errors"][0]["code"], "SOURCE_INCOMPLETE")


class ReadChangedIssuesTest(GithubCase):

    def test_the_scheduler_interface_returns_number_and_stamp(self):
        self.fake.collection("issues", [issue_row(12)])
        changed = self.github.read_changed_issues("2026-09-01T00:00:00Z")
        self.assertEqual(changed, [{"number": 12, "title": "Issue 12",
                                    "state": "open",
                                    "updated_at": "2026-09-09T10:00:00Z"}])

    def test_the_window_is_sent_as_the_since_parameter(self):
        self.github.read_changed_issues("2026-09-01T00:00:00Z")
        self.assertTrue(any("since=2026-09-01T00%3A00%3A00Z" in word
                            for word in self.fake.requests[0]["argv"]))

    def test_pull_requests_are_filtered_from_the_changed_set(self):
        rows = [issue_row(12),
                issue_row(13, pull_request={"url": "https://example.invalid"})]
        self.fake.collection("issues", rows)
        changed = self.github.read_changed_issues(None)
        self.assertEqual([row["number"] for row in changed], [12])

    def test_an_incomplete_read_is_reported_through_board_state(self):
        self.fake.fail_page("issues", 2)
        self.github.read_changed_issues(None)
        self.assertFalse(self.github.board_state()["complete"])


# --- writing ----------------------------------------------------------------

class ApplyTest(GithubCase):

    def setUp(self):
        super().setUp()
        for number in (11, 12, 13, 14):
            self.fake.issue(number, {"id": 9000 + number})

    def test_only_the_named_operations_are_reachable(self):
        self.assertEqual(tuple(GithubAdapter.OPERATIONS),
                         contracts.SETUP_BOARD_OPERATIONS)

    def test_a_comment_is_refused_before_any_call(self):
        code = self.refuse_raw("github.add_comment", {"issue_number": 14,
                                                  "body": "hello"})
        self.assertEqual(code, "OPERATION_FORBIDDEN")
        self.assertEqual(self.fake.requests, [])

    def test_an_arbitrary_endpoint_is_refused_before_any_call(self):
        code = self.refuse_raw("github.request", {"path": "repos/demo/company",
                                              "method": "DELETE"})
        self.assertEqual(code, "OPERATION_FORBIDDEN")
        self.assertEqual(self.fake.requests, [])

    def test_a_graphql_string_is_refused_before_any_call(self):
        code = self.refuse_raw("github.graphql", {"query": "{ viewer { login } }"})
        self.assertEqual(code, "OPERATION_FORBIDDEN")
        self.assertEqual(self.fake.requests, [])

    def test_another_repository_is_refused_before_any_call(self):
        code = self.refuse_raw("github.set_labels",
                           {"issue_number": 14, "labels": ["ready"],
                            "repo": "someone/else"})
        self.assertEqual(code, "REPO_MISMATCH")
        self.assertEqual(self.fake.requests, [])

    def test_the_pinned_api_version_and_accept_header_are_sent(self):
        self.github.read_issue(12)
        argv = self.fake.requests[0]["argv"]
        self.assertIn("Accept: application/vnd.github+json", argv)
        self.assertIn("X-GitHub-Api-Version: %s" % GithubAdapter.API_VERSION,
                      argv)

    def test_a_body_travels_on_standard_input_not_in_the_command_line(self):
        self.apply("github.set_state",
                          {"issue_number": 14, "state": "closed",
                           "state_reason": "not_planned",
                           "reason": "The owner deferred it"})
        argv = self.fake.mutations()[-1]["argv"]
        self.assertIn("--input", argv)
        self.assertEqual(argv[argv.index("--input") + 1], "-")
        self.assertNotIn("not_planned", " ".join(argv))

    def test_a_child_uses_the_child_database_id(self):
        self.apply("github.set_parent", {"issue_number": 14,
                                                "parent_number": 11})
        request = self.fake.last_mutation()
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["path"],
                         "repos/demo/company/issues/11/sub_issues")
        self.assertEqual(request["body"], {"sub_issue_id": 9014})

    def test_removing_a_blocker_names_the_identifier_in_the_path(self):
        self.apply("github.add_blocker", {"issue_number": 14,
                                                 "blocker_number": 12})
        self.apply("github.remove_blocker", {"issue_number": 14,
                                                    "blocker_number": 12})
        request = self.fake.last_mutation()
        self.assertEqual(request["method"], "DELETE")
        self.assertEqual(
            request["path"],
            "repos/demo/company/issues/14/dependencies/blocked_by/9012")

    def test_every_changed_field_is_read_back_before_verified(self):
        result = self.apply("github.set_labels",
                                   {"issue_number": 14, "labels": ["ready"]})
        self.assertEqual(result["outcome"], "verified")
        self.assertEqual(result["before"]["labels"], [])
        self.assertEqual(result["after"]["labels"], ["ready"])
        self.assertEqual(result["changed"], ["labels"])

    def test_a_readback_that_disagrees_is_uncertain_not_verified(self):
        self.fake.issue(15, {"id": 9015})
        self.fake.readback_refuses = True
        result = self.apply("github.set_labels",
                                   {"issue_number": 15, "labels": ["ready"]})
        self.assertEqual(result["outcome"], "uncertain")


class CycleTest(ApplyTest):

    def test_an_issue_cannot_be_its_own_parent(self):
        code = self.refuse("github.set_parent", {"issue_number": 14,
                                                 "parent_number": 14})
        self.assertEqual(code, "RELATIONSHIP_CYCLE")
        self.assertEqual(self.fake.mutations(), [])

    def test_a_parent_cycle_is_refused_before_the_write(self):
        self.apply("github.set_parent", {"issue_number": 12,
                                                "parent_number": 11})
        code = self.refuse("github.set_parent", {"issue_number": 11,
                                                 "parent_number": 12})
        self.assertEqual(code, "RELATIONSHIP_CYCLE")

    def test_a_dependency_cycle_is_refused_before_the_write(self):
        self.apply("github.add_blocker", {"issue_number": 14,
                                                 "blocker_number": 12})
        code = self.refuse("github.add_blocker", {"issue_number": 12,
                                                  "blocker_number": 14})
        self.assertEqual(code, "RELATIONSHIP_CYCLE")

    def test_a_deep_dependency_cycle_is_refused(self):
        self.apply("github.add_blocker", {"issue_number": 14,
                                                 "blocker_number": 13})
        self.apply("github.add_blocker", {"issue_number": 13,
                                                 "blocker_number": 12})
        code = self.refuse("github.add_blocker", {"issue_number": 12,
                                                  "blocker_number": 14})
        self.assertEqual(code, "RELATIONSHIP_CYCLE")

    def test_a_short_cycle_behind_a_wide_graph_is_still_refused(self):
        """Sixty-one blockers on one issue, and a two-hop cycle behind them.

        The walk explores a transitive closure, so the number of issues it
        touches has nothing to do with how short the cycle is. A budget spent
        per node used to let this through and write the edge.
        """

        self.seed(5)
        for number in range(10, 71):
            self.seed(number)
            self.apply("github.add_blocker",
                              {"issue_number": 5, "blocker_number": number})
        before = len(self.fake.mutations())
        code = self.refuse("github.add_blocker", {"issue_number": 10,
                                                  "blocker_number": 5})
        self.assertEqual(code, "RELATIONSHIP_CYCLE")
        self.assertEqual(len(self.fake.mutations()), before)

    def test_a_sixty_eight_hop_chain_is_still_refused(self):
        chain = list(range(100, 168))
        for number in chain:
            self.seed(number)
        for upper, lower in zip(chain, chain[1:]):
            self.apply("github.add_blocker",
                              {"issue_number": upper, "blocker_number": lower})
        before = len(self.fake.mutations())
        code = self.refuse("github.add_blocker",
                           {"issue_number": chain[-1],
                            "blocker_number": chain[0]})
        self.assertEqual(code, "RELATIONSHIP_CYCLE")
        self.assertEqual(len(self.fake.mutations()), before)

    def test_a_walk_that_runs_out_of_budget_refuses_rather_than_writes(self):
        """The adapter cannot prove there is no cycle, so it writes nothing.

        This is the same answer an unreadable edge gets, and for the same
        reason: not knowing is not the same as knowing there is none.
        """

        for number in range(200, 210):
            self.seed(number)
        for number in range(201, 210):
            self.apply("github.add_blocker",
                              {"issue_number": 200, "blocker_number": number})
        before = len(self.fake.mutations())
        with mock.patch.object(github, "MAX_RELATION_NODES", 3):
            code = self.refuse("github.add_blocker", {"issue_number": 14,
                                                      "blocker_number": 200})
        self.assertEqual(code, "SOURCE_INCOMPLETE")
        self.assertEqual(len(self.fake.mutations()), before)

    def test_a_hierarchy_cycle_past_the_budget_refuses(self):
        self.seed(300)
        self.seed(301)
        self.apply("github.set_parent", {"issue_number": 301,
                                                "parent_number": 300})
        with mock.patch.object(github, "MAX_RELATION_NODES", 1):
            code = self.refuse("github.set_parent", {"issue_number": 14,
                                                     "parent_number": 301})
        self.assertEqual(code, "SOURCE_INCOMPLETE")

    def seed(self, number):
        return self.fake.issue(number, {"id": 90000 + number})


class UnreadableEdgeTest(ApplyTest):
    """An edge write needs to know the edges that are already there.

    Writing a parent onto an issue whose current parent could not be read
    leaves the old parent in place and reports success, which is the worst of
    the three possible outcomes.
    """

    def test_a_parent_is_not_written_over_an_unreadable_relationship(self):
        self.fake.hide_relationships.add(14)
        code = self.refuse("github.set_parent", {"issue_number": 14,
                                                 "parent_number": 12})
        self.assertEqual(code, "SOURCE_INCOMPLETE")
        self.assertEqual(self.fake.mutations(), [])

    def test_a_blocker_is_not_written_over_an_unreadable_relationship(self):
        self.apply("github.add_blocker", {"issue_number": 14,
                                                 "blocker_number": 12})
        before = len(self.fake.mutations())
        self.fake.fail_page("blocked_by", 1)
        code = self.refuse("github.add_blocker", {"issue_number": 14,
                                                  "blocker_number": 13})
        self.assertEqual(code, "SOURCE_INCOMPLETE")
        self.assertEqual(len(self.fake.mutations()), before)

    def test_a_cycle_check_that_cannot_walk_the_chain_refuses(self):
        self.fake.hide_relationships.add(11)
        code = self.refuse("github.set_parent", {"issue_number": 12,
                                                 "parent_number": 11})
        self.assertEqual(code, "SOURCE_INCOMPLETE")
        self.assertEqual(self.fake.mutations(), [])


class ReparentTest(ApplyTest):

    def test_reparenting_removes_the_old_edge_and_adds_the_new_one(self):
        self.apply("github.set_parent", {"issue_number": 14,
                                                "parent_number": 11})
        result = self.apply("github.set_parent", {"issue_number": 14,
                                                         "parent_number": 12})
        steps = [step["step"] for step in result["substeps"]]
        self.assertEqual(steps, ["remove_parent", "add_parent"])
        self.assertEqual(result["after"]["parent"], 12)
        self.assertEqual(self.github.read_issue(11)["children"], [])

    def test_each_substep_records_its_own_method_and_path(self):
        self.apply("github.set_parent", {"issue_number": 14,
                                                "parent_number": 11})
        result = self.apply("github.set_parent", {"issue_number": 14,
                                                         "parent_number": 12})
        self.assertEqual(result["substeps"][0]["method"], "DELETE")
        self.assertEqual(result["substeps"][0]["path"],
                         "repos/demo/company/issues/11/sub_issue")
        self.assertEqual(result["substeps"][1]["method"], "POST")

    def test_no_checkbox_is_written_into_any_body(self):
        self.apply("github.set_parent", {"issue_number": 14,
                                                "parent_number": 11})
        self.assertEqual(self.github.read_issue(14)["body"], "")
        self.assertEqual(self.github.read_issue(11)["body"], "")


class BodyTest(ApplyTest):

    def setUp(self):
        super().setUp()
        self.fake.issue(20, {"id": 9020,
                             "body": "Human prose.\n\n%s\nold\n%s\n\nMore prose."
                                     % (GithubAdapter.MANAGED_BEGIN,
                                        GithubAdapter.MANAGED_END)})

    def test_a_managed_block_edit_preserves_the_text_around_it(self):
        self.apply("github.update_issue",
                          {"issue_number": 20, "body_block": "new"})
        body = self.github.read_issue(20)["body"]
        self.assertIn("Human prose.", body)
        self.assertIn("More prose.", body)
        self.assertIn("new", body)
        self.assertNotIn("old", body)

    def test_a_whole_body_change_needs_an_explicit_review_flag(self):
        code = self.refuse("github.update_issue",
                           {"issue_number": 20, "body": "everything replaced"})
        self.assertEqual(code, "WHOLE_BODY_UNREVIEWED")
        self.assertEqual(self.fake.mutations(), [])

    def test_a_reviewed_whole_body_change_is_applied(self):
        self.apply("github.update_issue",
                          {"issue_number": 20, "body": "everything replaced",
                           "whole_body_reviewed": True})
        self.assertEqual(self.github.read_issue(20)["body"],
                         "everything replaced")

    def test_a_managed_block_is_appended_when_the_body_has_none(self):
        self.apply("github.update_issue",
                          {"issue_number": 14, "body_block": "first"})
        body = self.github.read_issue(14)["body"]
        self.assertIn(GithubAdapter.MANAGED_BEGIN, body)
        self.assertIn("first", body)


class ConcurrentEditTest(ApplyTest):

    def test_a_body_changed_under_us_is_source_changed(self):
        code = self.refuse(
            "github.update_issue", {"issue_number": 14, "title": "New title"},
            expected_before={"issue_updated_at": "2026-09-08T09:00:00Z",
                             "title": "Issue 14"})
        self.assertEqual(code, "SOURCE_CHANGED")
        self.assertEqual(self.fake.mutations(), [])

    def test_a_matching_expectation_proceeds(self):
        result = self.apply(
            "github.update_issue", {"issue_number": 14, "title": "New title"},
            expected_before={"issue_updated_at": "2026-09-09T10:00:00Z",
                             "title": "Issue 14"})
        self.assertEqual(result["outcome"], "verified")

    def test_a_changed_field_is_reported_with_both_values(self):
        try:
            self.apply(
                "github.set_labels", {"issue_number": 14, "labels": ["ready"]},
                expected_before={"issue_updated_at": "2026-09-09T10:00:00Z",
                                 "labels": ["triage"]})
        except CabinetError as problem:
            self.assertEqual(problem.code, "SOURCE_CHANGED")
            self.assertIn("triage", problem.message)
            self.assertIn("labels", problem.message)
        else:
            raise AssertionError("a stale expectation was not refused")

    def test_a_stale_body_is_never_retried_blindly(self):
        self.refuse(
            "github.update_issue", {"issue_number": 14, "body_block": "x"},
            expected_before={"issue_updated_at": "2026-09-08T09:00:00Z"})
        self.assertEqual(self.fake.mutations(), [])


class RequiredExpectationTest(ApplyTest):
    """Conflict-aware writing is enforced, not offered.

    An action carrying an empty `expected_before` used to get no comparison at
    all: the re-read happened and had nothing to disagree with, so a whole-body
    replacement could overwrite somebody's concurrent edit and return
    `verified`.
    """

    def test_a_field_change_with_no_expectation_is_refused_before_any_call(self):
        code = self.refuse_raw("github.set_labels",
                               {"issue_number": 14, "labels": ["ready"]})
        self.assertEqual(code, "EXPECTATION_REQUIRED")
        self.assertEqual(self.fake.requests, [])

    def test_the_refusal_names_the_missing_claims(self):
        try:
            self.github.apply("github.set_state",
                              {"issue_number": 14, "state": "closed",
                               "state_reason": "completed", "reason": "done"},
                              expected_before={"issue_updated_at": "x"})
        except CabinetError as problem:
            self.assertEqual(problem.code, "EXPECTATION_REQUIRED")
            self.assertIn("state", problem.message)
            self.assertIn("state_reason", problem.message)
        else:
            raise AssertionError("a bare expectation was not refused")

    def test_a_whole_body_replacement_must_name_the_body_it_replaces(self):
        self.fake.issue(20, {"id": 9020, "body": "Human prose."})
        code = self.refuse_raw(
            "github.update_issue",
            {"issue_number": 20, "body": "replaced",
             "whole_body_reviewed": True},
            expected_before={"issue_updated_at": "2026-09-09T10:00:00Z"})
        self.assertEqual(code, "EXPECTATION_REQUIRED")

    def test_a_whole_body_replacement_over_a_concurrent_edit_is_refused(self):
        self.fake.issue(20, {"id": 9020, "body": "Human prose."})
        code = self.refuse_raw(
            "github.update_issue",
            {"issue_number": 20, "body": "replaced",
             "whole_body_reviewed": True},
            expected_before={"issue_updated_at": "2026-09-09T10:00:00Z",
                             "body": "what it said when I read it"})
        self.assertEqual(code, "SOURCE_CHANGED")
        self.assertEqual(self.fake.mutations(), [])

    def test_a_managed_block_edit_needs_the_timestamp_but_not_the_whole_body(self):
        self.assertEqual(
            github.required_expectations("github.update_issue",
                                         {"issue_number": 20,
                                          "body_block": "x"}),
            ("issue_updated_at",))

    def test_both_spellings_of_the_timestamp_are_accepted(self):
        result = self.apply(
            "github.set_labels", {"issue_number": 14, "labels": ["ready"]},
            expected_before={"updated_at": "2026-09-09T10:00:00Z",
                             "labels": []})
        self.assertEqual(result["outcome"], "verified")

    def test_creating_an_issue_needs_no_expectation(self):
        self.assertEqual(
            github.required_expectations("github.create_issue",
                                         {"title": "New"}), ())

    def test_observe_expectations_produces_exactly_what_is_required(self):
        payload = {"issue_number": 14, "labels": ["ready"]}
        observed = github.observe_expectations(
            self.github.read_issue(14), "github.set_labels", payload)
        self.assertEqual(set(observed),
                         set(github.required_expectations("github.set_labels",
                                                          payload)))
        self.assertEqual(observed["labels"], [])


class AssigneeTest(ApplyTest):

    def test_an_unassignable_account_is_refused_before_the_write(self):
        code = self.refuse("github.set_assignees",
                           {"issue_number": 14, "assignees": ["cabinet-qa"]})
        self.assertEqual(code, "ASSIGNEE_UNKNOWN")
        self.assertEqual(self.fake.mutations(), [])

    def test_a_real_account_is_assigned(self):
        self.fake.assignable.add("amitbaz")
        result = self.apply("github.set_assignees",
                                   {"issue_number": 14,
                                    "assignees": ["amitbaz"]})
        self.assertEqual(result["after"]["assignees"], ["amitbaz"])

    def test_clearing_assignees_needs_no_account_check(self):
        result = self.apply("github.set_assignees",
                                   {"issue_number": 14, "assignees": []})
        self.assertEqual(result["after"]["assignees"], [])


class StateTest(ApplyTest):

    def test_a_state_change_records_its_business_reason_without_commenting(self):
        result = self.apply(
            "github.set_state", {"issue_number": 14, "state": "closed",
                                 "state_reason": "completed",
                                 "reason": "AC1 passed at the integrated SHA"})
        self.assertEqual(result["evidence"]["reason"],
                         "AC1 passed at the integrated SHA")
        self.assertEqual(self.fake.last_mutation()["body"],
                         {"state": "closed", "state_reason": "completed"})
        self.assertNotIn("comments", self.fake.paths())

    def test_a_state_reason_outside_the_enumeration_is_refused(self):
        code = self.refuse("github.set_state",
                           {"issue_number": 14, "state": "closed",
                            "state_reason": "duplicate", "reason": "x"})
        self.assertEqual(code, "FIELD_INVALID")

    def test_a_state_change_with_no_recorded_reason_is_refused(self):
        code = self.refuse("github.set_state",
                           {"issue_number": 14, "state": "closed",
                            "state_reason": "completed", "reason": "  "})
        self.assertEqual(code, "FIELD_INVALID")


class RateLimitTest(ApplyTest):

    def test_a_rate_limit_backs_off_on_the_provider_guidance(self):
        self.fake.rate_limit(times=1, retry_after="7")
        self.github.read_issue(14)
        self.assertEqual(self.fake.sleeps, [7.0])

    def test_backoff_never_spins(self):
        self.fake.rate_limit(times=99)
        with self.assertRaises(CabinetError) as caught:
            self.github.read_issue(14)
        self.assertEqual(caught.exception.code, "RATE_LIMITED")
        self.assertLessEqual(len(self.fake.requests),
                             GithubAdapter.RATE_LIMIT_ATTEMPTS)
        self.assertTrue(all(delay > 0 for delay in self.fake.sleeps))

    def test_a_rate_limited_write_is_not_repeated_inside_the_backoff(self):
        self.fake.rate_limit(times=99)
        try:
            self.apply("github.set_labels",
                              {"issue_number": 14, "labels": ["ready"]})
        except CabinetError:
            pass
        self.assertLessEqual(len(self.fake.mutations()),
                             GithubAdapter.RATE_LIMIT_ATTEMPTS)


# --- idempotent create and reconciliation -----------------------------------

class CreateTest(GithubCase):

    def payload(self, key="B001:r1:create-invite"):
        return {"title": "Invite entry", "body": "Body prose.",
                "labels": ["ready"], "assignees": [],
                "idempotency_key": key}

    def test_a_create_carries_an_operation_marker_in_the_body(self):
        self.apply("github.create_issue", self.payload())
        body = self.fake.last_mutation()["body"]["body"]
        self.assertIn("cabinet:action", body)
        self.assertIn("B001:r1:create-invite", body)
        self.assertIn("Body prose.", body)

    def test_a_created_issue_returns_its_external_reference(self):
        result = self.apply("github.create_issue", self.payload())
        self.assertEqual(result["external_ref"]["repo"], "demo/company")
        self.assertIsNotNone(result["external_ref"]["issue_number"])
        self.assertIsNotNone(result["external_ref"]["issue_id"])

    def test_a_timeout_after_a_successful_create_is_uncertain(self):
        self.fake.timeout_after_write("repos/demo/company/issues")
        result = self.apply("github.create_issue", self.payload())
        self.assertEqual(result["outcome"], "uncertain")

    def test_reconciling_that_timeout_adopts_the_one_real_issue(self):
        self.fake.timeout_after_write("repos/demo/company/issues")
        self.apply("github.create_issue", self.payload())
        created = max(self.fake.issues)
        self.fake.collection("issues", [issue_row(
            created, body=self.fake.issues[created]["body"])])
        outcome = self.github.reconcile_action(
            action_envelope("github.create_issue", self.payload()))
        self.assertEqual(outcome["matches"], 1)
        self.assertEqual(outcome["outcome"], "adopted")
        self.assertEqual(outcome["external_ref"]["issue_number"], created)

    def test_two_matching_markers_are_uncertain_and_never_adopted(self):
        self.fake.timeout_after_write("repos/demo/company/issues")
        self.apply("github.create_issue", self.payload())
        self.apply("github.create_issue", self.payload())
        rows = [issue_row(number, body=record["body"])
                for number, record in sorted(self.fake.issues.items())]
        self.fake.collection("issues", rows)
        outcome = self.github.reconcile_action(
            action_envelope("github.create_issue", self.payload()))
        self.assertEqual(outcome["matches"], 2)
        self.assertEqual(outcome["outcome"], "uncertain")
        self.assertIsNone(outcome["external_ref"])

    def test_no_match_asks_for_a_bounded_delay_before_a_retry(self):
        self.fake.collection("issues", [])
        outcome = self.github.reconcile_action(
            action_envelope("github.create_issue", self.payload()))
        self.assertEqual(outcome["matches"], 0)
        self.assertEqual(outcome["outcome"], "retry_after_delay")
        self.assertGreater(outcome["retry_after_seconds"], 0)

    def test_reconciling_an_edge_compares_the_live_state(self):
        self.fake.issue(12, {"id": 9012})
        self.fake.issue(14, {"id": 9014})
        self.apply("github.add_blocker", {"issue_number": 14,
                                                 "blocker_number": 12})
        outcome = self.github.reconcile_action(action_envelope(
            "github.add_blocker", {"issue_number": 14, "blocker_number": 12}))
        self.assertEqual(outcome["outcome"], "already_applied")

    def test_reconciling_an_unapplied_edge_says_it_can_be_retried(self):
        self.fake.issue(12, {"id": 9012})
        self.fake.issue(14, {"id": 9014})
        outcome = self.github.reconcile_action(action_envelope(
            "github.add_blocker", {"issue_number": 14, "blocker_number": 12}))
        self.assertEqual(outcome["outcome"], "not_applied")

    def test_no_comment_is_ever_used_as_transport(self):
        self.fake.timeout_after_write("repos/demo/company/issues")
        self.apply("github.create_issue", self.payload())
        self.fake.collection("issues", [])
        self.github.reconcile_action(
            action_envelope("github.create_issue", self.payload()))
        self.assertFalse([path for path in self.fake.paths()
                          if path.endswith("/comments")])


def action_envelope(kind, payload, key="B001:r1:create-invite"):
    return {"action_id": "A001", "idempotency_key": key, "kind": kind,
            "batch_id": "B001", "revision": 1, "expected_before": {},
            "payload": payload}


class TransportTest(unittest.TestCase):
    """The two defects a live read found, held down by tests.

    Both were invisible against a fake that produced tidy payloads, and both
    turned a real response into an empty one — the exact failure the board
    completeness rule exists to prevent.
    """

    def test_a_body_that_is_not_readable_json_is_an_error_not_an_empty_page(self):
        truncated = {"returncode": 0, "timed_out": False, "stderr": "",
                     "stdout": "HTTP/2.0 200 OK\r\n\r\n[{\"number\": 1, \"ti"}
        adapter = GithubAdapter(lambda argv, input_text=None: truncated,
                                "demo/company", sleeper=lambda _: None)
        with self.assertRaises(CabinetError) as caught:
            adapter.read_issue(1)
        self.assertEqual(caught.exception.code, "PROVIDER_ERROR")

    def test_the_provider_run_does_not_rewrite_its_own_json(self):
        from cabinet_runtime import processes

        body = '{"license":{"key":"mit"},"secret_token":"x"}'
        result = processes.run_argv(
            ["echo"], "/", {}, 5, runner=_echo(body),
            redact_output=False)
        self.assertEqual(json.loads(result["stdout"])["license"]["key"], "mit")

    def test_redaction_stays_on_by_default_for_every_other_command(self):
        from cabinet_runtime import processes

        result = processes.run_argv(["echo"], "/", {}, 5,
                                    runner=_echo("api_key=abcdef123456"))
        self.assertIn("[redacted]", result["stdout"])
        self.assertNotIn("abcdef123456", result["stdout"])

    def test_a_provider_message_is_redacted_before_it_is_surfaced(self):
        message = json.dumps({"message": "bad credential ghp_%s" % ("a" * 36)})
        reply = {"returncode": 1, "timed_out": False, "stderr": "",
                 "stdout": "HTTP/2.0 401 Unauthorized\r\n\r\n" + message}
        adapter = GithubAdapter(lambda argv, input_text=None: reply,
                                "demo/company", sleeper=lambda _: None)
        with self.assertRaises(CabinetError) as caught:
            adapter.read_issue(1)
        self.assertEqual(caught.exception.code, "AUTH_REQUIRED")
        self.assertNotIn("ghp_", caught.exception.message)


class EvidenceRedactionTest(ApplyTest):
    """A token pasted into a ticket body must not travel in an evidence record.

    The record has to stay readable as JSON while it happens, which is why
    this uses the value-only redactor rather than the one that also rewrites
    `name: value` — that one is what corrupted a licence key into invalid
    syntax against the live API.
    """

    TOKEN = "ghp_" + "a" * 36

    def test_a_token_in_a_body_is_masked_in_the_evidence(self):
        self.fake.issue(20, {"id": 9020,
                             "body": "Deploy with %s please." % self.TOKEN})
        result = self.apply("github.update_issue",
                            {"issue_number": 20, "title": "New title"})
        record = json.dumps(result["before"]) + json.dumps(result["after"])
        self.assertNotIn(self.TOKEN, record)

    def test_the_evidence_record_is_still_valid_json(self):
        self.fake.issue(20, {"id": 9020,
                             "body": "A licence {\"key\":\"mit\"} and %s."
                                     % self.TOKEN})
        result = self.apply(
            "github.update_issue",
            {"issue_number": 20, "body": "replaced", "whole_body_reviewed": True},
            expected_before={
                "issue_updated_at": "2026-09-09T10:00:00Z",
                "body": "A licence {\"key\":\"mit\"} and %s." % self.TOKEN})
        record = json.loads(json.dumps(result))
        self.assertNotIn(self.TOKEN, json.dumps(record))
        self.assertIn('"key":"mit"', record["before"]["body"])

    def test_a_state_change_reason_is_redacted_too(self):
        result = self.apply(
            "github.set_state",
            {"issue_number": 14, "state": "closed",
             "state_reason": "completed",
             "reason": "verified with %s" % self.TOKEN})
        self.assertNotIn(self.TOKEN, result["evidence"]["reason"])
        self.assertIn("[redacted]", result["evidence"]["reason"])

    def test_board_content_itself_is_left_alone_by_design(self):
        """A role has to read the prose, so the board file keeps it verbatim."""

        self.fake.collection("issues", [issue_row(1, title="A {\"key\":\"mit\"} title")])
        board = self.github.read_board()
        self.assertEqual(board["open_issues"][0]["title"],
                         'A {"key":"mit"} title')


class ProviderBoundTest(unittest.TestCase):
    """The output bound has to be larger than a page the provider really sends.

    One page of a hundred pull requests measured 1,047,842 bytes against the
    subprocess adapter's default of 1,048,576. Reverting the raised bound used
    to break no test.
    """

    def test_the_provider_bound_is_far_above_one_observed_page(self):
        from cabinet_runtime import processes

        self.assertGreater(github.PROVIDER_OUTPUT_LIMIT,
                           8 * processes.OUTPUT_LIMIT)

    def test_gh_run_asks_for_that_bound_and_leaves_stdout_unrewritten(self):
        from cabinet_runtime import processes

        seen = {}

        def spy(argv, cwd, env, timeout, **kwargs):
            seen.update(kwargs)
            return {"returncode": 0, "stdout": "", "stderr": "",
                    "timed_out": False, "classification": "completed"}

        original = processes.run_argv
        processes.run_argv = spy
        try:
            github.gh_run(environ={"PATH": "/usr/bin"})(["gh", "api", "x"])
        finally:
            processes.run_argv = original
        self.assertEqual(seen["output_limit"], github.PROVIDER_OUTPUT_LIMIT)
        self.assertFalse(seen["redact_output"])

    def test_a_page_at_the_default_bound_would_have_been_truncated(self):
        from cabinet_runtime import processes

        page = "x" * (processes.OUTPUT_LIMIT + 1)
        self.assertIn("truncated", processes.bound(page, processes.OUTPUT_LIMIT))
        self.assertEqual(processes.bound(page, github.PROVIDER_OUTPUT_LIMIT),
                         page)


def _echo(text):
    """A `subprocess.run` stand-in that returns fixed output."""

    class Completed:
        returncode = 0
        stdout = text
        stderr = ""

    return lambda *args, **kwargs: Completed()


class _StatusRun:
    """A run callable that answers every request with one HTTP status."""

    def __init__(self, status):
        self.status = status
        self.sleeps = []

    def sleeper(self, seconds):
        self.sleeps.append(seconds)

    def __call__(self, argv, input_text=None):
        from support import _response

        return _response(self.status, {"message": "synthetic"})


# --- the service wiring -----------------------------------------------------

class BoardActionCase(ServiceCase):
    """A company whose board adapter is the real one over a fake provider."""

    register_addresses = True

    def setUp(self):
        super().setUp()
        self.fake = FakeGithubRun(self.repo)
        for number in (11, 12, 13, 14):
            self.fake.issue(number, {"id": 9000 + number})
        self.fake.collection("issues", [issue_row(n) for n in (11, 12, 13, 14)])
        self.github = GithubAdapter(self.fake, self.repo,
                                    sleeper=self.fake.sleeper)
        self.service.github = self.github
        self.service.board_reader = self.github

    def prepare(self, kind, payload, key="k1", expected_before=None):
        if expected_before is None and kind in github.EXPECTATION_OPERATIONS:
            expected_before = github.observe_expectations(
                self.github.read_issue(payload["issue_number"]), kind, payload)
        envelope = action()
        envelope.update(kind=kind, payload=payload, idempotency_key=key,
                        expected_before=expected_before or {})
        return self.call("prepare_action", {"envelope": envelope})

    def execute(self, kind, payload, **kwargs):
        prepared = self.prepare(kind, payload, **kwargs)
        return self.call("execute_action", {"action_id": prepared["action_id"]})


class ExecuteBoardActionTest(BoardActionCase):

    def setUp(self):
        super().setUp()
        self.approve_setup_through_fake_ui()

    def test_an_authorized_edge_runs_and_is_recorded_verified(self):
        result = self.execute("github.add_blocker",
                              {"issue_number": 14, "blocker_number": 12})
        self.assertEqual(result["state"], "verified")
        self.assertEqual(result["external_ref"]["issue_number"], 14)
        self.assertEqual(self.github.read_issue(14)["blocked_by"], [12])

    def test_the_evidence_carries_the_before_and_after_readback(self):
        result = self.execute("github.set_labels",
                              {"issue_number": 14, "labels": ["ready"]})
        self.assertEqual(result["evidence"]["before"]["labels"], [])
        self.assertEqual(result["evidence"]["after"]["labels"], ["ready"])

    def test_a_forbidden_kind_never_reaches_the_adapter(self):
        quiet = len(self.fake.requests)
        code = self.refuse_execute("github.add_comment",
                                   {"issue_number": 14, "body": "hi"})
        self.assertEqual(code, "OPERATION_FORBIDDEN")
        self.assertEqual(len(self.fake.requests), quiet)

    def test_an_unlisted_operation_never_reaches_the_adapter(self):
        self.store.revoke_grant(
            self.store.active_setup_grant(self.repo)["grant_id"], "narrowing")
        self.elicitor.response = {"action": "accept",
                                  "content": {"approve": True}}
        self.call("setup", {"scope": setup_scope(
            repo=self.repo, operations=["github.set_labels"])})
        quiet = len(self.fake.requests)
        code = self.refuse_execute("github.add_blocker",
                                   {"issue_number": 14, "blocker_number": 12})
        self.assertEqual(code, "OPERATION_NOT_AUTHORIZED")
        self.assertEqual(len(self.fake.requests), quiet)

    def test_a_stale_expectation_blocks_the_action_rather_than_failing_it(self):
        prepared = self.prepare(
            "github.set_labels", {"issue_number": 14, "labels": ["ready"]},
            expected_before={"issue_updated_at": "2026-09-08T00:00:00Z",
                             "labels": []})
        code = self.refuse("execute_action",
                           {"action_id": prepared["action_id"]})
        self.assertEqual(code, "SOURCE_CHANGED")
        self.assertEqual(self.store.get_action("A001")["state"], "blocked")
        self.assertEqual(self.fake.mutations(), [])

    def test_a_create_carries_the_actions_own_idempotency_key(self):
        result = self.execute("github.create_issue",
                              {"title": "Invite entry", "body": "Prose."},
                              key="B001:r1:create-invite")
        self.assertEqual(result["state"], "verified")
        created = self.github.read_issue(
            result["external_ref"]["issue_number"])
        self.assertIn("B001:r1:create-invite", created["body"])
        self.assertIn("Prose.", created["body"])

    def test_no_write_transaction_is_held_across_the_network_call(self):
        seen = []
        original = self.fake.__call__

        def watching(argv, input_text=None):
            seen.append(self.store.in_transaction())
            return original(argv, input_text)

        self.service.github = GithubAdapter(watching, self.repo,
                                            sleeper=self.fake.sleeper)
        self.execute("github.set_labels",
                     {"issue_number": 14, "labels": ["ready"]})
        self.assertTrue(seen)
        self.assertFalse(any(seen))

    def refuse_execute(self, kind, payload, **kwargs):
        prepared = self.prepare(kind, payload, **kwargs)
        return self.refuse("execute_action",
                           {"action_id": prepared["action_id"]})


class StateGateTest(BoardActionCase):

    def setUp(self):
        super().setUp()
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()

    def test_closing_as_completed_without_a_verdict_is_refused(self):
        code = self.refuse_execute(
            "github.set_state", {"issue_number": 12, "state": "closed",
                                 "state_reason": "completed",
                                 "reason": "Delivery says it is done"})
        self.assertEqual(code, "ACCEPTANCE_REQUIRED")
        self.assertEqual(self.fake.mutations(), [])

    def test_closing_as_completed_after_a_passing_verdict_runs(self):
        self.seed_passing_verdict()
        result = self.execute(
            "github.set_state", {"issue_number": 12, "state": "closed",
                                 "state_reason": "completed",
                                 "reason": "AC1 passed at the integrated SHA"})
        self.assertEqual(result["state"], "verified")

    def test_a_failed_verdict_does_not_open_the_gate(self):
        self.seed_passing_verdict(outcome="fail")
        code = self.refuse_execute(
            "github.set_state", {"issue_number": 12, "state": "closed",
                                 "state_reason": "completed",
                                 "reason": "Delivery says it is done"})
        self.assertEqual(code, "ACCEPTANCE_REQUIRED")

    def test_not_planned_on_an_approved_issue_needs_an_owner_decision(self):
        code = self.refuse_execute(
            "github.set_state", {"issue_number": 12, "state": "closed",
                                 "state_reason": "not_planned",
                                 "reason": "We changed our minds"})
        self.assertEqual(code, "OWNER_DECISION_REQUIRED")
        self.assertEqual(self.fake.mutations(), [])

    def test_not_planned_runs_once_the_owner_decided(self):
        self.store.record_owner_decision(
            "issue-12", "Drop issue 12 from B001?",
            {"action": "accept", "content": {"approve": True}})
        result = self.execute(
            "github.set_state", {"issue_number": 12, "state": "closed",
                                 "state_reason": "not_planned",
                                 "reason": "The owner dropped it"})
        self.assertEqual(result["state"], "verified")

    def test_not_planned_on_an_issue_outside_the_batch_is_ordinary_grooming(self):
        result = self.execute(
            "github.set_state", {"issue_number": 13, "state": "closed",
                                 "state_reason": "not_planned",
                                 "reason": "Superseded by issue 14"})
        self.assertEqual(result["state"], "verified")

    def test_closing_a_prerequisite_releases_no_assignment(self):
        self.seed_passing_verdict()
        assignment = self.store.reserve_assignment(
            "W002", "B001", 1, "implementer", "issue:14", issue_number=14)
        self.execute(
            "github.set_state", {"issue_number": 12, "state": "closed",
                                 "state_reason": "completed",
                                 "reason": "AC1 passed at the integrated SHA"})
        after = self.store.get_assignment(assignment["assignment_id"])
        self.assertEqual(after["state"], "reserved")
        self.assertEqual(self.store.verdicts_for(after["assignment_id"]), [])

    def test_a_pass_at_an_older_head_does_not_open_the_gate(self):
        """The work moved after QA looked at it."""

        self.seed_passing_verdict(verdict_sha="c" * 40)
        code = self.refuse_execute(
            "github.set_state", {"issue_number": 12, "state": "closed",
                                 "state_reason": "completed",
                                 "reason": "QA passed it once"})
        self.assertEqual(code, "ACCEPTANCE_REQUIRED")
        self.assertEqual(self.fake.mutations(), [])

    def test_an_assignment_that_reported_nothing_cannot_be_completed(self):
        self.store.reserve_assignment("W001", "B001", 1, "implementer",
                                      "issue:12", issue_number=12)
        self.store.record_verdict("W001", "b" * 40, "qa", "pass", [])
        code = self.refuse_execute(
            "github.set_state", {"issue_number": 12, "state": "closed",
                                 "state_reason": "completed",
                                 "reason": "Nothing was reported"})
        self.assertEqual(code, "ACCEPTANCE_REQUIRED")

    def seed_passing_verdict(self, outcome="pass", head="b" * 40,
                             verdict_sha=None):
        """An assignment that reported a head, and a verdict against one."""

        self.store.reserve_assignment("W001", "B001", 1, "implementer",
                                      "issue:12", issue_number=12)
        for state in ("starting", "running"):
            self.store.set_assignment_state("W001", state)
        self.store.set_assignment_state("W001", "reported", reported_sha=head)
        self.store.record_verdict("W001", verdict_sha or head, "qa", outcome,
                                  [{"ref": "artifact:E001", "sha256": "a" * 64}])

    def refuse_execute(self, kind, payload, **kwargs):
        prepared = self.prepare(kind, payload, **kwargs)
        return self.refuse("execute_action",
                           {"action_id": prepared["action_id"]})


class PublicRepositoryTest(BoardActionCase):

    def setUp(self):
        super().setUp()
        self.fake.visibility = "public"
        self.approve_setup_through_fake_ui(visibility="public")

    def test_prose_is_prepared_for_the_owner_rather_than_executed(self):
        result = self.execute("github.update_issue",
                              {"issue_number": 14, "title": "New title"})
        self.assertEqual(result["state"], "prepared")
        self.assertTrue(result["owner_approval_required"])
        self.assertEqual(self.fake.mutations(), [])

    def test_the_prepared_artifact_carries_the_exact_content(self):
        result = self.execute("github.update_issue",
                              {"issue_number": 14, "title": "New title"})
        self.assertEqual(result["artifact"]["operation"], "github.update_issue")
        self.assertEqual(result["artifact"]["payload"]["title"], "New title")
        self.assertEqual(result["artifact"]["repo"], self.repo)

    def test_metadata_still_executes_on_a_public_board(self):
        result = self.execute("github.set_labels",
                              {"issue_number": 14, "labels": ["ready"]})
        self.assertEqual(result["state"], "verified")

    def test_live_visibility_overrides_what_the_scope_declared(self):
        grant = self.store.active_setup_grant(self.repo)
        self.assertEqual(grant["scope"]["visibility"], "public")


class VisibilityProbeTest(BoardActionCase):

    def test_a_repository_declared_private_but_public_is_recorded_public(self):
        self.fake.visibility = "public"
        self.approve_setup_through_fake_ui(visibility="private")
        grant = self.store.active_setup_grant(self.repo)
        self.assertEqual(grant["scope"]["visibility"], "public")
        self.assertEqual(grant["scope"]["visibility_source"], "live")

    def test_an_unreadable_repository_is_recorded_unknown(self):
        """A read that failed is not the caller's word for what it found."""

        self.fake.repo_readable = False
        self.approve_setup_through_fake_ui(visibility="private")
        grant = self.store.active_setup_grant(self.repo)
        self.assertEqual(grant["scope"]["visibility_source"], "unknown")
        self.assertIsNone(grant["scope"].get("visibility_confirmed"))

    def test_an_unknown_visibility_prepares_prose_rather_than_writing_it(self):
        self.fake.repo_readable = False
        self.approve_setup_through_fake_ui(visibility="private")
        result = self.execute("github.update_issue",
                              {"issue_number": 14, "title": "New title"})
        self.assertEqual(result["state"], "prepared")
        self.assertTrue(result["owner_approval_required"])
        self.assertEqual(self.fake.mutations(), [])

    def test_an_unknown_visibility_with_no_earlier_live_read_blocks_metadata(self):
        self.fake.repo_readable = False
        self.approve_setup_through_fake_ui(visibility="private")
        code = self.refuse_execute("github.set_labels",
                                   {"issue_number": 14, "labels": ["ready"]})
        self.assertEqual(code, "VISIBILITY_UNKNOWN")
        self.assertEqual(self.fake.mutations(), [])

    def test_metadata_survives_a_failed_read_when_a_live_read_agreed_before(self):
        """Twice believed private is a stronger position than never checked."""

        self.approve_setup_through_fake_ui(visibility="private")
        self.store.revoke_grant(
            self.store.active_setup_grant(self.repo)["grant_id"], "re-running")
        self.fake.repo_readable = False
        self.approve_setup_through_fake_ui(visibility="private")
        grant = self.store.active_setup_grant(self.repo)
        self.assertEqual(grant["scope"]["visibility_source"], "unknown")
        self.assertEqual(grant["scope"]["visibility_confirmed"], "private")
        result = self.execute("github.set_labels",
                              {"issue_number": 14, "labels": ["ready"]})
        self.assertEqual(result["state"], "verified")

    def test_a_declared_private_repository_that_is_public_is_recorded_public(self):
        self.fake.visibility = "public"
        self.approve_setup_through_fake_ui(visibility="private")
        grant = self.store.active_setup_grant(self.repo)
        self.assertEqual(grant["scope"]["visibility"], "public")
        self.assertEqual(grant["scope"]["visibility_confirmed"], "public")

    def refuse_execute(self, kind, payload, **kwargs):
        prepared = self.prepare(kind, payload, **kwargs)
        return self.refuse("execute_action",
                           {"action_id": prepared["action_id"]})


class AssignmentOwnershipTest(BoardActionCase):

    def setUp(self):
        super().setUp()
        self.fake.assignable.add("amitbaz")

    def test_an_unmapped_role_keeps_ownership_in_cabinet(self):
        self.approve_setup_through_fake_ui()
        code = self.refuse_execute("github.set_assignees",
                                   {"issue_number": 14,
                                    "assignees": ["amitbaz"]})
        self.assertEqual(code, "ASSIGNEE_NOT_CONFIGURED")
        self.assertEqual(self.fake.mutations(), [])

    def test_a_configured_real_account_is_assigned(self):
        self.approve_setup_through_fake_ui(
            accounts={"engineering": "amitbaz"})
        result = self.execute("github.set_assignees",
                              {"issue_number": 14, "assignees": ["amitbaz"]})
        self.assertEqual(result["state"], "verified")

    def test_a_fictitious_username_cannot_be_configured(self):
        self.approve_setup_through_fake_ui(
            accounts={"engineering": "cabinet-engineering"})
        code = self.refuse_execute("github.set_assignees",
                                   {"issue_number": 14,
                                    "assignees": ["cabinet-engineering"]})
        self.assertEqual(code, "ASSIGNEE_UNKNOWN")

    def refuse_execute(self, kind, payload, **kwargs):
        prepared = self.prepare(kind, payload, **kwargs)
        return self.refuse("execute_action",
                           {"action_id": prepared["action_id"]})


class BoardFreshnessTest(BoardActionCase):

    def test_the_snapshot_reports_what_the_board_read_last_said(self):
        self.call("wait_events", {"after_seq": 0})
        board = self.call("snapshot")["freshness"]["board"]
        self.assertTrue(board["complete"])

    def test_a_partial_board_cannot_authorize_a_dispatch(self):
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()
        self.fake.fail_page("issues", 2)
        self.fake.collection("issues", [issue_row(n) for n in range(1, 151)])
        self.call("wait_events", {"after_seq": 0})
        prepared = self.prepare("worker.launch",
                                {"issue_number": 12, "role": "implementer"})
        code = self.refuse("execute_action",
                           {"action_id": prepared["action_id"]})
        self.assertEqual(code, "SOURCE_INCOMPLETE")

    def test_a_complete_board_lets_the_dispatch_reach_its_own_executor(self):
        self.approve_setup_through_fake_ui()
        self.approve_batch_through_fake_ui()
        self.call("wait_events", {"after_seq": 0})
        prepared = self.prepare("worker.launch",
                                {"issue_number": 12, "role": "implementer"})
        code = self.refuse("execute_action",
                           {"action_id": prepared["action_id"]})
        # Past the board gate and into O4's own executor, which then refuses
        # for its own reason: a worker is launched into a workspace, and this
        # assignment has not had one created yet.
        self.assertEqual(code, "WORKSPACE_NOT_CREATED")


if __name__ == "__main__":
    unittest.main()
