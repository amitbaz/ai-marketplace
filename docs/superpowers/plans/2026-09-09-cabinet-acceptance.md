# Cabinet Recovery and Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use subagent-driven-development only with owner-authorized delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the operating company survives interruption, reports clearly, installs as a Claude plugin and completes a real approved business batch.

**Architecture:** Recover work by reconciling durable state with live providers; preserve judgment separately from observations. Lifecycle commands, bounded hooks and an evidence ledger prevent session endings or partial checks from masquerading as product completion.

**Tech Stack:** Python standard-library tests, Claude plugin commands/hooks, native sessions, Superset CLI, GitHub, Markdown evidence.

**Spec:** [Company design](../specs/2026-09-09-cabinet-company-design.md), [master](2026-09-09-cabinet-ai-company.md), [contracts](2026-09-09-cabinet-contracts.md). Complete O1–O5 first.

## Global Constraints

- "The owner can inspect detail, pause work, or redirect at any point."
- "A session ending does not complete a batch."
- "No session or host running means work is paused, not secretly continuing."
- "Batch approval does not authorize purchases, public communications, or release."
- Every R01–R18 needs its own evidence or an explicit blocked/unrun status.

## A1: Resume from live reconciliation, not conversation memory

**Files:** Extend `store.py`, `service.py`, `migration.py`, `exports.py`,
`references/recovery.md`; create `tests/cabinet/test_recovery.py` and recovery
fixtures. Create `scripts/cabinet-hook`, `hooks/hooks.json`.

**Interfaces:** `reconcile(observations)` returns `{decisions, resumed,
lost, uncertain, blocked, new_generation}` after using registered adapters.
`checkpoint(kind, summary)` records the event sequence and a bounded structured
summary, not an invented claim about live work. Add `Store.get_handoff(id)`,
`Store.get_action(id)`, `Store.pending_handoffs(now)`, `Store.close()` if not
already present; these return persisted state without implying freshness.

- [ ] Write recovery tests with interrupted-state fixtures:

```python
def test_recovery_adopts_live_worker_instead_of_starting_duplicate(self):
    self.approve_batch_through_fake_ui()
    self.fixture.assignment(state="running", terminal_id="T001", native_session_id="N001")
    self.superset.live("T001", native_session_id="N001", head="b" * 40)
    before = self.superset.launch_count
    result = self.service.reconcile({})
    self.assertEqual(result["resumed"], ["W001"])
    self.assertEqual(self.superset.launch_count, before)

def test_recovery_keeps_owner_approval_and_unresolved_question(self):
    self.approve_batch_through_fake_ui()
    before = self.store.get_batch("B001", 1)["digest"]
    self.fixture.handoff("H001", state="acknowledged")
    self.restart_chief()
    self.assertEqual(self.store.get_batch("B001", 1)["digest"], before)
    self.assertEqual(self.store.get_handoff("H001")["state"], "acknowledged")
    self.assertFalse(self.service.snapshot()["batch"]["requires_reapproval"])
```

The restart test closes the old service/connection, marks its process dead in
the fake provider, creates a new service with a different session ID, acquires
the new fenced lease, and reconciles. It does not copy in-memory variables into
the replacement. A real PID/process-start check is separately integration-tested.

- [ ] Run red; implement this ordered recovery:

```text
Open identity-checked store and inspect old lease/process identity.
If old lead is live, stay read-only; do not seize its assignments.
Acquire new generation only after safe ownership resolution.
Load charter/goals/decisions, frozen approvals and last event cursor.
Read current GitHub state and registered worktrees/terminals/revisions.
Reconcile uncertain external operations before retrying anything.
Adopt verified live workers; spawn replacement staff for expired team sessions.
Rebind role addresses and deliver unresolved obligations with the same IDs.
Invalidate check evidence when source revisions changed.
Export current views; give the opening brief; resume only authorized work.
```

- [ ] Test timeout after GitHub mutation, timeout after workspace/terminal create,
  stale native address, PID reuse, two chiefs racing to resume, corrupt/new schema,
  truncated export, missing notebook, restored backup, unknown slug identity and
  external user edits. Preserve uncertainty rather than inventing completion.
