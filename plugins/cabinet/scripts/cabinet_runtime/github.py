"""The board adapter: paginated reads and verified, scoped writes.

This module is the only place in the runtime that talks to the issue provider,
and it is deliberately narrow. `apply` accepts nine named operations and
nothing else — no endpoint string, no query language, no comment — so the
model's influence over what reaches the provider ends at choosing which of the
nine, with which validated fields.

Four properties are worth naming, because each one is a defect that is easy to
ship and hard to notice afterwards:

* **A relationship is an edge between database identifiers.** The number is
  what a person types; the identifier is what the provider stores. Every edge
  here resolves its identifier from a read of the issue first, so a number can
  never arrive where an identifier belongs.
* **An incomplete read is not an empty one.** A page that failed is reported as
  a named error and the collection is marked incomplete. A caller that treats
  a shrunken board as the board would authorize the wrong work.
* **A write is not finished until it has been read back.** Every changed field
  and every edge is re-read afterwards and compared against what was asked
  for. A provider that answered 200 and did something else produces
  `uncertain`, never `verified`.
* **A timeout is ambiguous, not a failure.** The request may have arrived. The
  outcome is `uncertain` and `reconcile_action` is what settles it, by looking
  for the operation's own marker rather than by repeating the write.

The provider is reached through an injected `run(argv, input_text=None)`, which
returns the bounded dictionary `processes.run_argv` produces. Bodies travel on
standard input, never interpolated into a command line.
"""

import json
import time
from urllib.parse import quote

from . import processes
from .contracts import SETUP_BOARD_OPERATIONS
from .errors import CabinetError

#: The provider API version this adapter is written against. Verified live on
#: 2026-09-10: the response carried `X-Github-Api-Version-Selected: 2026-03-10`.
#: It is a constant rather than a caller's argument because the response shapes
#: this module parses are the ones that version returns.
API_VERSION = "2026-03-10"
ACCEPT = "application/vnd.github+json"

#: Issue states and close reasons the provider accepts, and Cabinet's own
#: pairing rule: a closed issue carries a reason, an open one carries none.
ISSUE_STATES = ("open", "closed")
STATE_REASONS = ("completed", "not_planned", "reopened")

#: Bounds. `MAX_PAGES` is a stop, not a page count: a collection that never
#: stops paginating is a provider defect, and looping on it forever is ours.
MAX_PAGES = 60
MAX_PR_CHECKS = 50

#: How many distinct issues a cycle walk will read before it gives up. It is a
#: whole-board number rather than a depth, because the dependency walk explores
#: a transitive closure and a closure is as wide as the board. Running out is a
#: refusal, not a pass: see `_reject_cycle`.
MAX_RELATION_NODES = 5000
PAGE_SIZE = 100

#: Rate limiting. Attempts are counted, each wait comes from the provider's own
#: guidance where it gave any, and a wait is never zero — a retry loop with no
#: delay is a busy loop whatever it is called.
RATE_LIMIT_ATTEMPTS = 3
DEFAULT_BACKOFF = (2.0, 8.0, 30.0)
MIN_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0

#: The delay a caller waits before re-reading for a create whose outcome was a
#: timeout and whose marker has not appeared yet.
RECONCILE_DELAY_SECONDS = 15

#: The block inside an issue body that Cabinet owns. Everything outside it is
#: somebody's writing and is never rewritten by a field edit.
MANAGED_BEGIN = "<!-- cabinet:begin -->"
MANAGED_END = "<!-- cabinet:end -->"
MARKER_PREFIX = "cabinet:action"

#: Operations that change something already on an issue, and therefore have to
#: say what they believe is there. Creating an issue is excluded: there is no
#: prior state to be stale about.
EXPECTATION_OPERATIONS = ("github.update_issue", "github.set_labels",
                          "github.set_assignees", "github.set_state")

#: The edge each operation has to know before it may change it. Against a
#: relationship the provider could not state, a reparent leaves the old parent
#: in place while reporting success, and a cycle check has nothing to walk, so
#: these refuse rather than write into the dark.
EDGE_OPERATIONS = {"github.set_parent": "parent",
                   "github.remove_parent": "parent",
                   "github.add_blocker": "blocked_by",
                   "github.remove_blocker": "blocked_by"}

#: Codes raised only from here. Each one names a different recovery, which is
#: the whole reason they are separate.
SOURCE_INCOMPLETE = "SOURCE_INCOMPLETE"
SOURCE_CHANGED = "SOURCE_CHANGED"

# Required and optional payload fields per operation. Anything else is refused
# before a request is built, so an invented field cannot ride along into a body.
_PAYLOAD_FIELDS = {
    "github.create_issue": (("title",),
                            ("body", "labels", "assignees", "idempotency_key")),
    "github.update_issue": (("issue_number",),
                            ("title", "body", "body_block",
                             "whole_body_reviewed")),
    "github.set_labels": (("issue_number", "labels"), ()),
    "github.set_assignees": (("issue_number", "assignees"), ()),
    "github.set_parent": (("issue_number", "parent_number"), ()),
    "github.remove_parent": (("issue_number",), ("parent_number",)),
    "github.add_blocker": (("issue_number", "blocker_number"), ()),
    "github.remove_blocker": (("issue_number", "blocker_number"), ()),
    "github.set_state": (("issue_number", "state", "state_reason", "reason"),
                         ()),
}


