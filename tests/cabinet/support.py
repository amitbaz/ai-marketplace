"""Shared test fixtures for the Cabinet runtime suites.

Repository-only module (see AGENTS.md: `tests/` is not shipped). Nothing here
is imported by production code or exposed by the service. Standard library
only, so the suite runs with the interpreter already on the machine.

Import as `from support import batch, action, FakeClock` with
`PYTHONPATH=plugins/cabinet/scripts:tests/cabinet`.
"""

import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def batch():
    return {
        "batch_id":"B001", "revision":1, "repo":"demo/company",
        "goal":"Invite one tester", "outcome":"Only an invited account can enter",
        "in_scope":["Invitation check"], "out_of_scope":["Payments"],
        "acceptance":[{"id":"AC1","behavior":"Uninvited account is rejected"}],
        "issues":[12], "base_sha":"a" * 40, "owned_paths":["app/"],
        "check_profile_ids":["local-unit"], "risks":[],
        "capacity":{"implementation_workers":1},
        "release_policy":"owner_approval", "external_publication":False
    }


def action(key="create-12"):
    return {"action_id":"A001", "idempotency_key":key,
            "kind":"workspace.create", "batch_id":"B001", "revision":1,
            "expected_before":{}, "payload":{"issue_number":12}}


def handoff_envelope(**overrides):
    """The contracts' H001 QA correction, with any field replaced."""

    envelope = {
        "handoff_id":"H001", "batch_id":"B001", "revision":1,
        "from_role":"qa", "to_role":"engineering", "kind":"correction",
        "question":"The uninvited account entered; correct AC1",
        "evidence":[{"ref":"artifact:E001", "sha256":"a" * 64}],
        "reply_to":"H001",
        "expected_response":"Correction SHA and verification evidence"
    }
    envelope.update(overrides)
    return envelope


#: Every packaged role that runs as one of the chief's in-process teammates
#: addresses its peers by its own role name, which is what the chief registers.
ROLE_ADDRESSES = ("chief-of-staff", "product", "engineering", "qa",
                  "delivery-lead")


class FakeClock:
    def __call__(self):
        return "2026-09-09T12:00:00Z"


class FakeElicitor:
    def __init__(self, response):
        self.response = response
        self.requests = []
    def request(self, message, schema):
        self.requests.append((message, copy.deepcopy(schema)))
        return copy.deepcopy(self.response)


class RaisingElicitor:
    """An elicitor whose dialog never returns: timeout, closed session, refusal.

    `hook` runs before the error is raised, for the case where the company
    also moved during the same unanswered wait.
    """

    def __init__(self, error, hook=None):
        self.error = error
        self.hook = hook
        self.requests = []

    def request(self, message, schema):
        self.requests.append((message, copy.deepcopy(schema)))
        if self.hook is not None:
            self.hook()
        raise self.error


class MutatingElicitor:
    """An elicitor that changes company state while the dialog is open.

    `hook` runs after the request is recorded and before the response is
    returned, which is the window a client dialog occupies in production.
    """

    def __init__(self, response, hook):
        self.response = response
        self.hook = hook
        self.requests = []

    def request(self, message, schema):
        self.requests.append((message, copy.deepcopy(schema)))
        self.hook()
        return copy.deepcopy(self.response)


class RecordingExecutor:
    """Stands in for every adapter. A forbidden action must never reach it."""

    def __init__(self):
        self.calls = []

    def run(self, envelope):
        self.calls.append(copy.deepcopy(envelope))
        return {"ok": True}


def guarded_execute(policy, executor, envelope):
    """Authorize, then invoke the adapter. Mirrors `execute_action`'s order."""

    grant = policy.authorize(envelope)
    return grant, executor.run(envelope)


