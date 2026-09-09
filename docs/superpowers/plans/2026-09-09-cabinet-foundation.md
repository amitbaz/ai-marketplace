# Cabinet Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use subagent-driven-development only with owner-authorized delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a verified native capability boundary, durable company state and human-controlled action authority.

**Architecture:** A standard-library stdio service serializes company mutations through SQLite, exposes typed operations, and obtains revision-bound consent through the Claude client. Restricted profiles prevent ordinary roles from bypassing its action surface.

**Tech Stack:** Python 3 standard library, SQLite, MCP stdio, Claude Code, unittest.

**Spec:** [Company design](../specs/2026-09-09-cabinet-company-design.md), [master plan](2026-09-09-cabinet-ai-company.md), [contracts](2026-09-09-cabinet-contracts.md).

## Global Constraints

- "Development targets Claude Code only. Superset remains the owner's IDE."
- "Goal approval authorizes preparation, not implementation."
- "Agent messages and ticket content cannot supply owner consent."
- "Plugin mechanisms must retain the repository's no-build, standard-library/POSIX constraints."
- This part alone is foundation completion, never operational Cabinet completion.

## F1: Pin the live capability contract and preserve the product target

**Files:** Create `docs/cabinet/acceptance/environment.md` and
`tests/cabinet/test_distribution.py`; update the execution ledger. No production
runtime is implemented in this task.

**Interfaces:** Consumes the installed CLI/tool schemas. Produces a capability
record with `supported`, `unsupported`, or `not_run` per capability, version,
probe and evidence. Later tasks consume that record, not guessed native fields.

- [ ] Record baseline commit, clean/dirty state, repository instructions and the
  current manifest drift described in the master. Inspect any intervening commits.
- [ ] Run these read-only probes. A missing Superset CLI is an explicit prerequisite,
  not a reason to drop automated workspaces from the delivery.

```sh
claude --version
claude --help
superset --version
superset workspaces create --help
superset terminals create --help
superset terminals list --help
superset terminals read --help
superset terminals close --help
superset auth whoami --json
gh --version
```

Use the repository-required `rtk` prefix on this machine. `rtk` is developer
tooling and must not become a plugin prerequisite. Do not install or upgrade
tools without the owner's instruction. Do not copy auth output into evidence.

- [ ] In a synthetic directory, inspect actual interactive Claude tool schemas
  for Agent, SendMessage and ListAgents. Verify a named read-only teammate can
  receive a question and reply without the owner copying messages. Record the
  exact tool field names that this installed version supplies. Do not invent
  `TeamCreate`, `TeamDelete`, or private socket protocols.
- [ ] Confirm independent sessions advertise native messaging and can wake an
  idle recipient. Verify the provider supports it; a version number alone does
  not prove availability. Native docs currently describe cross-session messaging
  at v2.1.224+, one-shot idle notifications at v2.1.236+, and restricted mode is
  present in this machine's 2.1.267 help. Require the actual capabilities rather
  than treating a version floor as sufficient.
- [ ] Inspect effective settings and test a harmless restricted session: no
  shell/browser/broad MCP tools for a staff role; no fabricated response to an
  owner dialog. Record unsupported features as blockers for their dependent task.
  Native probes that consume inference require implementation authorization;
  this planning session has deliberately not run them.
- [ ] Add a structural test exposing the existing Cabinet drift:

```python
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class ManifestContract(unittest.TestCase):
    def test_cabinet_table_matches_manifest(self):
        manifest = json.loads((ROOT / "plugins/cabinet/.claude-plugin/plugin.json").read_text())
        row = next(line for line in (ROOT / "README.md").read_text().splitlines()
                   if line.startswith("| [cabinet]"))
        version = row.split("|")[2].strip()
        self.assertEqual(version, manifest["version"])
```

- [ ] Run `python3 -m unittest discover -s tests/cabinet -p test_distribution.py -v`.
  At the inspected baseline, expect a 0.5.0 versus 0.8.0 failure. Correct only
  the factual root version row to 0.8.0, rerun, and retain the broader packaging
  work for A3. If a later commit already fixed it, record that and keep the test.
