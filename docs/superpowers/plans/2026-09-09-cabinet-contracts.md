# Cabinet runtime contracts

Companion to [the master plan](2026-09-09-cabinet-ai-company.md). These are proposed
interfaces to implement, not APIs already present. All task examples refer to
these names. Python implementations use standard-library modules only.

## File ownership and layout

```text
plugins/cabinet/
  .claude-plugin/plugin.json        Claude manifest, 1.0.0 at final acceptance
  .mcp.json                       stdio server declaration
  agents/
    chief-of-staff.md              restricted interactive lead
    product.md                    outcome and customer evidence
    delivery-lead.md               board and batch ownership
    engineering.md                implementation coordination
    qa.md                         independent verification verdict
    implementer.md                isolated editing worker
    test-runner.md                isolated test execution worker
    architect.md                  compatibility/deep architecture specialist
    design.md                     on-demand user experience specialist
    marketing.md                  on-demand growth specialist
    brand.md, cfo.md, counsel.md   retained on-demand specialists
  skills/coordination-rules/SKILL.md   single workflow entrypoint
  skills/coordination-rules/references/
    company.md                    role authority and decision routing
    batch.md                      proposal through completion
    communication.md              actionable message lifecycle
    recovery.md                   resume/reconcile/pause/close
    briefing.md                   owner-facing copy and examples
  commands/
    company.md, batch.md, status.md, pause.md, close.md
    hire.md, standup.md, decide.md, brief.md, check.md
    ask.md, review.md, charter.md, help.md
  scripts/
    cabinet-launch                Python launcher; no workflow prose
    cabinet-service               Python stdio service entrypoint
    cabinet_runtime/
      __init__.py, errors.py, contracts.py, store.py, approval.py
      policy.py, rpc.py, service.py, github.py, superset.py
      processes.py, profiles.py, migration.py, exports.py
    memory-path, board-snapshot, charter-sources  compatible legacy wrappers
  hooks/hooks.json                lifecycle reminders, never source of authority
  scripts/cabinet-hook             bounded lifecycle event sender
  README.md, FILES.md
scripts/check-cabinet.py            repository-only structural checks
tests/cabinet/
  support.py, test_store.py, test_approval.py, test_policy.py, test_rpc.py
  test_github.py, test_superset.py, test_profiles.py, test_handoffs.py
  test_recovery.py, test_exports.py, test_distribution.py, test_verification.py
  fixtures/                        synthetic API/protocol/recovery scenarios
docs/cabinet/acceptance/            sanitized live evidence and review verdicts
```

Only repository checks/tests may contain fixture workflow prose. Plugin scripts
contain mechanism and tool/schema descriptions, never repeat the skill's rules.
New skill reference files belong beside the canonical skill, not in adapters.

## Process boundary

The service is a trusted local action executor. The model does not receive raw
shell, HTTP, SQL, file-write, or token retrieval methods through it. All service
inputs use strict field validation and reject unknown fields. `shell=False` for
subprocess calls; URLs and command argv are assembled from enumerated operations.

One lead holds the company lease. SQLite serializes writes even if more than one
MCP connection exists. A connection that does not hold the lease is read-only
until its explicit takeover succeeds. The private runtime directory is not an
agent-readable working directory. Human-readable exports are a separate view.

Native staff can read repository evidence and public company views, and exchange
native messages. Only the chief's tool allowlist contains service mutation tools.
This is a change from prose-only command writes to a single typed writer; agents
do not gain general file-write authority. Workers cannot use the service's
GitHub or approval tools and cannot read its storage or credentials.

Treat labels like `from_role` in a message as claims checked against the current
registered native sender/session. They are not security credentials. The service
enforces capabilities by exposed operations, lease, approved scope and persisted
state; it never accepts a message string as an owner grant.

## Runtime storage

```text
~/.cabinet/founder.md
~/.cabinet/repos/<owner>-<repo>/       existing Markdown retained initially
  company.md, decisions.md, money.md, proposals.md, <role>.md
  runtime/
    identity.json                    immutable github.com/owner/repo binding
    cabinet.sqlite3                  source of events and transactional state
    profiles/                        generated restricted launch profiles
    backups/                         SQLite backup + document copies + hashes
  views/
    company-context.md               source-tagged charter/goals/authority
    current-batch.md, handoffs.md, latest-brief.md, departments.md
```