def setup_scope(repo="demo/company", visibility="private", operations=None,
                profiles=None, workers=1, accounts=None):
    """The setup scope the owner is asked to approve in the setup dialog."""

    if profiles is None:
        profiles = ["local-unit"]
    return {
        "github_accounts": dict(accounts or {}),
        "repo": repo,
        "visibility": visibility,
        "board_operations": list(operations if operations is not None else (
            "github.create_issue", "github.update_issue", "github.set_labels",
            "github.set_assignees", "github.set_parent", "github.remove_parent",
            "github.add_blocker", "github.remove_blocker", "github.set_state")),
        "check_profiles": [{"profile_id": name,
                            "argv": ["python3", "-m", "unittest"],
                            "env": {"PYTHONHASHSEED": "0"}}
                           for name in profiles],
        "capacity": {"implementation_workers": workers},
    }


class CountingClock:
    """A clock whose readings move backwards, to prove cursors use `seq`."""

    def __init__(self, start=2026):
        self.year = start

    def __call__(self):
        self.year -= 1
        return "%04d-01-01T00:00:00Z" % self.year


def dead_processes(*pids):
    """Return a `process_alive` callable reporting the named PIDs as dead."""

    dead = set(pids)

    def probe(pid, process_start):
        return pid not in dead

    return probe


def always_alive(pid, process_start):
    return True


def copy_legacy_company(destination):
    """Copy the synthetic legacy Markdown company into `destination`."""

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for source in sorted((FIXTURES / "legacy-company").glob("*.md")):
        shutil.copy2(source, destination / source.name)
    return destination


def file_state(directory):
    """Return name -> (size, mtime_ns, bytes) for every Markdown file."""

    state = {}
    for path in sorted(Path(directory).glob("*.md")):
        stat = path.stat()
        state[path.name] = (stat.st_size, stat.st_mtime_ns, path.read_bytes())
    return state


def repo_root():
    return Path(__file__).resolve().parents[2]


def runtime_pythonpath():
    return os.pathsep.join([
        str(repo_root() / "plugins/cabinet/scripts"),
        str(repo_root() / "tests/cabinet"),
    ])


class CompanyCase(unittest.TestCase):
    """A company with one proposed batch and this process holding the lease.

    No fixture here inserts a grant. Every approval in the approval and policy
    suites travels through an elicitor response, which is the only path that
    creates one in production.
    """

    repo = "demo/company"

    def setUp(self):
        from cabinet_runtime.store import Store, own_process_identity

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = FakeClock()
        self.store = Store(self.root, self.clock, repo=self.repo).open()
        self.addCleanup(self.store.close)
        self.store.propose_batch(batch())
        pid, marker = own_process_identity()
        self.store.acquire_lease("S1", pid, marker)
        self.executor = RecordingExecutor()

    def approve(self, batch_id="B001", revision=1):
        """Approve a batch the way the owner does: an accepting dialog."""

        from cabinet_runtime.approval import ApprovalService

        ui = FakeElicitor({"action": "accept", "content": {"approve": True}})
        outcome = ApprovalService(self.store, ui).request(batch_id, revision)
        self.elicitor = ui
        return outcome

    def approve_setup(self, **kwargs):
        """Complete the one-time setup dialog for this repository."""

        from cabinet_runtime.approval import ApprovalService

        ui = FakeElicitor({"action": "accept", "content": {"approve": True}})
        outcome = ApprovalService(self.store, ui).request_setup(
            setup_scope(**kwargs))
        self.setup_elicitor = ui
        return outcome


# --- service, launcher and protocol fixtures --------------------------------
#
# Everything below lands with F4b. `ServiceCase` is the fixture the contracts'
# table names, and O2 through A2 build their suites on it.

PLUGIN_ROOT = repo_root() / "plugins" / "cabinet"
SERVICE_SCRIPT = PLUGIN_ROOT / "scripts" / "cabinet-service"
LAUNCH_SCRIPT = PLUGIN_ROOT / "scripts" / "cabinet-launch"
MCP_JSON = PLUGIN_ROOT / ".mcp.json"


