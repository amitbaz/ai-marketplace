# Cabinet Operating Team Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use subagent-driven-development only with owner-authorized delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the five core staff coordinate approved work, maintain GitHub, launch isolated workers and resolve verification failures without owner message forwarding.

**Architecture:** Native Claude sessions own judgment and discussion; the chief's bounded service records and performs authorized operations. Superset supplies workspace/terminal lifecycle, while native cross-session messages carry staff/worker communication.

**Tech Stack:** Claude plugin Markdown, native messaging, Python standard library, GitHub REST, Superset CLI, unittest.

**Spec:** [Company design](../specs/2026-09-09-cabinet-company-design.md), [master](2026-09-09-cabinet-ai-company.md), [contracts](2026-09-09-cabinet-contracts.md). Complete F1–F4 first.

## Global Constraints

- "Development targets Claude Code only. Superset remains the owner's IDE."
- "The owner does not copy prompts, forward replies, or interpret technical disputes."
- "Batch approval does not authorize purchases, public communications, or release."
- "A session ending does not complete a batch."
- This part must produce functioning collaboration, not renamed advisory reports.

## O1: Replace the advisory-only contract with accountable staff

**Files:** Rewrite `skills/coordination-rules/SKILL.md`; create its five reference
files from the contracts. Expand F4's `agents/chief-of-staff.md`; create `product.md`,
`engineering.md`, `implementer.md`, `test-runner.md`, `design.md`, `marketing.md`;
update `delivery-lead.md`, `qa.md`, `architect.md`, `brand.md`, `cfo.md`, `counsel.md`.
Create `commands/company.md`, `commands/batch.md`; update `hire.md` and `ask.md`.
Create `scripts/check-cabinet.py`; extend `test_distribution.py`.

**Interfaces:** Every staff startup receives `company_view`, `role`,
`batch_id/revision` when applicable, `assignment_id`, lead native address,
registered peer addresses and last confirmed handoff IDs. Worker context also
contains workspace, base SHA, allowed paths and check-profile IDs. Every role
loads the coordination skill explicitly: native teammate spawning does not
guarantee application of the agent definition's `skills` field.

- [ ] Add structural tests that fail on the baseline: missing Product/Engineering
  roles, missing active handoff workflow, broad staff tools, and advisory-only
  standup behavior. Parse the repository's deliberately simple frontmatter with
  a local checker; no YAML package dependency. Reject duplicate keys, unquoted
  argument hints and malformed name/description/tool lines.

```python
def test_all_core_roles_are_packaged(self):
    expected = {"chief-of-staff", "product", "delivery-lead", "engineering", "qa"}
    actual = {p.stem for p in (ROOT / "plugins/cabinet/agents").glob("*.md")}
    self.assertTrue(expected <= actual)

def test_product_has_no_execution_or_publishing_tools(self):
    text = (ROOT / "plugins/cabinet/agents/product.md").read_text()
    tools = next(line for line in text.splitlines() if line.startswith("tools:"))
    for forbidden in ("Bash", "Write", "Edit", "WebFetch", "mcp__github__*"):
        self.assertNotIn(forbidden, tools)
```

- [ ] Write the central skill with this execution order; adapters invoke it and
  supply native syntax, rather than reproducing its instructions:

```text
1. Verify company identity, restricted runtime and current lease.
2. Load company context and reconcile live work before proposing new work.
3. Start/register the required staff; hand each its remit and relevant context.
4. Product gathers evidence and proposes a business outcome with exclusions.
5. Engineering defines technical work; QA defines independent acceptance.
6. Delivery prepares the board and dependencies; assistant presents the batch.
7. Owner response grants or declines the frozen scope. Only then dispatch work.
8. Staff resolve in-scope questions through active handoffs and report results.
9. QA verifies the actual resulting revision; Delivery reconciles the board.
10. Assistant gives the completion/session brief and persists the checkpoint.
```

Owner batch approval is mandatory even when implementation would be reversible.
The old "only one-way doors reach the owner" filter must not suppress this
explicit authority boundary. Routine technical decisions inside an approved
batch remain staff decisions.