Validate the exact canonical repository against `identity.json` and the legacy
charter before opening state. Old hyphenated slugs can collide: `a-b/c` and
`a/b-c` must never share records. Report IDENTITY_CONFLICT instead of adopting
unknown state. An explicit migration can later move to host/owner/repo nesting;
this release need not rename compatible existing paths.

Directory mode 0700; private files 0600; reject traversal, symlinked private
directories and paths outside the resolved company directory. Never print
tokens or persist raw environment variables. Views contain only selected
company context, not private profiles, approval internals or credentials.

Use `sqlite3.connect`, `PRAGMA foreign_keys=ON`, `journal_mode=WAL`,
`synchronous=FULL`, `busy_timeout=5000`. Every transition and its event commit in
one transaction. Use `Connection.backup` rather than copying an open WAL file.
Schema version 1 is created transactionally; a newer unknown version opens
read-only with SCHEMA_TOO_NEW. Update/delete triggers protect event rows from
ordinary service operations; this does not resist a malicious host owner.

Tables:

| Table | Key / uniqueness | Essential columns |
| --- | --- | --- |
| events | seq INTEGER PRIMARY KEY; event_id UNIQUE | kind, entity_id, revision, time, payload_json |
| batches | (batch_id, revision) | body_json, digest, state, created_seq |
| grants | grant_id; (batch_id, revision, digest) | owner_response_json, revoked_seq, approved_seq |
| handoffs | handoff_id | batch_id, revision, from_role, to_role, body_json, digest, state, attempts, next_retry_at |
| actions | action_id; idempotency_key UNIQUE | kind, payload_json, digest, state, external_ref_json, evidence_json |
| assignments | assignment_id; active work ownership constraint | batch_id, revision, role, issue_number, workspace_id, terminal_id, native_session_id, generation, state |
| verdicts | (assignment_id, revision_sha, reviewer_role) | outcome, evidence_json, time |
| lease | singleton key 1 | session_id, pid, process_start, generation, last_seen, paused |
| documents | (name, revision) | content, digest, source_json, supersedes |

Live source data is an observation with a timestamp. Never treat a persisted
check verdict or issue status as current without matching its source revision.

## JSON objects

Batch body, frozen by canonical JSON hash:

```json
{
  "batch_id": "B001", "revision": 1, "repo": "owner/repo",
  "goal": "Let invited people use separate accounts",
  "outcome": "An invited user can enter and see only their own information",
  "in_scope": ["Invitation entry", "Account separation verification"],
  "out_of_scope": ["Public signup", "Payments"],
  "acceptance": [{"id":"AC1","behavior":"An uninvited person cannot enter"}],
  "issues": [12, 14], "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "owned_paths": ["apps/example/"], "check_profile_ids": ["local-unit"],
  "risks": ["Invitation flow may expose an existing isolation bug"],
  "capacity": {"implementation_workers": 1},
  "release_policy": "owner_approval", "external_publication": false
}
```

Validate SHA as 40 lowercase hex characters and resolve it against the actual
repository before execution. The synthetic example uses `"a" * 40`.
Scope paths are repository-relative, normalized and symlink-checked. Check
profiles are separately setup-approved immutable argv/environment/isolation
records, not arbitrary commands embedded in tickets. A capacity change is an
explicit owner preference; models and reasoning settings inherit user choices.

Handoff envelope:

```json
{
  "handoff_id":"H001", "batch_id":"B001", "revision":1,
  "from_role":"qa", "to_role":"engineering", "kind":"correction",
  "question":"The uninvited account entered; correct AC1",
  "evidence":[{"ref":"artifact:E001","sha256":"64-hex-digest"}],
  "reply_to":"H001", "expected_response":"Correction SHA and verification evidence"
}
```

Action envelope:

```json
{
  "action_id":"A001", "idempotency_key":"B001:r1:issue14:add-blocker12",
  "kind":"github.add_blocker", "batch_id":"B001", "revision":1,
  "expected_before":{"issue_updated_at":"source timestamp"},
  "payload":{"issue_number":14,"blocker_number":12}
}
```