def load_script(path, name):
    """Import a packaged executable as a module without running it."""

    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeGithub:
    """Recorder standing in for the board adapter O3 lands.

    `execute_action` must refuse a forbidden kind before anything reaches an
    adapter, so `calls` staying empty is the assertion, not the return value.
    """

    def __init__(self):
        self.calls = []

    def apply(self, operation, payload):
        self.calls.append((operation, copy.deepcopy(payload)))
        return {"ok": True}


class FakeSuperset:
    """Recorder standing in for the workspace adapter O4 lands."""

    def __init__(self):
        self.calls = []
        self.launch_count = 0
        self.workspace_create_count = 0

    def create_workspace(self, name, branch, base_ref):
        self.calls.append(("create_workspace", name, branch, base_ref))
        self.workspace_create_count += 1
        return {"workspace_id": "W-fake"}

    def create_terminal(self, workspace_id, launch_argv):
        self.calls.append(("create_terminal", workspace_id, list(launch_argv)))
        self.launch_count += 1
        return {"terminal_id": "T-fake"}


def launch_context(company_dir, repo="demo/company", session_id="S1",
                   launch_id="L0000000", profile_digest=None,
                   profile_path=None, role="chief-of-staff"):
    """The verified restricted-launch record `cabinet-service` hands over.

    It carries no capability: the entrypoint verifies the capability and
    passes on only the facts the service is allowed to hold.
    """

    company_dir = str(company_dir)
    return {
        "kind": "restricted",
        "launch_id": launch_id,
        "company_dir": company_dir,
        "repo": repo,
        "role": role,
        "profile_path": profile_path or
        "%s/runtime/profiles/%s.settings.json" % (company_dir, launch_id),
        "profile_digest": profile_digest or ("0" * 64),
        "session_id": session_id,
    }


class ServiceCase(unittest.TestCase):
    """A company whose service this process may mutate.

    Set `restricted = False` in a subclass for the ordinary plugin-loaded
    connection, which holds no launcher context and may only read.
    """

    repo = "demo/company"
    restricted = True
    #: Set on a subclass whose tests check a sender or recipient against the
    #: registered native addresses. Off by default so a suite that does not
    #: care about addressing keeps a company with no registrations in it.
    register_addresses = False

    def setUp(self):
        from cabinet_runtime import profiles
        from cabinet_runtime.service import CabinetService
        from cabinet_runtime.store import Store, own_process_identity

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "company"
        self.clock = FakeClock()
        self.store = Store(self.root, self.clock, repo=self.repo).open()
        self.addCleanup(self.store.close)
        self.store.propose_batch(batch())
        pid, marker = own_process_identity()
        self.store.acquire_lease("S1", pid, marker)
        self.github = FakeGithub()
        self.superset = FakeSuperset()
        self.elicitor = FakeElicitor({"action": "accept",
                                      "content": {"approve": True}})
        self.launch = (launch_context(self.root, repo=self.repo)
                       if self.restricted else None)
        self.service = CabinetService(
            self.store, self.github, self.superset, self.clock, self.elicitor,
            profiles.build_profile, launch=self.launch, sleeper=lambda _: None)
        self.qa_correction = handoff_envelope()
        if self.register_addresses:
            self.register_role_addresses()

    def register_role_addresses(self, roles=ROLE_ADDRESSES):
        """Bind each role's native address the way the chief does at startup.

        A message-body `from_role` is a claim. These registrations are what it
        is checked against, so a suite that tests sender or recipient identity
        needs them present before the first handoff is recorded.
        """

        for role in roles:
            self.call("register_staff", {"role": role, "native_address": role})

    def call(self, method, arguments=None):
        """Call a tool the way the protocol layer does."""

        return self.service.call("cabinet_%s" % method, arguments or {})

    def refuse(self, method, arguments=None):
        """Call a tool expecting a CabinetError; return its code."""

        from cabinet_runtime.errors import CabinetError

        try:
            self.call(method, arguments)
        except CabinetError as problem:
            return problem.code
        raise AssertionError("cabinet_%s did not refuse" % method)

    def approve_batch_through_fake_ui(self, batch_id="B001", revision=1):
        """Approve a batch the way the owner does: an accepting dialog."""

        self.elicitor.response = {"action": "accept",
                                  "content": {"approve": True}}
        return self.call("request_owner_approval",
                         {"batch_id": batch_id, "revision": revision})

    def approve_setup_through_fake_ui(self, **kwargs):
        """Complete the one-time setup dialog through the service."""

        self.elicitor.response = {"action": "accept",
                                  "content": {"approve": True}}
        kwargs.setdefault("repo", self.repo)
        return self.call("setup", {"scope": setup_scope(**kwargs)})