- [ ] Encode role-specific work, not merely personas. Product's output includes
  customer evidence versus assumptions, the proposed outcome, business rationale,
  exclusions and acceptance. Engineering supplies a dependency/path ownership
  map and named risks. QA supplies an acceptance-to-check map and independent
  verdicts. Delivery owns pending handoffs and provider readbacks. The chief
  asks the owner only for authority or knowledge the staff cannot supply.
- [ ] Add an explicit disagreement rule: technical means → Engineering;
  desired behavior → Product; execution sequence → Delivery; evidence validity
  → QA. A dispute affecting agreed outcome or risk posture reaches the assistant
  with options and a recommendation. Neither Engineering nor the chief can
  manufacture a QA pass to unblock a task.
- [ ] Encode initiative as event routing, rather than waiting for the owner to
  remember each department. The chief dispatches the owning role on these events:

| Event | Owner and required response |
| --- | --- |
| Company starts or a goal/charter changes | Product reassesses the next outcome; Delivery reconciles current work |
| Batch proposed | Engineering breaks down the work; QA maps acceptance; Delivery checks readiness |
| Batch approved | Delivery releases only authorized assignments for dispatch |
| Board changes or a handoff stalls | Delivery investigates and routes to the responsible staff member |
| Worker reports a candidate | QA verifies; Engineering owns corrections |
| Batch completes | Product recommends the next outcome; assistant gives the closing brief |
| New customer evidence arrives | Product distinguishes evidence from assumptions and proposes any reprioritization |
| Relevant financial/privacy/design threshold appears | Activate the corresponding specialist without granting purchasing/publication authority |
- [ ] Preserve the wider department registry in `company.md` reference: Design,
  Brand, Marketing, Finance and Legal/Privacy are available on demand. Create
  design/marketing read-only role definitions with no publishing tools. A privacy
  threshold can activate Counsel during a core batch. Product owns customer
  research/feedback initially. No invented market evidence or autonomous outreach.
- [ ] Make `/cabinet:company` the company-session entry. In a broad existing
  session it runs read-only diagnosis and provides the verified launcher handoff;
  in a qualified chief session it resumes the operating loop. Initial launching
  is setup, not a recurring copy/paste message workflow. `/cabinet:batch` prepares
  or presents the current proposed revision; it never starts work from its name
  or from an issue label alone.
- [ ] Update hire to import the existing charter/decisions and draft only missing
  company context. Preserve sources, rejected decisions and calibration history.
  Staff propose charter amendments; the owner confirms them through setup/decision
  elicitation. Migration must not ask the owner to reconstruct discoverable facts.
- [ ] Run structural checks; then a live read-only Product–Engineering scenario
  in a synthetic company. Product must recommend a smaller batch when evidence
  makes an unrelated feature unnecessary. Save role outputs and reviewer rationale.
- [ ] Commit: `feat(cabinet): define the company operating roles and workflow`.

## O2: Durable, active communication and supervision

**Files:** Extend `store.py`, `service.py`, `contracts.py`; implement
`references/communication.md` and `tests/cabinet/test_handoffs.py`; add handoff
scenario fixtures. Update core role bodies to use the shared protocol.

**Interfaces:** `record_handoff(envelope)` and `update_handoff(id, transition,
evidence)` follow the contracts. Add `pending_handoffs(now)`, returning due items
without advancing their state. Native dispatch uses the actual tools observed
in F1; the service never writes Claude's private inbox files or invents tool APIs.

- [ ] Write the state tests, including a false receipt:

```python
def test_send_is_not_acknowledgment(self):
    saved = self.service.record_handoff(self.qa_correction)
    self.service.update_handoff(saved["handoff_id"], "sent",
        {"transport":"native", "recipient":"engineering", "result":"sent"})
    item = self.store.get_handoff(saved["handoff_id"])
    self.assertEqual(item["state"], "sent")
    self.assertIn(item["handoff_id"],
                  [x["handoff_id"] for x in self.store.pending_handoffs("2026-09-09T12:00:31Z")])

def test_wrong_registered_sender_cannot_ack(self):
    saved = self.service.record_handoff(self.qa_correction)
    self.service.update_handoff(saved["handoff_id"], "sent",
        {"transport":"native", "recipient":"engineering", "result":"sent"})
    with self.assertRaises(CabinetError) as caught:
        self.service.update_handoff(saved["handoff_id"], "acknowledged",
            {"native_sender":"product", "assignment_generation":1})
    self.assertEqual(caught.exception.code, "RECIPIENT_MISMATCH")
```