`idempotency_key` reused with different canonical payload raises
IDEMPOTENCY_CONFLICT. External identifiers come from verified provider results.
Never map a Cabinet role name to a fictitious GitHub username.

## State transitions

Batch: `proposed → approved → running → verifying → ready_for_release`.
Any active batch can become `paused` or `blocked`; resume returns to its stored
prior state after reconciliation. `completed` means the approved development
outcome was verified, with a separate `released=false` fact until owner-reported
release evidence exists. A batch need not be released to finish its approved
development scope. `superseded` preserves the old revision and revokes its grant.

Transition guards: first authorized dispatch moves approved to running; a
reported candidate with collected check artifacts moves running to verifying.
A QA failure returns verifying to running for an in-scope correction. All ACs
must have matching QA passes at the integrated SHA, with no unresolved required
handoffs or live implementation assignments, before ready_for_release. The
chief's batch-end checkpoint then records completed development with
released=false. A request to complete earlier raises ACCEPTANCE_INCOMPLETE.
Release evidence is recorded separately from this development state machine.

Handoff: `recorded → sent → acknowledged → resolved`; alternate terminal states
`failed` and `superseded`. `sent` records a successful transport result;
`acknowledged` requires the recipient's own reply, not the sender's guess.
Answering a question can resolve a clarification; correcting a defect requires
QA acceptance of the correction evidence before resolving its handoff.

Action: `prepared → running → verified`; ambiguous provider outcomes become
`uncertain` and require readback before retry. `blocked` and `failed` are distinct.
Never hold a SQL write transaction while waiting on a network response.

Assignment: `reserved → starting → running → reported → verified`; failure paths
`blocked`, `lost`, `cancel_requested`, `cancelled`. A terminal existing or going
idle is never proof of completion. At most one live assignment owns a given
work item/path set; conflicting assignments wait rather than race.

## Service methods

Define these Python methods on `CabinetService(store, github, superset, clock,
elicitor, profile_builder)`; inputs/returns are JSON-compatible dictionaries.
Adapters are injected and replaced with deterministic fakes in unit tests.

```python
snapshot()                              # company/batch/events with freshness
propose_batch(body)                      # frozen revision and digest
request_owner_approval(batch_id, revision) # dialog -> grant or declined/cancelled
record_handoff(envelope)                 # ID/state/digest; durable before send
update_handoff(handoff_id, transition, evidence)
prepare_action(envelope)                 # validate scope; persist intent
execute_action(action_id)                # scoped adapter -> readback/result
register_session(assignment_id, registration)
record_verdict(assignment_id, revision_sha, reviewer_role, outcome, evidence)
pause(reason)                           # fence new actions before messaging workers
reconcile(observations)                  # live adapter checks + proposed recovery
checkpoint(kind, summary)                # session_open/session_close/batch_end
export_company()                        # atomic human-readable views
backup()                                # consistent snapshot and manifest
```

Expose each as `cabinet_<method>` in server `cabinet`; Claude names them
`mcp__cabinet__cabinet_<method>`. `reconcile` accepts only observations collected
by the trusted adapters or transport receipts verified by the chief, not a
caller-provided declaration that a worker is safe to repeat. O2 specifies the
native transport receipt path. Actions are still subject to F3 policy.

Additional setup operations: `cabinet_doctor` (read-only), `cabinet_setup`
(interactive config/charter confirmation), `cabinet_acquire_lead`
(generation/lease acquisition), `cabinet_context` (bounded role context read).
Expose reads in ordinary sessions for diagnosis; mutation requires the verified
restricted chief launch and active lease. Do not pretend a slash command can
retroactively remove tools from a broad existing session.

MCP startup context carries absolute company identity and launch profile paths
from the launcher, not from model-provided tool arguments. A per-launch random
capability is exchanged privately between launcher and service and omitted from
tool output. For an ordinary plugin-loaded service without that context,
mutation returns RESTRICTED_SESSION_REQUIRED. Capabilities bind host process,
company, profile digest and generation; renewal occurs only via verified launch.

`prepare_action` validates identity, shape and known operation type and records
intent; it may prepare an action before approval. `execute_action` enforces the
current grant, scope, lease and pause state immediately before an external
operation. Preparing something is never permission to execute it.

## Adapter interfaces

