# O3 — GitHub board ownership: live read probes, and the write gate

**Date:** 2026-09-10 · **Host:** macOS (Darwin 25.6.0), arm64 ·
**`gh`:** 2.100.0 (2026-09-03) · **Plugin tree:** `codex/cabinet-company-design`,
base `045849c` · **Batch/revision:** none — these are adapter probes, not a
batch.

Two things are recorded here and they are not the same thing.

1. **Live reads: run.** Every read path in `github.py` was exercised against
   the real GitHub REST API, and one of them found a defect no fake could have
   found. Results below, sanitized.
2. **Live writes: BLOCKED — awaiting owner authorization of a fixture repo.**
   Nothing in this session created, changed or closed anything anywhere. Every
   mutation path is `unit_verified` against `FakeGithubRun` only.

---

## The write gate

**Status: BLOCKED — awaiting owner authorization of a fixture repository.**

The brief's checkbox reads: *"In an owner-approved private fixture repository,
create two synthetic issues, set parent and blocked_by, change one priority,
assign only a real approved account if configured, and verify all fields."*

The owner has not authorized a fixture repository, so it was not run. In this
session:

- no repository, issue, comment or label was created anywhere;
- no `gh api` call used `--method` other than `GET`;
- `amitbaz/career-platform` was **read** (issue shapes, relationship element
  shapes, the delegated wrapper end to end) and never written.

**Exact next action to unblock it.** The owner creates or names one **private**
repository they are willing to have Cabinet mutate — a throwaway such as
`amitbaz/cabinet-fixture` — and says so explicitly. Then, against that
repository only: create two synthetic issues, set one as the other's parent,
add a `blocked_by` edge, change one label, assign only a real account if a
`github_accounts` mapping exists, and read every field back. Approval for that
repository is **separate from and does not extend to** Career Platform's board.

Until that runs, R06's live half is unproven. What is proven is the shape of
every request, because the tests assert the exact method, path and body that
would be sent.

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
| Every mutation path, cycle rejection, readback, reconciliation, gates | **unit_verified** (`FakeGithubRun`) |
| Live board writes | **BLOCKED — awaiting owner authorization of a fixture repo** |