class FixtureBuilder:
    """Seeds stored records together with the events that produced them.

    Nothing here writes a row behind the service's back: each fixture drives
    the same operations production uses, so a record that could not be reached
    through the service cannot be reached through a fixture either.
    """

    def __init__(self, case):
        self.case = case

    def handoff(self, handoff_id="H001", state="recorded", **overrides):
        """Seed the contracts' QA correction and walk it to `state`."""

        envelope = handoff_envelope(handoff_id=handoff_id, **overrides)
        service = self.case.service
        service.record_handoff(envelope)
        if state == "recorded":
            return envelope
        service.update_handoff(handoff_id, "sent",
                               {"transport": "native",
                                "recipient": envelope["to_role"],
                                "result": "sent",
                                "native_sender": envelope["from_role"]})
        if state == "sent":
            return envelope
        recipient = self.case.store.get_address(envelope["to_role"])
        service.update_handoff(handoff_id, "acknowledged",
                               {"native_sender": envelope["to_role"],
                                "revision": envelope["revision"],
                                "assignment_generation":
                                    recipient["generation"]})
        if state == "acknowledged":
            return envelope
        raise AssertionError("FixtureBuilder.handoff cannot seed %r; resolving "
                             "a correction needs a QA verdict the test owns"
                             % (state,))