- [ ] Make hooks mechanical. SessionStart can report the active company's
  checkpoint to the lead. Stop can block premature completion while live authorized
  work remains and no explicit pause/close exists. SessionEnd records observed
  exit only; it cannot guarantee a summary or keep the system alive.
  Match session IDs to the chief before any hook mutation. A teammate ending must
  not end the company. Missing store/config makes a hook inert with a diagnostic.
- [ ] Use the documented hook schema for the installed Claude version; read its
  official hooks docs before writing the JSON. Ensure a Stop hook cannot loop
  forever: one block per new actionable event sequence; repeated no-progress stop
  records an operational pause requiring recovery. Never auto-accept elicitation
  or broaden permissions in a hook.
- [ ] Kill a synthetic chief during a running worker, launch a new chief, and
  verify it adopts that worker and continues the outstanding handoff. Separately
  kill a teammate and restore its responsibility. Owner performs no state repair.
- [ ] Commit: `feat(cabinet): recover company work across session boundaries`.

## A2: Business reporting, owner steering and consistent commands

**Files:** Create `commands/status.md`, `pause.md`, `close.md`; rewrite
`standup.md`, `now.md`, `review.md`, `decide.md`, `brief.md`, `check.md`, `charter.md`,
`help.md`; complete `references/briefing.md`; extend `exports.py`,
`tests/cabinet/test_exports.py` and lifecycle scenario fixtures.

**Interfaces:** `snapshot` returns separate `company_position`, `approved_work`,
`observed_progress`, `owner_decisions`, `handled_internally`, `next_proposal`,
`unverified_claims`, and `freshness`. `checkpoint` stores the source event range
for each brief. Derive briefs from these fields and the charter, not terminal titles.

- [ ] Write the deterministic reporting assertions first:

```python
def test_session_end_does_not_finish_active_batch(self):
    self.fixture.assignment(state="running")
    self.service.checkpoint("session_close", {"summary":"Pausing for today"})
    actual = self.service.snapshot()
    self.assertNotEqual(actual["batch"]["state"], "completed")
    self.assertTrue(actual["approved_work"]["unfinished"])

def test_development_completion_is_not_release(self):
    self.fixture.verified_candidate(head="b" * 40)
    report = self.service.snapshot()
    self.assertEqual(report["observed_progress"]["development"], "verified")
    self.assertFalse(report["observed_progress"]["released"])
```

- [ ] Run red; implement structured report projections, source freshness and
  events-since-last-brief. No missing source is rendered as zero or all-clear.
  Keep exact evidence in linked artifacts; keep the owner-facing text short.
- [ ] Use this briefing contract and examples in the canonical reference:

```text
OPENING
Where we stand: [business stage and nearest goal]
Current batch: [approved outcome and verified progress]
What changed: [consequence, including important board changes]
Your decisions: [only items requiring your authority/knowledge]

CLOSING / BATCH END
Accomplished: [verified capability and why it matters]
Still underway or blocked: [business consequence and who owns the next action]
Handled by the team: [material decisions, with reasons]
Next: [resume point or proposed next batch; approval status]
Release: [ready / not ready / owner-reported released, with evidence]
```

Positive example: "Invited testers can now enter, and we verified that an
uninvited account is rejected. The team found and fixed a gap during QA. This
is ready for your release decision; no invitations have been sent."

Failing example: "Added invite_id FK, fixed the guard and updated pgTAP; #14
green." It supplies mechanisms without company meaning and has no release
distinction. A human/independent reviewer judges language quality; a filename
regex alone cannot prove that the brief is understandable.

- [ ] Make commands coherent: `company` starts/resumes; `batch` proposes/presents;
  `status` reads current state; `now` remains a compatible read-only status entry;
  `pause` fences dispatch; `close` checkpoints and
  pauses by default; `standup` produces the opening brief; `review` activates
  relevant standing questions; `ask` addresses a named staff role; `brief` supplies
  context from the approved record without manual courier work; `check` requests
  QA against an exact candidate; `decide` records/elicits owner decisions;
  `charter` proposes/shows confirmed amendments; `help` reports the next valid
  action for the actual state. Old numeric decision IDs remain valid after import.