Fixtures register all role addresses first, store the correction envelope from
the contracts and use the actual source address metadata. Message-body names
must not substitute for that source metadata.

- [ ] Run the handoff suite red; implement allowed transitions, duplicate ID
  behavior, sender/recipient registration checks and terminal-state protection.
  Reusing an ID with altered content raises IDEMPOTENCY_CONFLICT. Resolving a
  correction requires its matching QA verdict, not only an Engineering reply.
- [ ] Implement this model-level native exchange exactly:

```text
Sender -> chief: proposed actionable envelope.
Chief -> service: record_handoff; receive persisted ID and digest.
Chief -> sender: persisted receipt plus current recipient address.
Sender -> recipient: native message with ID, digest, question and bounded evidence.
Sender -> chief: actual send result (failure is not sent).
Recipient -> chief: acknowledgment bearing the same ID and its generation.
Recipient <-> sender: direct clarification and response.
Recipient -> chief: result; chief records it and routes dependent work.
QA correction: QA, not Engineering, confirms the verified resolution.
```

Native messages can transport questions and evidence immediately, but actionable
work starts only from a persisted authorized assignment. Routine conversational
messages need not become individual database events; record decisions and open
obligations. Limit envelopes to 8 KiB and reference larger evidence by artifact
ID. Truncation must retain a visible missing-content marker and retrieval path.

- [ ] Implement retry scheduling as runtime state, not a token-consuming broadcast
  loop. Default acknowledgment probes at 30, 90 and 210 seconds; these are
  implementation defaults, not promised response times. On an offline recipient,
  restore its role from the assignment. After three unsuccessful delivery
  attempts, mark transport blocked and have Delivery diagnose. Slow active tool
  execution is not automatically a dead worker. Re-arm native one-shot idle
  notifications only from the chief where supported.
- [ ] Add `cabinet_wait_events(after_seq, timeout_seconds)` with timeout capped
  at 30 seconds, returning new durable events and due handoffs. It may observe
  Superset liveness; it cannot claim to observe native semantic completion.
  The chief alternates native messages with bounded waits while a batch is active.
  No per-poll user-facing commentary when nothing changed.
- [ ] While the company session is active, the service checks for changed GitHub
  issues at most once every five minutes by default, using updated-since reads
  with pagination and recording a board.changed event. Refresh the full relevant
  dependency graph before a batch/assignment decision and at batch close. Native
  worker reports trigger prompt readback. An idle/closed company is not a daemon;
  its next opening reconciles missed changes. These intervals are configurable
  runtime defaults and do not authorize new model/API purchases.
- [ ] Test retry after restart, out-of-order acknowledgment, duplicated replies,
  stale generation, wrong batch revision, unknown recipient, blocked native send,
  and a correction still failing after a claimed fix. A forwarded denied action
  remains denied, even if another agent has a wider normal tool grant.
- [ ] Run a real native Product → Engineering → QA exchange. Capture source
  addresses, message IDs, receipts and final disposition. Owner involvement in
  relaying any technical message fails R05.
- [ ] Commit: `feat(cabinet): coordinate acknowledged staff handoffs`.

## O3: Real GitHub ownership with conflict-aware writes

**Files:** Create `github.py`, `tests/cabinet/test_github.py` and paginated provider
fixtures. Extend `service.py`, `policy.py`; update legacy `board-snapshot` and
`charter-sources` to delegate to compatible standard-library readers when ready.
Update `references/batch.md` and Delivery's role.

**Interfaces:** GithubAdapter in the contracts. `run(argv, input_text=None)` is
injected and returns `{returncode, stdout, stderr}`. The service never exposes
an arbitrary `gh api` command or GraphQL string to the model.

- [ ] Write concrete edge-direction/ID tests:

```python
def test_blocker_uses_issue_database_id(self):
    self.fake.issue(12, {"number":12, "id":9012})
    self.fake.issue(14, {"number":14, "id":9014})
    self.github.apply("github.add_blocker", {"issue_number":14,"blocker_number":12})
    request = self.fake.last_mutation()
    self.assertEqual(request["method"], "POST")
    self.assertEqual(request["path"],
        "repos/demo/company/issues/14/dependencies/blocked_by")
    self.assertEqual(request["body"], {"issue_id":9012})

def test_partial_board_cannot_authorize_dispatch(self):
    self.fake.fail_page("issues", 2)
    board = self.github.read_board()
    self.assertFalse(board["complete"])
    self.assertEqual(board["errors"][0]["code"], "SOURCE_INCOMPLETE")
```

Implement FakeGithubRun in `support.py`: named issue/page fixtures, captured
requests, configurable timeout-after-write, and readbacks. It must distinguish
issue number, database ID and GraphQL node ID.

- [ ] Run tests red; implement these endpoints with numeric values resolved from
  read_issue, headers `Accept: application/vnd.github+json` and pinned supported
  `X-GitHub-Api-Version: 2026-03-10` (verify provider support in F1):

| Operation | Method/path | Body |
| --- | --- | --- |
| Create issue | POST `/repos/{repo}/issues` | title, body, approved labels/assignees |
| Update issue | PATCH `/repos/{repo}/issues/{number}` | only allowed changed fields |
| Add blocker | POST `/repos/{repo}/issues/{number}/dependencies/blocked_by` | issue_id of blocker |
| Remove blocker | DELETE same path plus `/{issue_id}` | none |
| Add child | POST `/repos/{repo}/issues/{parent}/sub_issues` | sub_issue_id |
| Remove child | DELETE `/repos/{repo}/issues/{parent}/sub_issue` | sub_issue_id |
| Verify parent/children | GET issue `parent` / `sub_issues` routes | none |

Use `gh api --method METHOD endpoint --input -` with serialized JSON via stdin;
no body text in shell interpolation. Explicit GET for read endpoints. Follow all
pages, filter pull requests from the issues collection, distinguish 401/403/404,
and retain missing relationships as unknown. Do not convert an error into `[]`.
Capture 429/secondary-rate-limit retry guidance and back off without a busy loop.

- [ ] Read back all changed fields and native edges before action state verified.
  Reject parent/dependency cycles. Reparenting is remove-old/add-new with durable
  substeps and post-readback, never a fake body checkbox. Map board priorities to
  the existing labels/project conventions; role ownership stays in Cabinet's
  assignment record unless a real preconfigured GitHub account mapping exists.
- [ ] Preserve human-authored ticket material. Re-read immediately before a write;
  compare expected fields and last-observed version, and return SOURCE_CHANGED
  when stale. Apply only the requested field delta. Body edits preserve text
  outside a managed block or use an explicitly reviewed whole-body change.
  GitHub issue updates do not supply a general multi-field transaction/CAS here:
  keep before/after artifacts and report any observed race; never claim race-free
  editing against independent external writers or blindly retry a stale body.
- [ ] Implement idempotent create using an operation marker in the authorized
  issue body. After timeout, enumerate recent issues and verify exactly one full
  marker match; zero can be retried after a bounded readback delay, multiple are
  UNCERTAIN and require reconciliation. Updates/edges compare desired live state
  before retry. No new comments are used as transport.
- [ ] Test more than 500 issues, more than 100 branches, missing epic label,
  failing relationship pages, duplicate creates, timeout-after-success,
  concurrent user edits, closed blockers with failed acceptance, forbidden repo,
  fake assignee, and public comments denied. Closing a prerequisite by itself
  cannot release an assignment without required verification evidence.
- [ ] In an owner-approved private fixture repository, create two synthetic
  issues, set parent and blocked_by, change one priority, assign only a real
  approved account if configured, and verify all fields. Keep this approval
  separate from authority to alter Career Platform's board.
- [ ] Commit: `feat(cabinet): maintain the board through verified scoped actions`.