class RpcHarness:
    """Drives a real `RpcServer` over a pipe pair, from the client side.

    The server runs on its own thread with genuine file objects, so the
    ordering the tests assert is the ordering the transport actually produces.
    A client reader thread parks every inbound message in a queue, because an
    `elicitation/create` server request arrives while the `tools/call` that
    caused it is still unanswered.
    """

    def __init__(self, service, elicitor=None, **kwargs):
        import queue as queue_module
        import threading

        from cabinet_runtime.rpc import RpcServer

        self._to_server = os.pipe()
        self._from_server = os.pipe()
        self._server_in = open(self._to_server[0], "rb", buffering=0)
        self._server_out = open(self._from_server[1], "wb", buffering=0)
        self._client_out = open(self._to_server[1], "wb", buffering=0)
        self._client_in = open(self._from_server[0], "rb", buffering=0)
        self.inbox = queue_module.Queue()
        self.held = []
        self.server = RpcServer(self._server_in, self._server_out, service,
                                elicitor, **kwargs)
        self._serve = threading.Thread(target=self.server.serve, daemon=True)
        self._receive = threading.Thread(target=self._read_forever, daemon=True)
        self._next_id = 0

    # --- lifecycle ---------------------------------------------------------

    def start(self):
        self._serve.start()
        self._receive.start()
        return self

    def close(self):
        """Shut down the way a client does: close the write end, then wait.

        Order matters. Closing the server's own reader underneath a parked
        `readline` is a torn-down file, not a disconnect; closing the client's
        write end gives the server a genuine end of stream and lets `serve`
        return on its own.
        """

        try:
            self._client_out.close()
        except OSError:
            pass
        self._serve.join(timeout=3)
        self.server.stop()
        for stream in (self._server_out, self._server_in, self._client_in):
            try:
                stream.close()
            except OSError:
                pass
        self._receive.join(timeout=3)

    def _read_forever(self):
        import json as json_module

        while True:
            try:
                line = self._client_in.readline()
            except (ValueError, OSError):
                return                     # the harness closed underneath us
            if not line:
                return
            try:
                self.inbox.put(json_module.loads(line.decode("utf-8")))
            except ValueError:
                self.inbox.put({"__unparsed__": line.decode("utf-8", "replace")})

    # --- sending -----------------------------------------------------------

    def send(self, message):
        import json as json_module

        self.send_raw((json_module.dumps(message) + "\n").encode("utf-8"))

    def send_raw(self, data):
        self._client_out.write(data)
        self._client_out.flush()

    def request(self, method, params=None, message_id=None):
        """Send a client request and return the id it was sent under."""

        if message_id is None:
            self._next_id += 1
            message_id = self._next_id
        body = {"jsonrpc": "2.0", "id": message_id, "method": method}
        if params is not None:
            body["params"] = params
        self.send(body)
        return message_id

    # --- receiving ---------------------------------------------------------

    def take(self, match, timeout=10.0):
        """Return the first inbound message satisfying `match`.

        Messages that do not match are held and remain available to a later
        `take`, so a test can assert ordering without losing anything.
        """

        import queue as queue_module
        import time as time_module

        for index, message in enumerate(self.held):
            if match(message):
                return self.held.pop(index)
        deadline = time_module.monotonic() + timeout
        while True:
            remaining = deadline - time_module.monotonic()
            if remaining <= 0:
                raise AssertionError("no matching message; held=%r" % (self.held,))
            try:
                message = self.inbox.get(timeout=remaining)
            except queue_module.Empty:
                raise AssertionError("no matching message; held=%r" % (self.held,))
            if match(message):
                return message
            self.held.append(message)

    def answer(self, message_id, timeout=1.0):
        """Return the response to `message_id`, or None if none has arrived."""

        try:
            return self.take(lambda m: m.get("id") == message_id
                             and "method" not in m, timeout=timeout)
        except AssertionError:
            return None

    def server_request(self, method, timeout=10.0):
        return self.take(lambda m: m.get("method") == method and "id" in m,
                         timeout=timeout)

    def respond(self, message_id, result):
        self.send({"jsonrpc": "2.0", "id": message_id, "result": result})

    # --- the handshake -----------------------------------------------------

    def initialize(self, protocol="2025-11-25", capabilities=None):
        if capabilities is None:
            capabilities = {"elicitation": {"form": {}}} \
                if protocol == "2025-11-25" else {"elicitation": {}}
        message_id = self.request("initialize", {
            "protocolVersion": protocol, "capabilities": capabilities,
            "clientInfo": {"name": "cabinet-test", "version": "1"}})
        result = self.take(lambda m: m.get("id") == message_id)
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result


# --- the GitHub provider double ---------------------------------------------

#: The synthetic base the fake hands back in a `Link` header. It is not a real
#: host: the adapter must follow the URL it was given rather than rebuild one,
#: and a fake host is how a test proves that.
FAKE_BASE = "https://api.github.com/cabinet-fake"


