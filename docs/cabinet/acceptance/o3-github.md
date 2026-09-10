# O3 — GitHub board ownership: live read probes, and the write gate

**Date:** 2026-09-10 · **Host:** macOS (Darwin 25.6.0), arm64 ·
**`gh`:** 2.100.0 (2026-09-03) · **Plugin tree:** `codex/cabinet-company-design`,
base `045849c` · **Batch/revision:** none — these are adapter probes, not a
batch.

Two things are recorded here and they are not the same thing.

1. **Live reads: run.** Every read path in `github.py` was exercised against
   the real GitHub REST API, and one of them found a defect no fake could have
   found. Results below, sanitized.
2. **Live writes: RUN (task L1, 2026-09-10)** against the owner-authorized
   private fixture repository `amitbaz/cabinet-fixture`. Career Platform's
   board was never written, in this session or any prior one. Details below.

---

## The write gate

**Status: RUN (task L1 Part B, 2026-09-10).** Live writes against
`amitbaz/cabinet-fixture` (private, owner-authorized throwaway repo, to be
deleted after A4) are recorded below. Career Platform's board was still
**never written** in this or any prior session.

Driven by a scripted Python client instantiating the real
`cabinet_runtime.github.GithubAdapter` directly against `gh api` (the brief
allows a scripted client driving the adapter, "since the point is the
adapter and readback, not the model"), rather than through a full chief
session, to keep the run to the minimum live surface needed to prove the
adapter and its readback. No `gh api` call used `--method` other than the
ones the adapter itself issues (`GET`, `POST`, `PUT`, `PATCH` — never
`DELETE`); no repository other than `amitbaz/cabinet-fixture` was named in
any write; nothing in `amitbaz/career-platform` or any other repository was
touched.

### What ran, in order

1. **Two synthetic issues created**, each body carrying the marker
   `cabinet-L1-partB-2026-09-10`:
   - `#1` "[cabinet-test] parent issue" — `POST repos/amitbaz/cabinet-fixture/issues` → 201, readback `GET .../issues/1` → 200, `outcome: verified`.
   - `#2` "[cabinet-test] child issue" — same shape, `outcome: verified`.
2. **Parent set**: `#2`'s parent set to `#1` via `github.set_parent` — reads `#2`, `#1` (twice, once per the adapter's own pre-write check), `POST repos/amitbaz/cabinet-fixture/issues/1/sub_issues` → 201, readback confirmed `parent: 1` on `#2`. `outcome: verified`.
3. **Blocker added**: `#2` blocked_by `#1` via `github.add_blocker` — `POST repos/amitbaz/cabinet-fixture/issues/2/dependencies/blocked_by` → 201, readback confirmed `blocked_by: [1]`. `outcome: verified`.
4. **Label changed**: `#2` labeled `bug` (an existing repo label — no label was created) via `github.set_labels`. First attempt refused live with `EXPECTATION_REQUIRED` because the script's `expected_before` did not name the current `labels` value — real evidence the conflict-aware-write policy holds even for a scripted client, not just in unit tests. Corrected call: `PUT repos/amitbaz/cabinet-fixture/issues/2/labels` → 200, readback confirmed `labels: ["bug"]`. `outcome: verified`.
5. **Parent closed `not_planned`** with an owner-decision record via `github.set_state`, `reason: "Owner decision (task L1 Part B, 2026-09-10): synthetic evidence issue, closing as not_planned after readback is captured."` Two live refusals along the way, both matching the policy exactly rather than being worked around: `EXPECTATION_REQUIRED` for a missing `state`, then again for a missing `state_reason` — `set_state`'s own `_PAYLOAD_FIELDS`/expectation check requires both. Corrected call: `PATCH repos/amitbaz/cabinet-fixture/issues/1` → 200, readback confirmed `state: closed`, `state_reason: not_planned`. `outcome: verified`.
6. **Full readback and compare**: final `read_issue` on both `#1` and `#2` matched every field the writes above claimed — parent/child linkage, `blocked_by`, `labels`, `state`/`state_reason` all consistent between the write responses and independent reads.
7. **Timeout-after-create reconciliation, with a real timeout** (not a simulated flag): a second `GithubAdapter` was built with a `run` wrapper that overrides every call's timeout to 0.05 s — far too short for a real network round trip — and used for one `github.create_issue` call carrying a fresh idempotency marker. `processes.run_argv` genuinely killed the subprocess and reported `timed_out: True`; `apply()` returned `outcome: uncertain` rather than raising, per its documented timeout branch. `reconcile_action` was then called (with the normal-timeout adapter, since reads need to actually finish) against the same marker: `matches: 0`, `outcome: retry_after_delay`. Waited the stated `retry_after_seconds` (15 s) and reconciled again: still `matches: 0`. **Conclusion: the 0.05 s timeout killed the subprocess before the request reached GitHub at all** — no issue was created, and reconciliation correctly reported that by reading rather than assuming either outcome. No third issue exists on the board (confirmed independently with `gh issue list --repo amitbaz/cabinet-fixture --state all`, which shows exactly `#1` and `#2`). This proves the reconciliation mechanism reads real state rather than guessing, though the specific empirical outcome here is "zero created" rather than "exactly one" — a genuine result, not a chosen one.
8. **Final board state, documented and left as-is:**
   - `#1` "[cabinet-test] parent issue" — **closed, not_planned**.
   - `#2` "[cabinet-test] child issue" — **open**, parented to `#1`, `blocked_by: [1]`, labeled `bug`.
   - No other issue exists on `amitbaz/cabinet-fixture`.