- [ ] Owner steering cancels/supersedes affected assignments without erasing their
  work. A redirect that changes batch scope produces a new proposed revision.
  The next-step recommendation is Product's job, informed by other roles and
  current evidence; it is not an automatic next-batch launch.
- [ ] Retain finance ledger with manual completion reports only. External drafts
  include exact content/destination/audience; approval records attach to their
  digest. This release prepares handoff artifacts for the owner to send/publish;
  it does not add a publishing executor. Do not ask for approval on routine
  internal coordination or already-authorized board edits.
- [ ] Evaluate three synthetic lifecycle cases: successful batch, mid-batch stop,
  and blocker needing owner judgment. Reviewer must identify company position,
  intended outcome, verified progress, next action and release status from the
  brief alone. Save the verdict; revise copy that fails.
- [ ] Commit: `feat(cabinet): report company progress and support owner steering`.

## A3: Claude-only distribution and explicit migration

**Files:** Update `plugins/cabinet/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
root README, Cabinet README/FILES, AGENTS.md, `.github/workflows/validate.yml`,
`scripts/check-cabinet.py`, `tests/cabinet/test_distribution.py`.
Remove Cabinet's entry from `.agents/plugins/marketplace.json` and remove
`plugins/cabinet/.codex-plugin/plugin.json`. Preserve every Groundwork artifact.

**Interfaces:** `python3 scripts/check-cabinet.py` returns nonzero on invalid
Cabinet manifests/frontmatter/commands/tool grants; `--self-test` proves its
negative fixtures. The existing Groundwork checker remains unchanged unless a
new neutral mechanical file needs its boundary handling corrected explicitly.

- [ ] Write tests for missing core role, missing command reference, broad staff
  tool, fictional native tool, legacy-only workflow claims, description/version
  drift, missing MCP executable, changed Groundwork manifest, and Codex Cabinet
  discovery still enabled. Test actual semantic manifest fields, not only strings.
- [ ] Run red. Set unreleased development version to `1.0.0-rc.1` consistently
  in Cabinet's Claude manifest and root table. Use this description identically
  in the Claude plugin and marketplace manifests:

```text
An AI company for a solo founder: accountable staff, approved work batches, direct coordination, durable decisions, and business-language briefs.
```

- [ ] Rewrite current documentation that says Cabinet never coordinates workers,
  has only six fresh advisory dispatches, or retains no runtime database. Explain
  role/session continuity, the explicit writer, approvals, supervised operation,
  restart recovery, local backup limits and actual permission coverage. Preserve
  the full wider department vision. State normal inference usage within the
  owner's chosen plan separately from prohibited purchases/upgrades.
- [ ] Amend AGENTS.md intentionally: the older no-Cabinet-scripts/no-hooks and
  `.cabinet/` committed-state descriptions are superseded; advisory tool restrictions
  remain, while the typed service and isolated workers have separate grants.
  Describe replacement enforcement instead of leaving contradictory old prose.
  Preserve Groundwork's shared-skill/adapter rules and dual-platform manifests.
- [ ] Add Cabinet checks and unit discovery to CI. Preserve existing checks:

```sh
python3 scripts/check-adapter-boundary.py
python3 scripts/check-adapter-boundary.py --self-test
python3 plugins/groundwork/scripts/harvest-transcripts --self-test
python3 plugins/groundwork/scripts/collect-metrics --self-test
python3 plugins/cabinet/scripts/local-sessions --self-test
bash plugins/cabinet/scripts/board-snapshot --self-test
python3 scripts/check-cabinet.py
python3 scripts/check-cabinet.py --self-test
PYTHONPATH=plugins/cabinet/scripts:tests/cabinet python3 -m unittest discover -s tests/cabinet -v
```

Run offline tests on macOS and Linux using preinstalled Python 3; do not introduce
pip/npm installations for plugin code. CI manifest paths must match the removed
Codex Cabinet manifest. Keep Groundwork validation and its self-test fixture.
- [ ] Copy the plugin to a fresh temp directory, launch Claude with that local
  plugin and synthetic settings, and actually exercise command discovery, agent
  dispatch, service tools and hooks. Valid JSON alone is not loader proof.
  Verify legacy commands have explicit supported behavior, not silent disappearance.
- [ ] Record migration behavior for existing Codex users; do not uninstall their
  existing plugin automatically. Runtime state is preserved; backups are local.
- [ ] Commit: `feat(cabinet): package the operating company for Claude Code`.

## A4: End-to-end company acceptance and truthful handoff

**Files:** Create `docs/cabinet/acceptance/core-company.md`, evidence artifacts
with sanitized metadata, and final updates to the progress ledger. After gates
pass, update Cabinet's manifest/table from prerelease to 1.0.0 and rerun checks.

**Interfaces:** The acceptance record uses R01–R18 from the master. Each row has
test input, expected outcome, actual outcome, artifact/event references, exact
plugin revision, and verdict: PASS, FAIL, BLOCKED or NOT_RUN. Unit-only proof
cannot fill a native or business-pilot requirement.

- [ ] Prepare a private synthetic repository with an invitation check and a small
  local unittest suite. Use synthetic company context and an intentionally flawed
  requirement/implementation so staff have something meaningful to resolve.
  Fixture repository creation/writes require owner authorization; if unavailable,
  keep the live GitHub gate blocked and continue offline checks.
- [ ] Start a new qualified chief. Let Product read the fixture goals and recommend
  an outcome. Engineering identifies work; QA defines acceptance; Delivery builds
  the real ticket hierarchy/blockers. Have the owner approve the exact batch.
  Record the user interaction count and classify setup, business decision,
  approval, technical relay or system repair separately.
- [ ] Run this scenario in order, retaining evidence after every step:

| Step | Required observation |
| --- | --- |
| 1 | Product asks Engineering a requirement question; they resolve it through native messages |
| 2 | Delivery verifies real parent/blocker/priority changes; no owner per-edit approval |
| 3 | Approved worker starts automatically in an isolated Superset workspace and registers |
| 4 | QA finds the seeded behavior failure and sends a correction to Engineering |
| 5 | Engineering supplies a new revision; independent checks and QA verify it |
| 6 | Duplicate one handoff and simulate a provider timeout; no duplicate external work |
| 7 | Interrupt the chief mid-batch and start a fresh session; recover vision, approval and unfinished work |
| 8 | Pause from the owner; new dispatch is fenced and in-flight work is accurately reported |
| 9 | Attempt forged approval, scope expansion, financial action, external send and release against harmless sentinels; all denied |
| 10 | Produce a verified local integration candidate and business-language batch summary |

- [ ] Acceptance fails if the owner must copy technical messages, edit state to
  repair the team, decide implementation details that staff could resolve, or
  remind the team of an already-recorded goal/approval. Legitimate new owner
  decisions are not failures. Log every exception instead of hiding it in a summary.
- [ ] Run the full static/unit suite and inspect final integrated revision. An
  independent reviewer checks R01–R18 against artifacts. Delegated review is used
  only if authorized; otherwise request review from the receiving agent/session
  without claiming it has already happened. Fix failures and rerun affected gates.
- [ ] Prepare the actual Career Platform pilot from its current charter and live
  board. It must be a real useful outcome, not an invented task for convenience.
  Obtain its batch approval, inspect that repository's own instructions, then
  exercise the same cycle. Publishing/release remain owner controlled. If owner
  approval is pending, stop only the real pilot and label that gate accurately.
- [ ] Once the required operational gates pass, set 1.0.0, rerun loader/manifest
  checks, and commit `feat(cabinet): verify the core AI company operating cycle`.
  A local commit is not a published release. Push/PR/release remain separate
  instructions. Report incomplete native platform tests explicitly.
- [ ] Final implementation handoff must contain:

```text
Implemented: [actual operating capabilities]
Verified: [unit/static, native scenario, actual business pilot — separately]
Not verified or blocked: [gate, reason, exact next action]
Owner involvement: [legitimate decisions vs technical relay/system repair]
Resume: [company identity, latest event/checkpoint, remaining tasks]
Release: [local candidate / published; exact revision]
```

Completion requires the demonstrated company cycle. The existence of a plugin,
role files, messaging functions or a pleasing brief is not a substitute.
