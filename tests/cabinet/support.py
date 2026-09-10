"""Shared test fixtures for the Cabinet runtime suites.

Repository-only module (see AGENTS.md: `tests/` is not shipped). Nothing here
is imported by production code or exposed by the service. Standard library
only, so the suite runs with the interpreter already on the machine.

Import as `from support import batch, action, FakeClock` with
`PYTHONPATH=plugins/cabinet/scripts:tests/cabinet`.
"""

import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path

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
                profiles=None, workers=1):
    """The setup scope the owner is asked to approve in the setup dialog."""

    if profiles is None:
        profiles = ["local-unit"]
    return {
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
                                "result": "sent"})
        if state == "sent":
            return envelope
        service.update_handoff(handoff_id, "acknowledged",
                               {"native_sender": envelope["to_role"]})
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