class GithubAdapter:
    """One repository's board, reached through `gh api` and nothing wider."""

    API_VERSION = API_VERSION
    OPERATIONS = SETUP_BOARD_OPERATIONS
    MANAGED_BEGIN = MANAGED_BEGIN
    MANAGED_END = MANAGED_END
    RATE_LIMIT_ATTEMPTS = RATE_LIMIT_ATTEMPTS

    def __init__(self, run, repo, api_version=API_VERSION, sleeper=None,
                 clock=None, page_size=PAGE_SIZE):
        self.run = run
        self.repo = repo
        self.api_version = api_version
        self._sleep = sleeper or time.sleep
        self._clock = clock or _utc_now
        self.page_size = page_size
        self._last_read = {"complete": True, "errors": [], "checked": None}
        self._requests = []

    # --- transport ---------------------------------------------------------

    def _argv(self, method, endpoint, has_body):
        argv = ["gh", "api", "-i", "--method", method, endpoint,
                "-H", "Accept: %s" % ACCEPT,
                "-H", "X-GitHub-Api-Version: %s" % self.api_version]
        if has_body:
            argv += ["--input", "-"]
        return argv

    def _request(self, method, endpoint, body=None):
        """One provider call, with bounded backoff and no busy loop.

        Returns a parsed response even for an error status: the caller decides
        whether a 404 is a failure or an answer. Only exhaustion of the rate
        limit and a malformed reply raise from here.
        """

        text = json.dumps(body, sort_keys=True) if body is not None else None
        argv = self._argv(method, endpoint, body is not None)
        for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
            response = _parse(self.run(argv, input_text=text))
            response["method"] = method
            response["path"] = endpoint.partition("?")[0]
            self._requests.append({"method": method, "path": response["path"],
                                   "status": response["status"]})
            if response["timed_out"] or not _is_rate_limited(response):
                return response
            if attempt == RATE_LIMIT_ATTEMPTS:
                raise CabinetError(
                    "RATE_LIMITED",
                    "the provider rate-limited %s %s %d times; the board is "
                    "unchanged and the wait is longer than this adapter will "
                    "hold a call open" % (method, response["path"], attempt))
            self._sleep(_backoff_seconds(response, attempt))
        raise CabinetError("RATE_LIMITED", "rate limited")  # pragma: no cover

    def _read(self, endpoint, what):
        """A GET whose failure is an error rather than an answer."""

        response = self._request("GET", endpoint)
        if response["timed_out"]:
            raise CabinetError("PROVIDER_UNCERTAIN",
                               "reading %s timed out" % what)
        if response["status"] >= 400:
            raise _status_error(response, what)
        return response["payload"]

    # --- reads -------------------------------------------------------------

    def read_visibility(self):
        """The repository's live visibility, for the setup grant to record."""

        payload = self._read("repos/%s" % self.repo, self.repo) or {}
        visibility = payload.get("visibility")
        if visibility not in ("public", "private", "internal"):
            visibility = "private" if payload.get("private") else "public"
        return "public" if visibility == "public" else "private"

    def read_issue(self, number):
        """One issue with its identifier, its parent and its blockers.

        A relationship the provider did not report is `unknown`. It is never
        an empty list: "there are none" and "this response could not say" lead
        to different decisions, and collapsing them loses the difference
        exactly where it matters.
        """

        errors = []
        payload = self._read("repos/%s/issues/%d" % (self.repo, int(number)),
                             "issue %s" % number)
        read = _issue_summary(payload)
        supported = "sub_issues_summary" in payload
        if supported and read["children_count"]:
            read["children"] = self._edge(
                "sub_issues", "repos/%s/issues/%d/sub_issues"
                % (self.repo, read["number"]), errors)
        elif supported:
            read["children"] = []
        if supported and read["blocked_by_count"]:
            read["blocked_by"] = self._edge(
                "blocked_by", "repos/%s/issues/%d/dependencies/blocked_by"
                % (self.repo, read["number"]), errors)
        elif supported:
            read["blocked_by"] = []
        read["errors"] = errors
        read["complete"] = not errors
        return read

    def _edge(self, collection, endpoint, errors):
        rows, complete = self._collect(collection, endpoint, errors)
        if not complete:
            return "unknown"
        return [row["number"] for row in rows]

    def read_changed_issues(self, since=None):
        """Issues updated since a timestamp. O2's `board.changed` scheduler.

        Pull requests are filtered out here as well: the collection returns
        both, and a pull request arriving as a board change would make the
        company re-read a board that did not move.
        """

        errors = []
        query = ["state=all", "sort=updated", "direction=desc",
                 "per_page=%d" % self.page_size]
        if since:
            query.append("since=%s" % quote(str(since), safe=""))
        rows, complete = self._collect(
            "issues", "repos/%s/issues?%s" % (self.repo, "&".join(query)),
            errors)
        self._record_read(complete, errors)
        return [{"number": row["number"], "title": row.get("title"),
                 "state": row.get("state"),
                 "updated_at": row.get("updated_at")}
                for row in rows if "pull_request" not in row]

    def board_state(self):
        """What the last collection read observed about its own completeness."""

        return dict(self._last_read)

    def read_board(self, since=None):
        """The whole board in one pass, with every page followed.

        `complete` is the field a dispatch decision reads. It is false whenever
        any page of any collection failed, and the failures are listed rather
        than summarized, so a caller can say which part of the board it cannot
        see.
        """

        errors = []
        taken_at = self._clock()
        raw, issues_complete = self._collect(
            "issues", "repos/%s/issues?state=open&per_page=%d"
            % (self.repo, self.page_size), errors)
        issues = [_board_issue(row) for row in raw if "pull_request" not in row]
        pulls, pulls_complete = self._collect(
            "pulls", "repos/%s/pulls?state=open&per_page=%d"
            % (self.repo, self.page_size), errors)
        branches, branches_complete = self._collect(
            "branches", "repos/%s/branches?per_page=%d"
            % (self.repo, self.page_size), errors)
        merged, merged_complete = self._merged_window(since, errors)
        epics = [row for row in issues if "epic" in row["labels"]]
        complete = all((issues_complete, pulls_complete, branches_complete,
                        merged_complete))
        self._record_read(complete, errors)
        return {
            "repo": self.repo, "taken_at": taken_at,
            "complete": complete, "errors": errors,
            "note": "A snapshot of one moment. Nothing here is carried "
                    "forward into a notebook.",
            "counts": {"open_issues": len(issues), "open_prs": len(pulls),
                       "branches": len(branches), "epics": len(epics),
                       "merged_since": len(merged)},
            "epics_index": [{"number": row["number"], "title": row["title"],
                             "url": row["url"]} for row in epics],
            "open_issues": issues,
            "open_prs": [self._board_pull(row, index)
                         for index, row in enumerate(pulls)],
            "branches": [row.get("name") for row in branches],
            "merged_window": since or None,
            "recently_merged": merged,
        }

    def _merged_window(self, since, errors):
        if not since:
            return [], True
        rows, complete = self._collect(
            "merged", "repos/%s/pulls?state=closed&sort=updated&direction=desc"
            "&per_page=%d" % (self.repo, self.page_size), errors)
        merged = []
        for row in rows:
            stamp = row.get("merged_at")
            if stamp and stamp >= since:
                merged.append({"number": row["number"], "title": row.get("title"),
                               "mergedAt": stamp,
                               "headRefName": (row.get("head") or {}).get("ref"),
                               "closes": _closing_references(row.get("body")),
                               "closes_source": "body_keywords"})
        return merged, complete

    def _board_pull(self, row, index):
        sha = (row.get("head") or {}).get("sha")
        return {"number": row["number"], "title": row.get("title"),
                "url": row.get("html_url"),
                "headRefName": (row.get("head") or {}).get("ref"),
                "isDraft": bool(row.get("draft")),
                "createdAt": row.get("created_at"),
                "updatedAt": row.get("updated_at"),
                "checks": self._checks(sha) if sha and index < MAX_PR_CHECKS
                else "unknown"}

    def _checks(self, sha):
        response = self._request(
            "GET", "repos/%s/commits/%s/check-runs?per_page=%d"
            % (self.repo, sha, self.page_size))
        if response["timed_out"] or response["status"] >= 400:
            return "unknown"
        counts = {}
        for run in (response["payload"] or {}).get("check_runs", []):
            name = (run.get("conclusion") or run.get("status")
                    or "PENDING").upper()
            counts[name] = counts.get(name, 0) + 1
        return counts

    def _collect(self, collection, endpoint, errors):
        """Follow every page, and say so when one of them did not arrive."""

        rows, page = [], 1
        while page <= MAX_PAGES:
            response = self._request("GET", endpoint)
            if response["timed_out"] or response["status"] >= 400:
                errors.append({
                    "code": SOURCE_INCOMPLETE, "collection": collection,
                    "page": page, "status": response["status"],
                    "detail": _message(response,
                                       "page %d of %s did not arrive"
                                       % (page, collection))})
                return rows, False
            payload = response["payload"]
            rows.extend(payload if isinstance(payload, list) else [])
            following = _next_link(response["headers"])
            if not following:
                return rows, True
            endpoint, page = following, page + 1
        errors.append({"code": SOURCE_INCOMPLETE, "collection": collection,
                       "page": MAX_PAGES, "status": None,
                       "detail": "%s did not stop paginating within %d pages"
                                 % (collection, MAX_PAGES)})
        return rows, False

    def _record_read(self, complete, errors):
        self._last_read = {"complete": complete, "errors": list(errors),
                           "checked": self._clock()}

    # --- writes ------------------------------------------------------------

    def apply(self, operation, payload, expected_before=None):
        """Run one named board operation and read back what it changed.

        The order is the guarantee. The operation is checked against the closed
        set, then the payload against that operation's fields, then the live
        issue against `expected_before`, and only then is anything written.
        Every refusal before the write leaves the board untouched, and the
        tests assert that by looking at the captured requests.
        """

        if operation not in self.OPERATIONS:
            raise CabinetError(
                "OPERATION_FORBIDDEN",
                "%r is not one of the board operations this adapter can "
                "perform; there is no general endpoint here" % (operation,))
        payload = self._validate(operation, payload)
        _check_expectations_present(operation, payload, expected_before)
        self._requests = []
        started = self._clock()
        if operation == "github.create_issue":
            return self._create_issue(payload, started)

        before = self.read_issue(payload["issue_number"])
        edge = EDGE_OPERATIONS.get(operation)
        if edge is not None and before[edge] == "unknown":
            raise CabinetError(
                SOURCE_INCOMPLETE,
                "issue %d's %s could not be read, so %s would be written "
                "against an edge nobody can see; a reparent onto an unread "
                "parent leaves the old one in place and reports success"
                % (before["number"], edge, operation))
        _check_expectations(before, expected_before)
        desired, substeps = getattr(self, "_op_" + operation.split(".", 1)[1])(
            before, payload)
        after = self.read_issue(payload["issue_number"])
        verified = _matches(after, desired)
        return {
            "operation": operation, "repo": self.repo,
            "outcome": "verified" if verified else "uncertain",
            "external_ref": _external_ref(self.repo, after),
            "before": _safe(_observed(before, desired)),
            "after": _safe(_observed(after, desired)),
            "changed": _changed(before, desired),
            "desired": _safe(_plain(desired)), "substeps": substeps,
            "requests": list(self._requests),
            "evidence": _safe({"reason": payload.get("reason"),
                               "started": started, "observed": self._clock()}),
        }

    def _validate(self, operation, payload):
        if not isinstance(payload, dict):
            raise CabinetError("FIELD_INVALID", "an action payload is an object")
        named = payload.get("repo")
        if named is not None and named != self.repo:
            raise CabinetError(
                "REPO_MISMATCH",
                "the payload names %r; this adapter is bound to %s"
                % (named, self.repo))
        required, optional = _PAYLOAD_FIELDS[operation]
        allowed = set(required) | set(optional) | {"repo"}
        for field in required:
            if field not in payload:
                raise CabinetError("FIELD_MISSING",
                                   "%s needs %s" % (operation, field))
        for field in payload:
            if field not in allowed:
                raise CabinetError(
                    "FIELD_UNKNOWN",
                    "%s is not a field of %s" % (field, operation))
        clean = dict(payload)
        for field in ("issue_number", "parent_number", "blocker_number"):
            if clean.get(field) is not None:
                clean[field] = _number(clean[field], field)
        for field in ("labels", "assignees"):
            if field in clean:
                clean[field] = _names(clean[field], field)
        if operation == "github.set_state":
            _check_state(clean)
        if operation == "github.update_issue":
            _check_body_change(clean)
        return clean

    # --- one operation each ------------------------------------------------

    def _op_update_issue(self, before, payload):
        body = dict()
        for field in ("title",):
            if field in payload:
                body[field] = payload[field]
        if "body_block" in payload:
            body["body"] = _merge_managed(before["body"], payload["body_block"])
        elif "body" in payload:
            body["body"] = payload["body"]
        if not body:
            raise CabinetError("FIELD_MISSING",
                               "github.update_issue changes nothing")
        self._write("PATCH", "repos/%s/issues/%d"
                    % (self.repo, before["number"]), body)
        return dict(body), []

    def _op_set_labels(self, before, payload):
        self._write("PUT", "repos/%s/issues/%d/labels"
                    % (self.repo, before["number"]),
                    {"labels": payload["labels"]})
        return {"labels": list(payload["labels"])}, []

    def _op_set_assignees(self, before, payload):
        for login in payload["assignees"]:
            self._require_assignable(login)
        self._write("PATCH", "repos/%s/issues/%d"
                    % (self.repo, before["number"]),
                    {"assignees": payload["assignees"]})
        return {"assignees": list(payload["assignees"])}, []

    def _require_assignable(self, login):
        response = self._request(
            "GET", "repos/%s/assignees/%s" % (self.repo, quote(login, safe="")))
        if response["status"] == 204 or 200 <= response["status"] < 300:
            return
        raise CabinetError(
            "ASSIGNEE_UNKNOWN",
            "%r cannot be assigned on %s; a role name is not a GitHub account "
            "and Cabinet never invents one" % (login, self.repo))

    def _op_set_parent(self, before, payload):
        parent = payload["parent_number"]
        self._reject_parent_cycle(before["number"], parent)
        self.read_issue(parent)
        substeps = []
        current = before["parent"]
        if current == parent:
            return {"parent": parent}, substeps
        if isinstance(current, int):
            substeps.append(self._substep(
                "remove_parent", "DELETE", "repos/%s/issues/%d/sub_issue"
                % (self.repo, current), {"sub_issue_id": before["id"]}))
        substeps.append(self._substep(
            "add_parent", "POST", "repos/%s/issues/%d/sub_issues"
            % (self.repo, parent), {"sub_issue_id": before["id"]}))
        return {"parent": parent}, substeps

    def _op_remove_parent(self, before, payload):
        current = before["parent"]
        if not isinstance(current, int):
            return {"parent": None}, []
        named = payload.get("parent_number")
        if named is not None and named != current:
            raise CabinetError(
                SOURCE_CHANGED,
                "issue %d has parent %s, not the %s the action expected"
                % (before["number"], current, named))
        return {"parent": None}, [self._substep(
            "remove_parent", "DELETE", "repos/%s/issues/%d/sub_issue"
            % (self.repo, current), {"sub_issue_id": before["id"]})]

    def _op_add_blocker(self, before, payload):
        blocker = self.read_issue(payload["blocker_number"])
        self._reject_dependency_cycle(before["number"], blocker["number"])
        self._write("POST", "repos/%s/issues/%d/dependencies/blocked_by"
                    % (self.repo, before["number"]), {"issue_id": blocker["id"]})
        return {"blocked_by": ("contains", blocker["number"])}, []

    def _op_remove_blocker(self, before, payload):
        blocker = self.read_issue(payload["blocker_number"])
        self._write("DELETE", "repos/%s/issues/%d/dependencies/blocked_by/%d"
                    % (self.repo, before["number"], blocker["id"]), None)
        return {"blocked_by": ("excludes", blocker["number"])}, []

    def _op_set_state(self, before, payload):
        body = {"state": payload["state"],
                "state_reason": payload["state_reason"]}
        self._write("PATCH", "repos/%s/issues/%d"
                    % (self.repo, before["number"]), body)
        return dict(body), []

    def _create_issue(self, payload, started):
        """Create once, with the action's own marker inside the body.

        The marker is what makes a create idempotent without a provider-side
        idempotency key: after an ambiguous outcome, `reconcile_action` looks
        for exactly one issue carrying it. No comment is written, here or
        anywhere else in this module.
        """

        body = {"title": payload["title"],
                "body": _with_marker(payload.get("body", ""),
                                     payload.get("idempotency_key"))}
        for field in ("labels", "assignees"):
            if payload.get(field):
                body[field] = payload[field]
        for login in payload.get("assignees") or ():
            self._require_assignable(login)
        response = self._write("POST", "repos/%s/issues" % self.repo, body)
        if response["timed_out"]:
            return {"operation": "github.create_issue", "repo": self.repo,
                    "outcome": "uncertain", "external_ref": None,
                    "before": {}, "after": {}, "changed": ["created"],
                    "desired": _safe({"title": payload["title"]}),
                    "substeps": [],
                    "requests": list(self._requests),
                    "evidence": {"marker": payload.get("idempotency_key"),
                                 "started": started, "observed": self._clock(),
                                 "note": "the create timed out after it may "
                                         "have been dispatched; reconcile "
                                         "before any retry"}}
        created = _issue_summary(response["payload"] or {})
        after = self.read_issue(created["number"])
        return {"operation": "github.create_issue", "repo": self.repo,
                "outcome": "verified" if after["title"] == payload["title"]
                else "uncertain",
                "external_ref": _external_ref(self.repo, after),
                "before": {}, "after": _safe(_observed(after, {"title": None})),
                "changed": ["created"],
                "desired": _safe({"title": payload["title"]}),
                "substeps": [], "requests": list(self._requests),
                "evidence": {"marker": payload.get("idempotency_key"),
                             "started": started, "observed": self._clock()}}

    def _write(self, method, endpoint, body):
        response = self._request(method, endpoint, body)
        if response["timed_out"]:
            return response
        if response["status"] >= 400:
            raise _status_error(response, "%s %s" % (method, endpoint))
        return response

    def _substep(self, name, method, endpoint, body):
        response = self._write(method, endpoint, body)
        return {"step": name, "method": method, "path": endpoint,
                "status": None if response["timed_out"] else response["status"],
                "timed_out": bool(response["timed_out"]),
                "observed": self._clock()}

    # --- cycles ------------------------------------------------------------

    def _reject_parent_cycle(self, child, parent):
        self._reject_cycle(
            child, parent, "parent",
            "making %d the parent of %d would close a hierarchy cycle"
            % (parent, child),
            "whether %d is already above %d" % (child, parent))

    def _reject_dependency_cycle(self, issue, blocker):
        self._reject_cycle(
            issue, blocker, "blocked_by",
            "blocking %d on %d would close a dependency cycle"
            % (issue, blocker),
            "whether %d is already upstream of %d" % (issue, blocker))

    def _reject_cycle(self, target, start, edge, cycle_message, question):
        """Walk one edge's transitive closure looking for `target`.

        Two rules make this a check rather than a gesture, and the second is
        the one that is easy to get wrong.

        * **The budget counts distinct issues, not hops, and running out is a
          refusal.** An earlier version spent a small budget per node visited
          and then *fell out of the loop and wrote the edge*. Because the
          dependency walk explores a whole upstream set, any issue with more
          than a few dozen blockers defeated the check no matter how short the
          cycle was — a two-hop cycle behind sixty-one blockers went straight
          through. An adapter that cannot finish the walk has not proved
          there is no cycle, which is the same position as an unreadable edge
          and gets the same answer: refuse, never write.
        * **An edge that could not be read is a refusal too.** "No blockers"
          and "this response could not say" lead to opposite decisions here.
        """

        queue, seen = [start], set()
        while queue:
            node = queue.pop()
            if node == target:
                raise CabinetError("RELATIONSHIP_CYCLE", cycle_message)
            if node in seen:
                continue
            if len(seen) >= MAX_RELATION_NODES:
                raise CabinetError(
                    SOURCE_INCOMPLETE,
                    "the %s graph reachable from issue %d is larger than the "
                    "%d issues this adapter will read to answer %s; it cannot "
                    "prove there is no cycle, so it writes nothing"
                    % (edge, start, MAX_RELATION_NODES, question))
            seen.add(node)
            edges = self.read_issue(node)[edge]
            if edges == "unknown":
                raise CabinetError(
                    SOURCE_INCOMPLETE,
                    "issue %d's own %s could not be read, so %s is unknown"
                    % (node, edge, question))
            queue.extend([edges] if isinstance(edges, int)
                         else (edges if isinstance(edges, list) else []))

    # --- reconciliation ----------------------------------------------------

    def reconcile_action(self, action):
        """Settle an ambiguous outcome by reading, never by repeating a write.

        A create is settled by its marker: zero matches can be retried after a
        bounded delay, one is adopted, and more than one is `uncertain` and
        stays that way until a person looks. Everything else is settled by
        comparing the live board against what the action asked for.
        """

        kind = action.get("kind")
        payload = action.get("payload") or {}
        if kind == "github.create_issue":
            return self._reconcile_create(action, payload)
        if kind not in self.OPERATIONS:
            raise CabinetError("OPERATION_FORBIDDEN",
                               "%r is not a board operation" % (kind,))
        live = self.read_issue(_number(payload["issue_number"], "issue_number"))
        applied = _already_applied(kind, payload, live)
        return {"action_id": action.get("action_id"), "kind": kind,
                "matches": 1 if applied else 0,
                "outcome": "already_applied" if applied else "not_applied",
                "external_ref": _external_ref(self.repo, live),
                "observed": self._clock(),
                "live": _observed(live, {"title": None, "state": None,
                                         "labels": None, "assignees": None,
                                         "parent": None, "blocked_by": None})}

    def _reconcile_create(self, action, payload):
        marker = _marker(action.get("idempotency_key")
                         or payload.get("idempotency_key"))
        errors = []
        rows, complete = self._collect(
            "issues", "repos/%s/issues?state=all&sort=created&direction=desc"
            "&per_page=%d" % (self.repo, self.page_size), errors)
        if not complete:
            raise CabinetError(
                SOURCE_INCOMPLETE,
                "the issues collection is incomplete, so the number of issues "
                "carrying %s cannot be counted" % marker)
        matches = [row for row in rows
                   if marker in (row.get("body") or "")
                   and "pull_request" not in row]
        result = {"action_id": action.get("action_id"),
                  "kind": "github.create_issue", "marker": marker,
                  "matches": len(matches), "external_ref": None,
                  "observed": self._clock()}
        if len(matches) == 1:
            result.update(outcome="adopted",
                          external_ref=_external_ref(
                              self.repo, _issue_summary(matches[0])))
        elif not matches:
            result.update(outcome="retry_after_delay",
                          retry_after_seconds=RECONCILE_DELAY_SECONDS)
        else:
            result.update(
                outcome="uncertain",
                numbers=[row["number"] for row in matches],
                detail="%d issues carry this action's marker; adopting either "
                       "would be a guess" % len(matches))
        return result