Sources: [GitHub issue dependencies](https://docs.github.com/en/rest/issues/issue-dependencies)
and [sub-issues](https://docs.github.com/en/rest/issues/sub-issues). Hierarchy and
dependency are different relationships; implement and test both natively.

## O4: Automatic isolated implementation with safe session registration

**Files:** Create `superset.py`, `tests/cabinet/test_superset.py`; extend
`processes.py`, `profiles.py`, `service.py`, `policy.py`, and implementer/test-runner
definitions. Add worker context template to `references/batch.md`.

**Interfaces:** SupersetAdapter and profile interfaces follow the contracts.
Reserve assignment and action before provider calls. A worker registration is
`{assignment_id, generation, native_session_id, native_address, workspace_id,
terminal_id, actual_base_sha, profile_digest}`; IDs must match service-issued
records and live provider reads. A worker name alone is never sufficient.

- [ ] Write tests for both missing approval and ambiguous startup:

```python
def test_unapproved_batch_never_creates_workspace(self):
    item = self.service.prepare_action(action())
    with self.assertRaises(CabinetError):
        self.service.execute_action(item["action_id"])
    self.assertEqual(self.superset.calls, [])

def test_timeout_after_create_reuses_exact_workspace(self):
    self.approve_batch_through_fake_ui()
    self.superset.timeout_after_creating = True
    item = self.service.prepare_action(action())
    self.service.execute_action(item["action_id"])
    self.assertEqual(self.store.get_action("A001")["state"], "uncertain")
    self.service.reconcile({})
    self.assertEqual(self.superset.workspace_create_count, 1)
```

FakeSuperset records created resources even when the response times out, allowing
reconciliation by stable names/branch and actual base. Fresh UUIDs per retry would
hide this error; derive resource names from batch/revision/assignment instead.

- [ ] Run red; implement probe and automatic creation with real supported CLI:

```python
create = [superset_path, "workspaces", "create", "--project", project_id,
          "--name", stable_name, "--branch", stable_branch,
          "--base-branch", verified_base_ref, "--skip-branch-prefix", "--local", "--json"]
# Read returned workspace; validate its real worktree and base before launching.
launch = [superset_path, "terminals", "create", "--workspace", workspace_id,
          "--cwd", verified_worktree, "--command", quoted_launch_command, "--json"]
```

`quoted_launch_command` is `shlex.join` where supported or
`" ".join(shlex.quote(arg) for arg in launch_argv)` for Python compatibility.
All argv elements originate in validated local paths/IDs; the prompt is stored
in an immutable context file and is never concatenated into executable text.
Terminal creation returns `terminalId`; `agents create` returns a different
shape. Use the terminal path to control the actual restricted launch flags,
not a user preset whose permissions are unknown.

- [ ] Audit Superset automatic setup before creating a worker. A worktree setup
  command can execute before the Claude sandbox exists. Require setup hooks to
  be disabled/inert for this path, or a verified platform mechanism that contains
  them under the same approved profile. Do not assume a nonexistent skip flag.
  If active unsandboxed setup is unavoidable, report SETUP_ISOLATION_UNAVAILABLE
  and hold R07 until resolved; never quietly run it or overwrite project config.
  This is a mandatory F1/O4 compatibility check for the actual installation.
- [ ] Verify the Git base SHA and clean workspace. When Superset only accepts a
  ref, create a local fixed ref through the bounded git adapter, verify it resolves
  to approved base_sha, and pass that ref; never silently use a moving main.
  Local git operations disable hooks via `-c core.hooksPath=<empty-trusted-dir>`.
  Suppress automatic network fetch/push; credentials belong to scoped readers,
  not to workers. Extra required dependencies are a diagnosed prerequisite.
- [ ] Generate worker prompt with approved outcome/ACs, issue ID, assignment,
  owned paths, exact base, peer addresses and response protocol. Worker discovers
  its own native address and sends the registration to the chief. Before marking
  running, compare native metadata with provider workspace/terminal observations.
  A missing registration is startup failure, not a successful dispatch.
- [ ] Enforce path ownership, capacity and pause fencing. Pause commits first,
  cancels any unstarted reservations, and tells live workers to stop safely.
  Closing a terminal is limited to the registered assignment; dirty worktrees
  are preserved. Never send follow-up text to a PTY whose Claude process exited:
  it may now be a shell. Normal follow-ups use native messaging instead.
- [ ] Pass real negative containment probes before enabling a real task:
  inaccessible synthetic credential sentinel, denied private service state,
  denied external network and loopback billing sentinel, no Docker/SSH agent
  socket, denied settings/git-hook mutation, no unsandboxed retry. Test allowed
  editing and a local check too; a profile that denies everything is not usable.
  Actual credentials and real billing/publishing endpoints are never probes.
- [ ] Run a synthetic edit in an automatically created Superset workspace; observe
  native registration and a worker-to-Engineering reply. Close/reopen the chief
  later in A1; do not erase evidence now.
- [ ] Commit: `feat(cabinet): dispatch approved isolated Superset workers`.

Source: [Superset CLI reference](https://github.com/superset-sh/superset/blob/main/apps/docs/content/docs/cli/cli-reference.mdx).
Verify current host/provider behavior; the planning session had no callable CLI.

## O5: Independent verification and local integration

**Files:** Extend `service.py`, `processes.py`, `policy.py`, batch reference,
Engineering/QA/test-runner roles; add `tests/cabinet/test_verification.py`.

**Interfaces:** `record_verdict(assignment_id, revision_sha, reviewer_role,
outcome, evidence)`; add trusted local operations `git.capture`,
`git.commit_candidate`, `git.integrate_candidate` and `check.collect` to the
action enum. Each acts only on registered worktrees and uses explicit argv.
No general Git/shell method. `reviewer_role` must match the registered native
report source; implementation output cannot create a QA verdict.

- [ ] Write a stale-evidence test and independent-role test:

```python
def test_new_code_invalidates_previous_pass(self):
    self.seed_assignment(head="b" * 40)
    self.service.record_verdict("W001", "b" * 40, "qa", "pass", self.evidence)
    self.fake_git.head = "c" * 40
    self.assertFalse(self.service.snapshot()["assignments"][0]["verified"])

def test_worker_cannot_report_its_own_independent_pass(self):
    self.seed_assignment(head="b" * 40)
    with self.assertRaises(CabinetError) as caught:
        self.service.record_verdict("W001", "b" * 40, "implementer", "pass", self.evidence)
    self.assertEqual(caught.exception.code, "INDEPENDENT_REVIEW_REQUIRED")
```

- [ ] Run red; capture exact local revision and content hashes before checks.
  Commit local candidate changes through the scoped git operation after verifying
  allowed paths. Test-runner outputs contain check profile ID, actual argv, base
  and head SHA, exit code, skipped/failed counts and output-artifact hash. Missing
  dependency, zero tests, or required tests skipped is not a pass.
- [ ] QA maps every AC to observed evidence, distinguishes fakes from real
  integrations, and returns pass/fail/blocked with reasons. Engineering receives
  defects through O2 and supplies a new revision. Run checks and QA again against
  that revision; do not reuse a previous pass after changes.
- [ ] Assemble a local integration candidate in its own registered worktree using
  exact reviewed commits, with hooks disabled and no push. Detect overlap before
  integration; conflicts return to Engineering with context. Re-run required
  checks on the integrated revision because separately green branches may fail
  together. Never mark the deployed branch or product released from a local merge.
- [ ] Test out-of-scope files, untracked extra changes, failed checks, contradictory
  QA/Engineering reports, modified evidence artifacts, missing SHA, integration
  conflicts, stale board closure, and scope expansion disguised as a bug fix.
  Approved paths constrain actions but cannot mechanically prove business intent:
  Product/QA review against ACs remains required.
- [ ] Demonstrate an intentionally failing local invitation test, automatic QA
  handoff, Engineering correction, and final pass. Owner receives the business
  consequence and final result, not a request to debug or forward a message.
- [ ] Commit: `feat(cabinet): verify corrections and integrated outcomes`.

Continue to A1. A successful one-session exchange is insufficient until recovery,
reporting, installability and the full acceptance scenario also pass.