### What this proves and what it does not

- **Proven live:** create, set_parent, add_blocker, set_labels, set_state
  (with `not_planned` + owner decision record), full readback-matches-write,
  and the timeout→reconcile path with a genuine (not simulated) timeout.
- **Not run this session:** `set_assignees` (the brief allows this only
  "if configured" with a real `github_accounts` mapping; none was
  configured for this synthetic run, so it was correctly skipped rather
  than assigning a fictitious account), `remove_parent`, `remove_blocker`,
  `github.update_issue`/body edits, and anything through the full
  chief/service/policy stack (this run drove the adapter directly, per the
  brief's allowance — the policy/service layer around it is
  `unit_verified` only, unchanged from before this task).
- **R06's live half is now proven** for the operations exercised above.
  Assignee-mapping and remove-edge paths remain `unit_verified` only.

---

## Probe 1 — authentication

```
$ gh auth status
```

| Fact | Observed |
| --- | --- |
| Logged in | yes |
| Host | github.com |
| Token type | OAuth (`gho_…`), stored in the keyring |
| Scopes | `gist`, `read:org`, `repo`, `workflow` |

The token value is not recorded here and is not readable from any adapter
return: `processes.redact` rewrites `gho_`/`ghp_`-shaped material, and the
adapter passes every provider message through it before surfacing one.

---

## Probe 2 — the API version header is accepted

```
$ gh api -i -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2026-03-10" repos/cli/cli
```

```
HTTP/2.0 200 OK
X-Github-Api-Version-Selected: 2026-03-10
X-Github-Media-Type: github.v3; format=json
X-Ratelimit-Limit: 5000
```

**`2026-03-10` is accepted and is what the server selected.** The pin in
`github.py` (`API_VERSION`) stays at that value. No newer version had to be
substituted.

The same response confirms `visibility: "public"` is a field of the repository
document, which is what `read_visibility()` reads into the setup grant.

---

## Probe 3 — issue, sub-issue and dependency response shapes

Two public issues in `cli/cli`, and one relationship-carrying issue set in
`amitbaz/career-platform` (read only).

**An issue's identifier is not its number.** `cli/cli#10000` returns
`id: 2716143027`, `number: 10000`, `node_id: "I_kwDODKw3uc6h5Q2z"` — three
different identifier spaces, which is why every edge in the adapter resolves
the database id from a read before it writes.

**A pull request arrives in the issues collection.** `cli/cli#11000` came back
with a `pull_request` key and `node_id: "PR_kwDODKw3uc6Wv2lA"`, and carried
**no** `sub_issues_summary` and **no** `issue_dependencies_summary`. Page 3 of
that repository's `state=all` issues collection held 100 rows: 61 pull requests
and 39 issues. Filtering on the `pull_request` key is what the adapter does.

**Relationship summaries are on the issue; the edges are on their own routes.**

| Route | Status | Shape |
| --- | --- | --- |
| `GET /repos/{repo}/issues/{n}` | 200 | `sub_issues_summary: {total, completed, percent_completed}`, `issue_dependencies_summary: {blocked_by, total_blocked_by, blocking, total_blocking}` |
| `GET /repos/{repo}/issues/{n}/sub_issues` | 200 | array of full issue documents |
| `GET /repos/{repo}/issues/{n}/dependencies/blocked_by` | 200 | array of full issue documents |

Three findings that changed the implementation:

- **There is no `parent` object.** A child carries `parent_issue_url`, and an
  issue with no parent simply omits the field. So "no parent" and "this
  response cannot say" are told apart by whether `sub_issues_summary` is
  present at all — which it is on every issue under this API version, and is
  not on a pull request. That is what makes `parent: "unknown"` reachable
  rather than decorative.
- **`blocked_by` counts open blockers; `total_blocked_by` counts all of them.**
  Observed on `amitbaz/career-platform#189`: `blocked_by: 3`,
  `total_blocked_by: 4`, and the `blocked_by` route returned 4 rows. An issue
  whose blocker is closed therefore reads `blocked_by: 0, total_blocked_by: 1`
  — visible on `#204`. A board reader that trusted `blocked_by` alone would
  report a dependency that is still recorded as absent.
- **Elements of both edge routes are full issue documents**, carrying `id`,
  `number`, `node_id`, `state` and `state_reason`. The adapter keeps only the
  numbers; the identifiers it needs it re-reads per issue.

---

## Probe 4 — pagination over a large collection

`cli/cli` reports 1085 open issues and pull requests, so its
`state=all` collection is well past one page.

```
$ gh api -i ".../issues?state=all&per_page=100&page=1"
Link: <https://api.github.com/repositories/212613049/issues?state=all&per_page=100
       &page=2&after=Y3Vyc29yOnYyOpLPAAABoFmkg8jPAAAAATwx-hQ%3D>; rel="next"
```