# --- response parsing --------------------------------------------------------

def _parse(result):
    """Turn one `gh api -i` result into a status, headers and a payload."""

    if not isinstance(result, dict):
        raise CabinetError("PROVIDER_ERROR",
                           "the run callable did not return a result mapping")
    if result.get("timed_out"):
        return {"timed_out": True, "status": None, "headers": {},
                "payload": None}
    stdout = result.get("stdout") or ""
    head, separator, body = stdout.partition("\r\n\r\n")
    if not separator:
        head, separator, body = stdout.partition("\n\n")
    if not separator:
        raise CabinetError(
            "PROVIDER_ERROR",
            "the provider reply carried no header block; %s"
            % (result.get("stderr") or "no diagnostic"))
    lines = head.replace("\r\n", "\n").split("\n")
    try:
        status = int(lines[0].split()[1])
    except (IndexError, ValueError):
        raise CabinetError("PROVIDER_ERROR",
                           "the provider reply had no status line") from None
    headers = {}
    for line in lines[1:]:
        name, colon, value = line.partition(":")
        if colon:
            headers[name.strip().lower()] = value.strip()
    payload = None
    if body.strip():
        try:
            payload = json.loads(body)
        except ValueError:
            # Never `payload = None`. A reply this adapter cannot read is not
            # an empty collection, and the difference between the two is the
            # whole point of the completeness rule: a page that arrived
            # truncated must be reported, not counted as zero rows.
            raise CabinetError(
                "PROVIDER_ERROR",
                "the HTTP %d reply was not readable JSON (%d bytes); it may "
                "have been truncated" % (status, len(body))) from None
    return {"timed_out": False, "status": status, "headers": headers,
            "payload": payload}


