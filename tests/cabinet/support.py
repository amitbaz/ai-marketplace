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