```python
# github.py
GithubAdapter(run, repo, api_version="2026-03-10")
read_board()                       # fully paginated; snapshot + missing fields
read_issue(number)                 # id != number; parent and blockers included
apply(operation, payload)          # named operation only
reconcile_action(action)           # zero/one/multiple match, before/after evidence

# superset.py
SupersetAdapter(run, project_id, host_id)
probe()                           # actual supported flags + auth/host checks
create_workspace(name, branch, base_ref)
create_terminal(workspace_id, launch_argv)
list_terminals(workspace_id)
read_terminal(workspace_id, terminal_id)
close_terminal(workspace_id, terminal_id)
reconcile_assignment(assignment)

# processes.py
run_argv(argv, cwd, env, timeout)   # shell=False; bounded stdout/stderr

# profiles.py
build_profile(role, workspace, public_context, check_profiles)
verify_profile(profile)            # refuses unknown hooks/MCP/code tools
worker_launch(profile, prompt_file, session_id)
```

Service tests call `execute_action`, not adapters directly, for authorization
checks. Adapter tests verify concrete argv and provider readback. Backend role
and approval checks remain mandatory even when UI tool descriptions sound safe.

## Approval and action policy

Owner setup approves the repository's board-management scope and check profiles.
Batch approval uses MCP form elicitation and freezes its digest. Accept only the
matching pending request's client response, `action=accept` and `approve=true`.
Decline, cancel, missing capability, timeout, closed session or mismatched revision
create no grant. There is no `approve` service method callable by an agent.

Claude hooks can auto-answer elicitation. A qualified chief session therefore
loads only Cabinet's reviewed profile/customizations; reject effective
Elicitation/ElicitationResult hooks and managed policy that synthesize responses.
If effective policy cannot be established, approval is unavailable. Native
teammate plan approvals do not enter the grants table.

Financial operations have no executor at all, even after a yes response. The
owner performs them. External publication and release have no automatic
executor in this core release: generate reviewed artifacts and record owner
decisions/completion reports. Later execution support must retain exact-content
approval, but is not required to satisfy this first core workflow.

Allowed board actions: create/update issue, change approved labels/assignees,
set/remove parent, add/remove blocker, and change state with recorded reason.
Completion closes only after the issue's acceptance verdict; deferring/cancelling
a goal requires owner direction when it changes an approved outcome. Ordinary
proposal grooming needs the setup grant, not an implementation grant. Comments,
announcements, repositories, releases, billing, actions dispatches and arbitrary
GraphQL/HTTP endpoints are outside this executor.

Record live repository visibility in the setup grant. Routine issue prose writes
are automatic on the configured private company board. On a public repository,
only the explicitly setup-authorized metadata operations are automatic; prepare
new/changed public prose for exact-content owner approval and manual publication
in this core release. Do not reinterpret board-maintenance consent as permission
to publish private company context. Public-board prose automation would need its
own artifact-bound executor and is not claimed by the private-board acceptance.

Allowed execution actions: reserve/create workspace, launch registered worker,
collect local diff/evidence, run setup-approved isolated checks, assemble a local
integration candidate. Push and merge-to-deployed-branch are excluded until an
explicitly reviewed release path exists. No automatic cleanup of worktrees.

## Isolation and trust boundary

The chief and advisory teammates have no shell, code interpreter, file-write,
browser, external-send or broad third-party MCP tools. Include only native
Read/Grep/Glob/Skill, Agent (chief only), SendMessage/ListAgents where supported,
available Task tools, and the exact Cabinet tools appropriate to the role.
Model-default tool expansion is a startup failure, not accepted convenience.

The chief's Agent tool must be restricted to the packaged approved staff types.
A PreToolUse mechanism validates the actual requested agent type and parent
session against that finite registry, preventing a general-purpose child from
regaining tools excluded from the chief. Test unknown types, CLI-defined types
and attempted permission bypass. Do not rely on the parent prompt to enforce
tool inheritance. This hook enforces a mechanical registry; workflow remains in
the skill. Advisory teammates cannot spawn their own implementation workers.

The same mechanical hook checks SendMessage targets against registered company
peers. Only a newly launched worker's first registration may target its fixed
chief before full peer registration. Unrelated sessions discovered by ListAgents
are not authorized recipients of company data or requests. Add tests for an
attempt to relay a denied action to a broad unrelated session.