def _is_rate_limited(response):
    if response["status"] == 429:
        return True
    if response["status"] != 403:
        return False
    headers = response["headers"]
    if headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers:
        return True
    return "rate limit" in (_message(response, "") or "").lower()


def _backoff_seconds(response, attempt):
    headers = response["headers"]
    seconds = None
    if headers.get("retry-after"):
        seconds = _float(headers["retry-after"])
    if seconds is None and headers.get("x-ratelimit-reset"):
        reset = _float(headers["x-ratelimit-reset"])
        if reset is not None:
            seconds = reset - time.time()
    if seconds is None or seconds <= 0:
        seconds = DEFAULT_BACKOFF[min(attempt, len(DEFAULT_BACKOFF)) - 1]
    return min(max(seconds, MIN_BACKOFF_SECONDS), MAX_BACKOFF_SECONDS)


def _float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _message(response, fallback):
    """The provider's own explanation, redacted before it is surfaced.

    `gh_run` turns off the subprocess adapter's whole-output redaction so a
    JSON body survives parsing. What is still redacted, and what is not:

    * **redacted** — the child's stderr (`processes.run_argv` always redacts
      that), provider `message` fields, which is this function, and every
      string inside an action's evidence record, through `_safe`.
    * **not redacted** — issue titles, issue bodies and comment bodies in
      `read_board`, `read_issue` and the snapshot files. That is deliberate:
      it is the owner's own board content, and masking it would corrupt the
      prose a role has to read. A credential pasted into a ticket body stays
      in the board file, as it already does on GitHub.
    """

    payload = response.get("payload")
    if isinstance(payload, dict) and payload.get("message"):
        return processes.redact(str(payload["message"]))
    return fallback