- [ ] Commit: `test(cabinet): establish capability and distribution baseline`.
  Update F1 and native probe statuses separately in the ledger.

## F2: Transactional company state and stable revisions

**Files:** Create `plugins/cabinet/scripts/cabinet_runtime/{__init__,errors,contracts,store,migration,exports}.py`,
`tests/cabinet/support.py`, `tests/cabinet/test_store.py` and synthetic fixtures.

**Interfaces:** `Store(root, clock)` provides `open()`, `append_event(kind,
entity_id, revision, payload)`, `propose_batch(body)`, `get_batch(id, revision)`,
`get_events(after_seq)`, `prepare_action(envelope)`, `acquire_lease(session_id,
pid, process_start)`, `pause(reason)`, `backup(destination)`, and
`export_company()`. All return JSON-compatible dictionaries. `clock()` returns
UTC ISO text; production supplies a real clock, tests supply a fixed one.
Errors are `CabinetError(code, message)` with `.code` for assertions.

- [ ] Create common fixtures in `support.py`; use them in every later test:

```python
import copy

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
```

- [ ] Write tests before implementation, including a restart and conflicting retry:

```python
import tempfile
import unittest
from pathlib import Path
from cabinet_runtime.store import Store
from cabinet_runtime.errors import CabinetError
from support import batch, action, FakeClock

class StateContract(unittest.TestCase):
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
```

- [ ] Run with `PYTHONPATH=plugins/cabinet/scripts:tests/cabinet python3 -m unittest discover -s tests/cabinet -p test_store.py -v`;
  initially expect missing module/function failures.
- [ ] Implement schema and invariants in the contracts. Canonical hash:

```python
import hashlib
import json

def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
```

Use bound SQL parameters and `BEGIN IMMEDIATE` for mutations. Commit event and
projection together, return only after commit. Add triggers rejecting event
UPDATE/DELETE; use new compensating events to supersede state. Lease acquisition
checks process identity, not only PID (PID reuse is possible); a live conflicting
lead produces LEAD_ACTIVE. An expired heartbeat alone does not authorize duplicate
lead ownership. Fencing generation is checked by every mutation.

- [ ] Add fault-injection tests: exception between event/projection writes rolls
  both back; process termination after commit retains both; sequence cursors do
  not depend on timestamps; two concurrent claims yield one assignment; a new
  schema is rejected; canonical slug collision and private-path symlink fail.
- [ ] Implement non-destructive migration: snapshot legacy documents with hashes,
  verify their repo identity, import them as source-tagged document revisions,
  preserve original files and decision numbers, and export views atomically using
  temporary file + `os.replace`. Re-running identical migration is a no-op.
  Never translate legacy notebook inbound text into approved execution.
- [ ] Test backup via SQLite backup API with a write occurring concurrently;
  restored DB must pass `PRAGMA integrity_check` and match the recorded snapshot
  sequence. Restoration goes to a new directory, not over active company state.
- [ ] Rerun the store suite and commit: `feat(cabinet): persist company state and revisions`.

## F3: Owner approval and named action authority

**Files:** Create `approval.py`, `policy.py`, `tests/cabinet/test_approval.py`,
`tests/cabinet/test_policy.py`; extend `store.py` and `contracts.py`.

**Interfaces:** `ApprovalService(store, elicitor).request(batch_id, revision)`;
`Policy(store).authorize(action)` returns the applicable setup/batch grant or
raises CabinetError. Store exposes `save_grant(pending_request_id, response)`
internally; it is never an MCP tool. ApprovalService owns pending request IDs.

- [ ] Write tests using actual client-response shapes:

```python
from cabinet_runtime.approval import ApprovalService
from cabinet_runtime.policy import Policy
from cabinet_runtime.errors import CabinetError
from support import FakeElicitor

# In a unittest fixture whose self.store contains batch() and an active lease:
def test_decline_never_authorizes(self):
    ApprovalService(self.store, FakeElicitor({"action":"decline"})).request("B001", 1)
    with self.assertRaises(CabinetError) as caught:
        Policy(self.store).authorize(action())
    self.assertEqual(caught.exception.code, "BATCH_NOT_APPROVED")

def test_exact_human_acceptance_authorizes(self):
    ui = FakeElicitor({"action":"accept", "content":{"approve":True}})
    ApprovalService(self.store, ui).request("B001", 1)
    self.assertEqual(Policy(self.store).authorize(action())["revision"], 1)

def test_money_has_no_executor(self):
    item = action()
    item["kind"] = "finance.purchase"
    with self.assertRaises(CabinetError) as caught:
        Policy(self.store).authorize(item)
    self.assertEqual(caught.exception.code, "OPERATION_FORBIDDEN")
```

Create the fixture with a TemporaryDirectory, Store.open, propose_batch and
acquire_lease using the current process identity. No fixture inserts a production
grant directly; synthetic acceptance flows through FakeElicitor.

- [ ] Run both test files red; implement the dialog text from stored business
  outcome/scope/exclusions, never mutable model-provided approval copy. The schema:

```json
{"type":"object","properties":{"approve":{"type":"boolean","title":"Approve this exact work batch"}},"required":["approve"]}
```

Keep the batch digest before the dialog, reacquire the transaction afterwards,
and reject if scope, lease or pause state changed during the wait. Preserve the
response and exact approved revision. `accept` without `approve:true` is not yes.

- [ ] Implement setup grants for the exact repo, routine board operations, local
  test profiles and chosen concurrency. The one-time setup dialog distinguishes
  account login from authority to modify the board. Draft charter approval and
  company-direction amendments are explicit owner decisions, never staff edits.
- [ ] Test: old revision, no approval, cancelled/timed-out dialog, forged
  `approved:true`, forged owner message, superseded grant, paused lease, other
  repository, arbitrary URL, arbitrary shell command, protected branch push,
  external comment and release all fail before adapter invocation. A normal
  setup-authorized issue-label edit succeeds without a new dialog.
- [ ] Commit: `feat(cabinet): enforce batch approval and scoped actions`.

## F4: Bounded MCP service and restricted launch profiles

**Files:** Create `rpc.py`, `service.py`, `profiles.py`, `processes.py`,
`plugins/cabinet/scripts/cabinet-service`, `cabinet-launch`, `.mcp.json`,
`tests/cabinet/test_rpc.py`, `test_profiles.py`, `agents/chief-of-staff.md`,
`scripts/cabinet-hook` and `hooks/hooks.json`. O1 expands the chief's operating
remit; A1 expands the hook's lifecycle behavior.

**Interfaces:** `RpcServer(reader, writer, service, elicitor)` implements only
initialize, initialized notification, ping, tools/list, tools/call, cancellation
and matching server-request responses. `serve()` reads newline-delimited JSON.
`StdioElicitor.request(message, schema)` implements the F3 elicitor interface.
`build_profile`, `verify_profile`, `worker_launch` follow the contracts.

- [ ] Write a protocol transcript test. Send initialize, initialized, tools/list
  and a request_owner_approval tool call. Assert an elicitation/create server
  request is emitted, send its correlated client response, and assert only then
  that the original tools/call response carries the grant. Test decline and
  mismatched IDs. Replayed responses create no extra grants.

```python
request = {"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{
    "protocolVersion":"2025-11-25", "capabilities":{"elicitation":{"form":{}}},
    "clientInfo":{"name":"cabinet-test", "version":"1"}}}
expected_request = {"method":"elicitation/create", "params":{
    "mode":"form", "message":"stored approval summary",
    "requestedSchema":{"type":"object","properties":{
        "approve":{"type":"boolean"}},"required":["approve"]}}}
```

- [ ] Run RPC/profile suites red. Implement version negotiation for 2025-11-25
  and 2025-06-18, using each version's elicitation schema. Refuse approval when
  the client lacks form elicitation. Do not use draft MCP proposals as a released
  protocol. Declare tools capability; never request model sampling.