class FakeGithubRun:
    """Stands in for the `run` callable the GitHub adapter is built with.

    It speaks the same shape as `processes.run_argv` — argv in, a bounded
    result dictionary out — and answers as `gh api -i` does, with a header
    block, a blank line and a JSON body. Everything the adapter learns about
    the provider therefore travels the same path in tests as in production.

    Three distinctions are deliberate, because each one is a real defect this
    fake exists to catch:

    * an issue is keyed by number **and**, separately, by database ID, so an
      adapter that sends a number where an ID belongs gets a miss rather than
      a plausible answer;
    * a page that was told to fail fails on its own, leaving the pages before
      it intact, so a partial collection is observable; and
    * a write can be told to time out *after* it has already taken effect,
      which is the outcome that makes a blind retry unsafe.
    """

    def __init__(self, repo="demo/company", visibility="private"):
        self.repo = repo
        self.visibility = visibility
        self.requests = []
        self.sleeps = []
        self.issues = {}
        self.by_id = {}
        self.collections = {}
        self.failed_pages = {}
        self.assignable = set()
        self.timeout_paths = set()
        self.rate_limited = 0
        self.rate_retry_after = "1"
        #: When set, a write is recorded and answered but never applied, so the
        #: adapter's readback disagrees with what it asked for.
        self.readback_refuses = False
        #: Issue numbers whose document omits the relationship summaries, the
        #: way a pull request or an older API version does. Their edges then
        #: read as unknown rather than as none.
        self.hide_relationships = set()
        self.page_size = 100
        self._next_id = 9000

    # --- fixtures ---------------------------------------------------------

    def issue(self, number, data=None):
        """Register one issue, reachable by number and by database ID."""

        record = {"number": number, "title": "Issue %d" % number, "body": "",
                  "state": "open", "state_reason": None, "labels": [],
                  "assignees": [], "updated_at": "2026-09-09T10:00:00Z",
                  "sub_issues_summary": {"total": 0, "completed": 0,
                                         "percent_completed": 0},
                  "issue_dependencies_summary": {"blocked_by": 0,
                                                 "total_blocked_by": 0,
                                                 "blocking": 0,
                                                 "total_blocking": 0}}
        record.update(data or {})
        record.setdefault("id", self._mint_id())
        record.setdefault("node_id", "I_%d" % record["id"])
        record.setdefault("html_url", "https://github.com/%s/issues/%d"
                          % (self.repo, number))
        record.setdefault("url", "%s/repos/%s/issues/%d"
                          % (FAKE_BASE, self.repo, number))
        record.setdefault("children", [])
        record.setdefault("blocked_by", [])
        self.issues[number] = record
        self.by_id[record["id"]] = record
        return record

    def _mint_id(self):
        self._next_id += 1
        return self._next_id

    def collection(self, name, items, page_size=None):
        """Store a whole collection, chunked into pages the way gh returns them."""

        size = page_size or self.page_size
        pages = [items[start:start + size]
                 for start in range(0, max(len(items), 1), size)] or [[]]
        self.collections[name] = pages
        return pages

    def fail_page(self, collection, page):
        """Make the named one-based page of a collection return a provider error."""

        self.failed_pages.setdefault(collection, set()).add(page)

    def timeout_after_write(self, path):
        """Apply the next write to this path, then report a timeout for it."""

        self.timeout_paths.add(path)

    def rate_limit(self, times=1, retry_after="1"):
        self.rate_limited = times
        self.rate_retry_after = str(retry_after)

    def sleeper(self, seconds):
        """The adapter's injected sleeper, so a busy loop is visible as zeros."""

        self.sleeps.append(seconds)

    # --- assertions -------------------------------------------------------

    def mutations(self):
        return [row for row in self.requests if row["method"] != "GET"]

    def last_mutation(self):
        """The last captured method, path and body. Carries no credential data."""

        rows = self.mutations()
        if not rows:
            raise AssertionError("no mutation was attempted")
        row = rows[-1]
        return {"method": row["method"], "path": row["path"],
                "body": copy.deepcopy(row["body"])}

    def paths(self, method=None):
        return [row["path"] for row in self.requests
                if method is None or row["method"] == method]

    # --- the run callable -------------------------------------------------

    def __call__(self, argv, input_text=None):
        method, endpoint = _parse_gh_argv(argv)
        path, query = _split_endpoint(endpoint)
        # Captured without a leading slash, exactly as the adapter wrote it, so
        # an assertion in a test reads as the endpoint the provider documents.
        body = json.loads(input_text) if input_text else None
        self.requests.append({"method": method, "path": path, "query": query,
                              "body": copy.deepcopy(body), "argv": list(argv)})
        if self.rate_limited > 0:
            self.rate_limited -= 1
            return _response(429, {"message": "You have exceeded a secondary "
                                              "rate limit"},
                             {"Retry-After": self.rate_retry_after,
                              "X-RateLimit-Remaining": "0"})
        status, payload, headers = self._route(method, path, query, body)
        if method != "GET" and path in self.timeout_paths:
            self.timeout_paths.discard(path)
            return {"returncode": None, "stdout": "", "stderr": "",
                    "timed_out": True,
                    "classification": "timeout_after_possible_dispatch"}
        return _response(status, payload, headers)

    # --- routing ----------------------------------------------------------

    def _route(self, method, path, query, body):
        parts = path.split("/")
        if parts[:1] == ["cabinet-fake"]:
            return self._page(parts[1], int(query.get("page", "1")))
        if len(parts) == 3 and parts[0] == "repos":
            return 200, {"full_name": self.repo, "visibility": self.visibility,
                         "private": self.visibility != "public"}, {}
        if len(parts) < 4 or parts[0] != "repos":
            return 404, {"message": "Not Found"}, {}
        named = "/".join(parts[1:3])
        if named != self.repo:
            return 404, {"message": "Not Found"}, {}
        rest = parts[3:]
        if rest[0] == "assignees" and len(rest) == 2:
            return (204, None, {}) if rest[1] in self.assignable \
                else (404, {"message": "Not Found"}, {})
        if rest[0] in ("issues", "pulls", "branches") and len(rest) == 1 \
                and method == "GET":
            return self._page(rest[0], int(query.get("page", "1")))
        if rest[0] != "issues":
            return 404, {"message": "Not Found"}, {}
        return self._issue_route(method, rest, path, body)

    def _issue_route(self, method, rest, path, body):
        if len(rest) == 1:
            return self._create(body)
        try:
            number = int(rest[1])
        except ValueError:
            return 404, {"message": "Not Found"}, {}
        record = self.issues.get(number)
        if record is None:
            return 404, {"message": "Not Found"}, {}
        tail = rest[2:]
        if not tail:
            return self._issue_document(method, record, body)
        if tail[0] == "sub_issues":
            return self._sub_issues(method, record, body)
        if tail[0] == "sub_issue":
            return self._remove_child(record, body)
        if tail[:2] == ["dependencies", "blocked_by"]:
            return self._blocked_by(method, record, tail, body)
        if tail[0] == "labels":
            if not self.readback_refuses:
                record["labels"] = [{"name": name} for name in body["labels"]]
            return 200, [{"name": name} for name in body["labels"]], {}
        return 404, {"message": "Not Found"}, {}

    def _issue_document(self, method, record, body):
        if method == "GET" or self.readback_refuses:
            return 200, self._render(record), {}
        for field in ("title", "body", "state", "state_reason"):
            if body and field in body:
                record[field] = body[field]
        if body and "labels" in body:
            record["labels"] = [{"name": name} for name in body["labels"]]
        if body and "assignees" in body:
            record["assignees"] = [{"login": name} for name in body["assignees"]]
        return 200, self._render(record), {}

    def _create(self, body):
        number = max(self.issues) + 1 if self.issues else 1
        record = self.issue(number, {
            "title": body.get("title", ""), "body": body.get("body", ""),
            "labels": [{"name": name} for name in body.get("labels", [])],
            "assignees": [{"login": name}
                          for name in body.get("assignees", [])]})
        return 201, self._render(record), {}

    def _sub_issues(self, method, record, body):
        if method == "GET":
            if 1 in self.failed_pages.get("sub_issues", ()):
                return 500, {"message": "Server Error"}, {}
            return 200, [self._render(self.issues[n])
                         for n in record["children"]], {}
        child = self.by_id.get(body["sub_issue_id"])
        if child is None:
            return 422, {"message": "sub_issue_id is not an issue"}, {}
        if child["number"] not in record["children"]:
            record["children"].append(child["number"])
        child["parent"] = record["number"]
        return 201, self._render(record), {}

    def _remove_child(self, record, body):
        child = self.by_id.get(body["sub_issue_id"])
        if child is None or child["number"] not in record["children"]:
            return 404, {"message": "Not Found"}, {}
        record["children"].remove(child["number"])
        child.pop("parent", None)
        return 200, self._render(record), {}

    def _blocked_by(self, method, record, tail, body):
        if method == "GET":
            if 1 in self.failed_pages.get("blocked_by", ()):
                return 500, {"message": "Server Error"}, {}
            return 200, [self._render(self.issues[n])
                         for n in record["blocked_by"]], {}
        if method == "DELETE":
            blocker = self.by_id.get(int(tail[2]))
            if blocker is None or blocker["number"] not in record["blocked_by"]:
                return 404, {"message": "Not Found"}, {}
            record["blocked_by"].remove(blocker["number"])
            return 204, None, {}
        blocker = self.by_id.get(body["issue_id"])
        if blocker is None:
            return 422, {"message": "issue_id is not an issue"}, {}
        if blocker["number"] not in record["blocked_by"]:
            record["blocked_by"].append(blocker["number"])
        return 201, self._render(record), {}

    def _page(self, collection, page):
        pages = self.collections.get(collection)
        if pages is None:
            return 200, [], {}
        if page in self.failed_pages.get(collection, ()):
            return 500, {"message": "Server Error"}, {}
        if page < 1 or page > len(pages):
            return 200, [], {}
        headers = {}
        if page < len(pages):
            headers["Link"] = '<%s/%s?page=%d>; rel="next"' % (
                FAKE_BASE, collection, page + 1)
        return 200, pages[page - 1], headers

    def _render(self, record):
        shown = {key: value for key, value in record.items()
                 if key not in ("children", "blocked_by", "parent")}
        if record["number"] in self.hide_relationships:
            shown.pop("sub_issues_summary", None)
            shown.pop("issue_dependencies_summary", None)
            return shown
        summary = dict(shown.get("sub_issues_summary") or {})
        summary["total"] = len(record["children"])
        shown["sub_issues_summary"] = summary
        dependencies = dict(shown.get("issue_dependencies_summary") or {})
        dependencies["total_blocked_by"] = len(record["blocked_by"])
        dependencies["blocked_by"] = len(
            [n for n in record["blocked_by"]
             if self.issues[n]["state"] == "open"])
        shown["issue_dependencies_summary"] = dependencies
        if record.get("parent") is not None:
            shown["parent_issue_url"] = "%s/repos/%s/issues/%d" % (
                FAKE_BASE, self.repo, record["parent"])
        return shown