def _status_error(response, what):
    status = response["status"]
    code = {401: "AUTH_REQUIRED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(
        status, "PROVIDER_ERROR")
    return CabinetError(code, "%s: HTTP %d — %s"
                        % (what, status, _message(response, "no detail")))


def _next_link(headers):
    """The `rel="next"` URL, followed as given rather than rebuilt.

    The issues collection paginates by cursor, so a page number reconstructed
    locally walks a different sequence than the provider intended.
    """

    for part in (headers.get("link") or "").split(","):
        section, _, relation = part.partition(";")
        if 'rel="next"' in relation and "<" in section:
            return section.strip().strip("<>").strip()
    return None


# --- issue shapes ------------------------------------------------------------

def _issue_summary(payload):
    summary = payload.get("sub_issues_summary")
    dependencies = payload.get("issue_dependencies_summary")
    parent_url = payload.get("parent_issue_url")
    return {
        "number": payload.get("number"), "id": payload.get("id"),
        "node_id": payload.get("node_id"), "title": payload.get("title"),
        "body": payload.get("body") or "", "state": payload.get("state"),
        "state_reason": payload.get("state_reason"),
        "labels": [row.get("name") for row in payload.get("labels") or []],
        "assignees": [row.get("login") for row in payload.get("assignees") or []],
        "updated_at": payload.get("updated_at"),
        "created_at": payload.get("created_at"),
        "url": payload.get("html_url") or payload.get("url"),
        "is_pull_request": "pull_request" in payload,
        "parent": _parent_number(parent_url) if summary is not None else "unknown",
        "children": "unknown", "blocked_by": "unknown",
        "children_count": (summary or {}).get("total")
        if summary is not None else "unknown",
        "blocked_by_count": (dependencies or {}).get("total_blocked_by")
        if dependencies is not None else "unknown",
    }


