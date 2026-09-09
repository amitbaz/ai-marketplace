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
    """An elicitor whose dialog never returns: timeout, closed session, refusal."""

    def __init__(self, error):
        self.error = error
        self.requests = []

    def request(self, message, schema):
        self.requests.append((message, copy.deepcopy(schema)))
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


def setup_scope(repo="demo/company", visibility="private", operations=None):
    """The setup scope the owner is asked to approve in the setup dialog."""

    return {
        "repo": repo,
        "visibility": visibility,
        "board_operations": list(operations if operations is not None else (
            "github.create_issue", "github.update_issue", "github.set_labels",
            "github.set_assignees", "github.set_parent", "github.remove_parent",
            "github.add_blocker", "github.remove_blocker", "github.set_state")),
        "check_profiles": [{"profile_id": "local-unit",
                            "argv": ["python3", "-m", "unittest"],
                            "env": {"PYTHONHASHSEED": "0"}}],
        "capacity": {"implementation_workers": 1},
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