Workers launch with `--restricted`, `--strict-mcp-config`, explicit `--tools`
and a verified profile. Implementers edit their assigned worktree. Test runners
may have Bash only under an active mandatory sandbox, with no unsandboxed retry,
external network, credential environment, credential files, service state, host
sockets, Docker socket, parent git metadata or mutable permission/config files.
Use local synthetic services only through separately approved narrow profiles.
Do not assume that a command prefix like `npm test` is safe: repository code can
execute arbitrary subprocesses. Verify its containment as well as its exit code.

Build trusted toolchain access and workspace access into the profile. Sanitize
the child environment by an allowlist; never carry all of `os.environ` into test
commands. The Claude process can authenticate through its normal trusted auth
path; that credential must not become readable by worker file tools or child
shells. Probe this separation rather than assuming it.

Native sandboxing is not a universal isolation guarantee. This design assumes
an uncompromised host and trusted Claude/Superset binaries. Unknown effective
settings, lack of sandbox dependencies, failure to isolate credentials/network,
or an unsupported platform blocks unattended execution. Never bypass this to
meet the schedule. Record the exact missing capability and continue non-execution
work; owner approval cannot make an unverified technical guarantee true.

## Test fixture interfaces

Create these in repository-only `tests/cabinet/support.py` as their consuming
task lands. The test method examples in task files live in unittest.TestCase
classes using a temporary directory per test. Nothing in this fixture module is
imported by production code or exposed by the service.

| Fixture | Defined behavior |
| --- | --- |
| `ServiceCase.setUp()` | Create TemporaryDirectory, fixed clock, Store.open, batch(), active lease, fake adapters and CabinetService; set self.store/service/clock/github/superset; add cleanup |
| `approve_batch_through_fake_ui()` | Run ApprovalService with accept/approve=true for B001 revision 1; never insert a grant directly |
| `FixtureBuilder.assignment(state, terminal_id=None, native_session_id=None)` | Seed W001 for issue 12 at B001/r1 with matching persisted state/event; return assignment |
| `FixtureBuilder.handoff(id, state)` | Seed the contracts' QA correction plus its transition events; return envelope |
| `FixtureBuilder.verified_candidate(head)` | Seed assignment, actual fake git head, check artifact and QA verdict at that SHA; released remains false |
| `seed_assignment(head)` | Set the fake git provider's actual head and FixtureBuilder.assignment for W001 |
| `restart_chief()` | Dispose old service/store; mark old process dead; reopen the same directory with a new native session and lease; reconcile without copying old Python state |
| `FakeSuperset.live(terminal_id, native_session_id, head)` | Set provider-observed live process/workspace/revision, independent of Cabinet's persisted observations |
| `FakeSuperset.calls/launch_count/workspace_create_count` | Capture each attempted provider call; increment only the corresponding actual provider effect |
| `FakeGithubRun.issue(number, data)` | Store a synthetic GET issue result keyed separately by issue number and database ID |
| `FakeGithubRun.fail_page(collection, page)` | Return an explicit provider error on the named page, preserving prior page effects |
| `FakeGithubRun.last_mutation()` | Return the last captured method/path/body, with no credential data |

`self.qa_correction` is the contracts' H001 envelope using B001/r1;
`self.evidence` is an artifact reference/digest plus matching check profile,
SHA, exit code and AC1 verdict. `self.fake` in GitHub tests names FakeGithubRun;
`self.fake_git` names the injected git observation provider. Register role
addresses in ServiceCase before testing sender checks. Implement each injected
test double's specified behavior before a test uses it; no fake result may enter
a live acceptance record.

## Evidence vocabulary

`implemented` = code/prose exists; `unit_verified` = deterministic checks passed;
`native_verified` = actual Claude/Superset behavior observed; `pilot_verified` =
the separately approved business batch passed. A mocked provider is labeled fake.

Live evidence records: date, host/platform, Claude/Superset versions, plugin
commit, batch/revision, sanitized input, event IDs, session/workspace IDs,
actual source SHA, check argv/exit/output artifact hash, and reviewer verdict.
Store provider payloads only after removing tokens and private user content.