def _parse_gh_argv(argv):
    """Recover the method and endpoint from a `gh api` command line."""

    method, endpoint, index = "GET", None, 0
    while index < len(argv):
        word = argv[index]
        if word == "--method":
            method, index = argv[index + 1], index + 2
        elif word in ("-H", "--header", "--input"):
            index += 2
        elif word in ("gh", "api"):
            index += 1
        elif word.startswith("-"):
            index += 1
        else:
            endpoint, index = word, index + 1
    return method, endpoint


def _split_endpoint(endpoint):
    """Split `path?query` — a full URL included — into a path and a mapping."""

    text = endpoint or ""
    for prefix in ("https://api.github.com/", "http://api.github.com/"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    path, _, raw = text.partition("?")
    query = {}
    for pair in raw.split("&"):
        if not pair:
            continue
        name, _, value = pair.partition("=")
        query[name] = unquote(value)
    return path.strip("/"), query


def _response(status, payload, headers=None):
    """Render one `gh api -i` result: header block, blank line, JSON body."""

    reasons = {200: "OK", 201: "Created", 204: "No Content", 401: "Unauthorized",
               403: "Forbidden", 404: "Not Found", 422: "Unprocessable Entity",
               429: "Too Many Requests", 500: "Internal Server Error"}
    lines = ["HTTP/2.0 %d %s" % (status, reasons.get(status, "Unknown"))]
    lines.append("Content-Type: application/json; charset=utf-8")
    lines.append("X-Github-Api-Version-Selected: 2026-03-10")
    for name, value in (headers or {}).items():
        lines.append("%s: %s" % (name, value))
    body = "" if payload is None else json.dumps(payload)
    stdout = "\r\n".join(lines) + "\r\n\r\n" + body
    stderr = "" if status < 400 else "gh: HTTP %d\n" % status
    return {"returncode": 0 if status < 400 else 1, "stdout": stdout,
            "stderr": stderr, "timed_out": False, "classification": "completed"}