**The issues collection paginates by cursor, not by page number.** The `next`
link carries an opaque `after=` cursor alongside the page number. A reader that
increments `page=` locally walks a different sequence than the provider
intended and can repeat or skip rows. `_next_link` follows the URL the provider
gave, verbatim, and the fixture's `Link` header points at a host that does not
exist so a test fails if the adapter ever rebuilds one.

Following that link with `gh api` against the full URL works, including the
cursor: page 2 returned 200 with its own `rel="next"`.

---

## Probe 5 — the delegated wrappers, end to end

`board-snapshot` and `charter-sources` now delegate to
`python3 -m cabinet_runtime.boardcli` when `python3` and the runtime package
are importable, and keep their `gh`+`jq` path otherwise.

**`bash plugins/cabinet/scripts/board-snapshot amitbaz/career-platform --since 2026-09-01`**

```
Board: 66 open · 3 epics · 0 PRs · 2 branches · 89 merged
board=$TMPDIR/cabinet-board-amitbaz-career-platform.json
epics=$TMPDIR/cabinet-epics-amitbaz-career-platform.json
```

3.6 s wall clock. `complete: true`, `errors: []`. The file's keys are the
legacy set plus `complete` and `errors`. A merged row keeps `closes`, derived
from closing keywords in the pull request body and labelled
`closes_source: "body_keywords"` so nobody mistakes it for the provider's own
link graph.

**`bash plugins/cabinet/scripts/board-snapshot octocat/Hello-World`**

```
Board: 5147 open · 0 epics · 10 PRs · 3 branches · 0 merged
board-snapshot: issues page 60 did not arrive (issues did not stop paginating
  within 60 pages); this snapshot is incomplete and does not say what is
  startable
```

This is the property under test, observed live: a board past the adapter's page
ceiling reports itself incomplete rather than reporting a number. The legacy
`--limit 500` would have returned exactly 500 and said nothing.

**`bash plugins/cabinet/scripts/charter-sources amitbaz/career-platform`**

```
Sources: 2 rejected · 19 recorded decisions · 30 comments on 15 tickets ·
  10 docs to read, 12 skipped, 45 unclassified
```

10.6 s. The Markdown inventory was checked against the `jq` filter it replaces
and agrees exactly: `{total: 67, read: 10, skip: 12, rest: 45}` from both.

---

## What the live reads found that the fakes could not

Two defects, both of which turned a real response into an empty one.

**1. Output redaction corrupted every JSON body containing a `key` field.**
`processes.run_argv` redacts anything shaped like `name: value` where the name
resembles a secret. A GitHub pull request document contains
`"license":{"key":"mit"}`, so the redactor rewrote it to `"license":{"key":
[redacted]"` — invalid JSON. The parse failed, and the adapter's original code
turned an unparsable body into `payload = None`, which `_collect` read as zero
rows. `board-snapshot --since 2026-09-01` reported **0 merged pull requests**
when there were **89**.

Fixed two ways, because either alone leaves the other hole open:

- `run_argv` gained `redact_output`, and `gh_run` turns it off. A caller that
  parses output structurally and returns selected fields owns its own
  redaction; the adapter does that in `_message`, which every surfaced
  provider string passes through. Redaction stays on by default everywhere
  else, and a test asserts it.
- An unreadable body now raises `PROVIDER_ERROR` instead of becoming `None`.
  A page that arrived truncated is reported, never counted as zero.

**2. The default output bound is smaller than a real page.** One page of 100
pull requests with bodies measured 1,047,842 bytes against `OUTPUT_LIMIT` of
1,048,576 — 734 bytes of headroom. `bound()` appends a truncation marker, which
would have broken the JSON on any slightly larger board, silently before the
fix and loudly after it. `gh_run` raises the provider bound to 32 MB.

Both are covered by `TransportTest` in `tests/cabinet/test_github.py`.

---

## Rate limiting

Not provoked live: doing so deliberately would have spent the account's budget
for no information the headers do not already give. The headers that drive the
backoff were observed present on every response (`X-Ratelimit-Limit: 5000`,
`X-Ratelimit-Remaining`, `X-Ratelimit-Reset`), and `Retry-After` handling,
attempt bounding and the no-zero-delay rule are `unit_verified` in
`RateLimitTest`.

---

## Evidence level

| Claim | Level |
| --- | --- |
| Read paths, pagination, PR filtering, relationship shapes, API version pin | **native_verified** |
| Legacy wrapper delegation and output parity | **native_verified** |
| Every mutation path, cycle rejection, readback, reconciliation, gates | **unit_verified** (`FakeGithubRun`); create/set_parent/add_blocker/set_labels/set_state/reconcile also **native_verified** against `amitbaz/cabinet-fixture` (task L1) |
| Live board writes | **RUN (task L1, 2026-09-10)** against `amitbaz/cabinet-fixture`; `set_assignees`/`remove_parent`/`remove_blocker`/body edits and the full chief/service/policy stack around the adapter remain unit_verified only |