def _board_issue(payload):
    """One board row, in the shape the legacy snapshot promised its readers."""

    read = _issue_summary(payload)
    counted = read["blocked_by_count"]
    children = read["children_count"]
    return {"number": read["number"], "title": read["title"], "url": read["url"],
            "createdAt": read["created_at"], "updatedAt": read["updated_at"],
            "labels": read["labels"], "state": read["state"],
            "parent": read["parent"],
            "children": [] if children == 0 else "unknown",
            "children_count": children,
            "blocked_by": [] if counted == 0 else "unknown",
            "blocked_by_count": counted}


def _parent_number(url):
    if not url:
        return None
    tail = str(url).rstrip("/").rsplit("/", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return None


def _external_ref(repo, read):
    return {"repo": repo, "issue_number": read.get("number"),
            "issue_id": read.get("id"), "node_id": read.get("node_id"),
            "url": read.get("url")}


# --- expectations, verification and bodies -----------------------------------

#: How an `expected_before` key names something on the live issue. Both spellings
#: of the timestamp are accepted: the action envelope in the contracts calls it
#: `issue_updated_at`, and a caller copying a provider field calls it
#: `updated_at`. Refusing one of them would be a spelling test, not a check.
_EXPECTED_KEYS = {"issue_updated_at": "updated_at", "updated_at": "updated_at",
                  "title": "title", "body": "body", "state": "state",
                  "state_reason": "state_reason", "labels": "labels",
                  "assignees": "assignees", "parent": "parent",
                  "blocked_by": "blocked_by"}

_TIMESTAMP_KEYS = ("issue_updated_at", "updated_at")


def required_expectations(operation, payload):
    """What a caller must have observed before it may ask for this change.

    Conflict-aware writing is not something a caller opts into. An action that
    changes a field on an existing issue has to say what it believes that field
    and the issue's timestamp are, so the re-read taken immediately before the
    write has something to disagree with. An action carrying nothing gets no
    comparison at all, and an update that overwrites somebody's concurrent
    edit then reports `verified`.

    A managed-block edit is the one place `body` is not required: it changes
    only the text between Cabinet's own markers and leaves every other line
    alone, so the timestamp is the check that matters. Replacing a whole body
    is the destructive case, and that one must name the body it is replacing.
    """

    if operation not in EXPECTATION_OPERATIONS:
        return ()
    needed = ["issue_updated_at"]
    if operation == "github.update_issue":
        needed += [field for field in ("title", "body") if field in payload]
    elif operation == "github.set_labels":
        needed.append("labels")
    elif operation == "github.set_assignees":
        needed.append("assignees")
    elif operation == "github.set_state":
        needed += ["state", "state_reason"]
    return tuple(needed)


def observe_expectations(read, operation, payload):
    """Build `expected_before` from a `read_issue` result.

    This is how a caller records what it saw. It exists so the requirement
    above is a step somebody takes rather than a trap they fall into.
    """

    observed = {}
    for key in required_expectations(operation, payload):
        observed[key] = read.get(_EXPECTED_KEYS[key])
    return observed


def _check_expectations_present(operation, payload, expected):
    supplied = set(expected or ())
    if any(key in supplied for key in _TIMESTAMP_KEYS):
        supplied.update(_TIMESTAMP_KEYS)
    missing = [key for key in required_expectations(operation, payload)
               if key not in supplied]
    if missing:
        raise CabinetError(
            "EXPECTATION_REQUIRED",
            "%s must state what it believes it is changing: expected_before "
            "is missing %s. Read the issue, record those values, and prepare "
            "the action against them — a write with nothing to compare is a "
            "write that cannot notice somebody else's edit"
            % (operation, ", ".join(missing)))


def _check_expectations(before, expected):
    """Refuse a write whose subject moved since the action was prepared.

    There is no compare-and-set on an issue update, so this is a re-read taken
    immediately before the write and nothing stronger. It catches the editor
    who changed the ticket while the action waited; it cannot catch one who
    changes it in the microseconds after. That limit is stated rather than
    papered over, and the before/after artifacts are what a person reads when
    they need to know which happened.
    """

    for key, expectation in (expected or {}).items():
        field = _EXPECTED_KEYS.get(key)
        if field is None:
            raise CabinetError("FIELD_UNKNOWN",
                               "%s is not an observable issue field" % key)
        observed = before.get(field)
        if _plain_value(observed) != _plain_value(expectation):
            raise CabinetError(
                SOURCE_CHANGED,
                "issue %s changed since this action was prepared: %s was %r "
                "when it was prepared and is %r now"
                % (before.get("number"), key, expectation, observed))


def _matches(after, desired):
    for field, wanted in desired.items():
        observed = after.get(field)
        if isinstance(wanted, tuple):
            mode, value = wanted
            if not isinstance(observed, list):
                return False
            if mode == "contains" and value not in observed:
                return False
            if mode == "excludes" and value in observed:
                return False
        elif _plain_value(observed) != _plain_value(wanted):
            return False
    return True


def _changed(before, desired):
    changed = []
    for field, wanted in desired.items():
        observed = before.get(field)
        if isinstance(wanted, tuple):
            mode, value = wanted
            present = isinstance(observed, list) and value in observed
            if (mode == "contains") != present:
                changed.append(field)
        elif _plain_value(observed) != _plain_value(wanted):
            changed.append(field)
    return changed


def _observed(read, desired):
    fields = set(desired) | {"number", "updated_at"}
    return {field: read.get(field) for field in sorted(fields)
            if field in read}


def _plain(desired):
    return {field: list(value) if isinstance(value, tuple) else value
            for field, value in desired.items()}


def _plain_value(value):
    return sorted(value) if isinstance(value, list) else value


def _safe(value):
    """Mask credential material inside an evidence record, keeping its shape.

    An action's evidence carries issue titles and bodies, and a body is prose
    somebody wrote — occasionally including a token they meant to put
    somewhere else. This runs over the parsed values rather than over the raw
    reply, so the record stays serializable; that is the whole reason
    `processes.redact_values` exists beside `redact`.
    """

    if isinstance(value, str):
        return processes.redact_values(value)
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    return value


def _merge_managed(body, block):
    """Replace Cabinet's block, leaving every other line of the body alone."""

    text = body or ""
    replacement = "%s\n%s\n%s" % (MANAGED_BEGIN, block, MANAGED_END)
    start = text.find(MANAGED_BEGIN)
    end = text.find(MANAGED_END)
    if start == -1 or end == -1 or end < start:
        joiner = "\n\n" if text.strip() else ""
        return text + joiner + replacement
    return text[:start] + replacement + text[end + len(MANAGED_END):]


def _marker(key):
    return "<!-- %s %s -->" % (MARKER_PREFIX, key or "unkeyed")


def _with_marker(body, key):
    return _merge_managed(body, _marker(key))


def _closing_references(body):
    """Issue numbers a merged pull request's body says it closes."""

    words = (body or "").replace("#", " #").split()
    closes, arm = [], False
    for word in words:
        lowered = word.strip(",.;:").lower()
        if lowered in ("close", "closes", "closed", "fix", "fixes", "fixed",
                       "resolve", "resolves", "resolved"):
            arm = True
            continue
        if arm and lowered.startswith("#") and lowered[1:].isdigit():
            closes.append(int(lowered[1:]))
        arm = False
    return closes


def _already_applied(kind, payload, live):
    if kind == "github.add_blocker":
        return _in(live["blocked_by"], payload.get("blocker_number"))
    if kind == "github.remove_blocker":
        return isinstance(live["blocked_by"], list) \
            and not _in(live["blocked_by"], payload.get("blocker_number"))
    if kind == "github.set_parent":
        return live["parent"] == payload.get("parent_number")
    if kind == "github.remove_parent":
        return live["parent"] is None
    if kind == "github.set_labels":
        return sorted(live["labels"]) == sorted(payload.get("labels") or [])
    if kind == "github.set_assignees":
        return sorted(live["assignees"]) == sorted(payload.get("assignees") or [])
    if kind == "github.set_state":
        return live["state"] == payload.get("state") \
            and live["state_reason"] == payload.get("state_reason")
    return all(live.get(field) == value for field, value in payload.items()
               if field in ("title", "body"))


def _in(edges, number):
    return isinstance(edges, list) and number in edges


# --- payload validation ------------------------------------------------------

def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CabinetError("FIELD_INVALID",
                           "%s must be a positive issue number" % field)
    return value


def _names(value, field):
    if not isinstance(value, list):
        raise CabinetError("FIELD_INVALID", "%s must be a list" % field)
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CabinetError("FIELD_INVALID",
                               "%s holds a name that is not text" % field)
    return list(value)


def _check_state(payload):
    if payload["state"] not in ISSUE_STATES:
        raise CabinetError("FIELD_INVALID",
                           "state must be one of %s" % (ISSUE_STATES,))
    if payload["state_reason"] not in STATE_REASONS:
        raise CabinetError("FIELD_INVALID",
                           "state_reason must be one of %s" % (STATE_REASONS,))
    if payload["state"] == "closed" and payload["state_reason"] == "reopened":
        raise CabinetError("FIELD_INVALID",
                           "a closed issue cannot carry the reason 'reopened'")
    if payload["state"] == "open" and payload["state_reason"] != "reopened":
        raise CabinetError("FIELD_INVALID",
                           "an open issue's only reason is 'reopened'")
    if not isinstance(payload["reason"], str) or not payload["reason"].strip():
        raise CabinetError(
            "FIELD_INVALID",
            "a state change records the business reason for it; that reason "
            "is stored in Cabinet and never written to the board as a comment")


def _check_body_change(payload):
    if "body" in payload and "body_block" in payload:
        raise CabinetError(
            "FIELD_INVALID",
            "an update changes either Cabinet's managed block or the whole "
            "body, not both")
    if "body" in payload and payload.get("whole_body_reviewed") is not True:
        raise CabinetError(
            "WHOLE_BODY_UNREVIEWED",
            "replacing a whole issue body overwrites somebody's writing; pass "
            "body_block to change only Cabinet's block, or set "
            "whole_body_reviewed once the exact replacement has been reviewed")


#: The only environment `gh` is given. It is the one credentialed child the
#: runtime starts, and the list is short on purpose: a variable absent from it
#: is absent from the child, because `build_env` has no fallback to the parent.
GH_ENVIRONMENT = ("PATH", "HOME", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                  "XDG_STATE_HOME", "GH_CONFIG_DIR", "GH_HOST", "GH_TOKEN",
                  "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN")

#: How long one provider call may take before its outcome becomes ambiguous.
REQUEST_TIMEOUT_SECONDS = 60

#: How much of one provider page may be read. A page of a hundred issues with
#: full bodies runs past the subprocess adapter's default megabyte, and a
#: truncated page is refused rather than counted, so the bound is raised here
#: to the size a real page reaches rather than left to fail on large boards.
PROVIDER_OUTPUT_LIMIT = 32 * 1024 * 1024


def gh_run(cwd="/", timeout=REQUEST_TIMEOUT_SECONDS, environ=None):
    """Build the `run` callable a production adapter is constructed with.

    Everything it inherits is named above. The result is bounded by
    `processes.run_argv`, and its **stderr** is redacted there; its stdout is
    not, because redaction rewrites `"key":"mit"` into invalid JSON and this
    caller parses what comes back. The adapter redacts what it surfaces
    instead — see `_message` for exactly what that covers and what it does
    not.
    """

    env = processes.build_env(GH_ENVIRONMENT, environ=environ)

    def run(argv, input_text=None):
        return processes.run_argv(argv, cwd, env, timeout,
                                  input_text=input_text,
                                  output_limit=PROVIDER_OUTPUT_LIMIT,
                                  redact_output=False)

    return run


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