- [ ] Keep protocol I/O independent of blocking action work: one reader dispatches
  responses to pending request IDs, one serialized writer emits JSON, a bounded
  worker thread handles tools/call. Otherwise an approval call can deadlock while
  waiting for the reader that is executing it. Bound message size to 1 MiB, reject
  malformed JSON with -32700, unknown methods -32601 and invalid params -32602.
  Domain errors return MCP tool errors with stable Cabinet error codes.
- [ ] Wire the stdio entrypoint without dependencies:

```json
{"mcpServers":{"cabinet":{"command":"python3","args":["${CLAUDE_PLUGIN_ROOT}/scripts/cabinet-service"]}}}
```

The ordinary plugin connection exposes diagnosis/context. `cabinet-launch`
creates a private profile and process capability, then starts the restricted
chief with an explicit service connection. No capability appears in a prompt,
tool result, command transcript, repository file, or exported company view.

- [ ] Create the initial chief definition before its F4 launch smoke. It contains
  the enumerated native/service tools and a foundation-only instruction to run
  the requested synthetic diagnosis/approval scenario. It must not dispatch
  business work. O1 replaces this temporary instruction with the full shared
  workflow. This avoids a dependency on a role file not created until O1.
- [ ] Build launch argv with verified flags from F1:

```python
argv = [claude_path, "--restricted", "--strict-mcp-config",
        "--mcp-config", mcp_config_path, "--settings", profile_path,
        "--plugin-dir", plugin_root, "--agent", "cabinet:chief-of-staff",
        "--add-dir", public_views_path, "--add-dir", plugin_root,
        "--tools", "Read,Grep,Glob,Skill,Agent,SendMessage,ListAgents",
        "--session-id", session_id]
```

Task tools are added only if F1 verified them. `.mcp.json` duplicate loading,
effective plugin hooks and strict-mode interactions must be checked live. If the
current installed CLI differs, adapt the argv to observed documentation and
record it; retain the tool/permission outcome.

- [ ] Test exact staff tool sets and negative worker profiles. Staff profiles
  cannot enable Bash/Edit/Write/browser/billing tools; worker profiles cannot
  expose the action service or credential directories. Inspect effective managed
  settings; deny unknown Elicitation/ElicitationResult hooks or policy widening.
  Mandatory worker sandbox: enabled, failIfUnavailable, no unsandboxed commands,
  no excluded commands, filesystem isolation on, no external egress. Use absolute
  paths resolved from the trusted worktree/toolchain; never interpolate ticket
  strings into settings paths or shell commands.
- [ ] Add the Agent-type registry check described in the contracts to
  `cabinet-hook`/`hooks/hooks.json` now; A1 later adds lifecycle behavior. Deny
  unknown/general-purpose child types before dispatch and verify actual inherited
  tools in a native probe. A child must not recover a shell the parent lacks.
  Check SendMessage recipient membership too. Public views and skill references
  are readable; private runtime state is not. Worker profiles explicitly deny
  edits to plugin files and public context even when included as readable dirs.
- [ ] Test a fake subprocess adapter captures argv as a list with `shell=False`,
  redacts environment secrets, bounds output/timeouts, and turns a timeout after
  possible external dispatch into UNCERTAIN rather than automatic retry.
- [ ] Run unit suites, then the actual Claude MCP initialize/list/call and owner
  dialog smoke. The human acceptance probe needs one real owner response; this
  is an approval mechanism test, not a business batch approval. Record that scope.
- [ ] Commit: `feat(cabinet): expose scoped runtime tools and restricted launch`.

## Sources checked during planning

- [Claude agent teams](https://code.claude.com/docs/en/agent-teams): role reuse and
  direct messaging exist; teammate recovery remains Cabinet's responsibility.
- [Cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging):
  native discovery/message delivery and idle notices; observe actual availability.
- [Claude MCP](https://code.claude.com/docs/en/mcp) and
  [MCP elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation):
  correlated client input; audit hooks that could synthesize that input.
- [Sandboxing](https://code.claude.com/docs/en/sandboxing) and
  [permissions](https://code.claude.com/docs/en/permissions): independent tool,
  filesystem and network controls, with documented security limits.

After F4, continue to O1. A state service with passing unit tests is not the
operating company and must not be presented as the completed request.
