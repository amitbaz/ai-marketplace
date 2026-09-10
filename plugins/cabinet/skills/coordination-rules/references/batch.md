# A batch — proposal through completion

Reference for [the coordination rules](../SKILL.md). A batch is one owner-
approved business outcome and everything authorized to reach it. It is the
unit of consent in this company: work exists inside a batch or it does not
exist.

## The states

```text
proposed → approved → running → verifying → ready_for_release → completed
```

Any active batch can become `paused` or `blocked`; resuming returns it to its
stored prior state after reconciliation. `superseded` preserves the old
revision and revokes its grant rather than editing it.

`completed` means the approved development outcome was verified. It carries a
separate fact, `released=false`, until the owner reports release evidence. **A
batch need not be released to finish its approved development scope**, and a
session ending never completes a batch.

What moves a batch forward:

| From | To | What has to be true |
| --- | --- | --- |
| proposed | approved | The owner approved this exact revision and digest |
| approved | running | The first authorized assignment was dispatched |
| running | verifying | A candidate was reported with its check artifacts collected |
| verifying | running | QA failed it; the correction is in scope |
| verifying | ready_for_release | Every acceptance criterion has a matching QA pass at the integrated revision, with no unresolved required handoff and no live implementation assignment |
| ready_for_release | completed | The chief's batch-end checkpoint recorded verified development, released=false |

A request to complete earlier is refused. Release evidence is recorded
separately and never inferred from a green check.

## What each role contributes to a proposal

A proposal is not ready until all four have contributed. The chief assembles
them; nobody writes the batch body but the chief.

**Product — the outcome.** Five things, and the first is the one most often
skipped:

- **Customer evidence versus assumptions**, separated and labelled. What a
  person could go and check, against what the company currently believes.
- **The proposed outcome** in business terms: what a customer can do
  afterwards that they cannot do now.
- **The business rationale**: why this outcome now, and what it tests.
- **The exclusions**: what is deliberately not in this batch, named, so that
  "we should also" has somewhere to go that is not scope creep.
- **Acceptance**: what would have to be true for this outcome to be real.

Product is expected to **recommend less work when less work is sufficient**.
A smaller batch that tests the business idea is a better proposal than a
complete one, and saying so is the job rather than a lack of ambition.

**Engineering — the technical shape.**

- A **dependency map**: what has to exist before what, including dependencies
  that exist only in the prose of a ticket.
- A **path ownership map**: which parts of the tree each assignment touches,
  so two workers never own the same paths. Conflicting assignments wait rather
  than race.
- **Named risks**: what could go wrong, with the specific thing that would go
  wrong, not a category.
- Where a technical decision is genuinely open, the options and the
  recommendation — inside an approved batch this is Engineering's call, and it
  is reported rather than asked.

**QA — independent acceptance.**

- An **acceptance-to-check map**: for every acceptance criterion Product
  wrote, the check that would fail if that criterion were violated. A
  criterion with no check behind it is a claim, and QA says so at proposal
  time rather than at verification time.
- What kinds of testing this outcome implies that the suite may not cover at
  all. Take the categories the charter actually justifies; do not import a
  generic taxonomy.
- QA writes acceptance **before** implementation and verifies **after**. It
  does not negotiate the verdict in between.

**Delivery — readiness.**

- Whether the board reflects this batch: tickets exist, the hierarchy is
  right, blockers are recorded where they are real.
- The startable frontier: what could actually begin on approval, and what is
  waiting on something.
- What is already in flight that this batch would collide with.
- Any handoff still unresolved from a previous batch.

## What the chief freezes

The batch body the owner approves. Once approved, its digest is the authority
for every dispatch, and these fields cannot change without a new revision:

| Field | What it holds |
| --- | --- |
| `outcome` | The business capability, in the owner's language |
| `rationale` | Why this, now |
| `evidence` | Customer evidence, labelled, with assumptions separated |
| `exclusions` | What is deliberately out |
| `acceptance` | The criteria, each with the check that covers it |
| `assignments` | The units of work, each with its owner role and paths |
| `dependencies` | What must precede what |
| `risks` | Named, with their consequence |
| `board` | The tickets this batch authorizes maintaining |

A change to any of these produces a **new proposed revision** for approval. It
does not amend the approved one, and it does not carry the old grant forward.

## After approval

Only assignments named in the approved revision are dispatched, and Delivery
releases them. An idea that arrives mid-batch is either inside the approved
outcome, in which case staff decide it and report it, or it is a proposal for
the next batch. There is no third option where good judgement widens the
scope.

## Board maintenance inside a batch

Delivery directs board changes; it performs none. Every change runs the same
four steps, and each step answers a different question.

| Step | Who | What it answers |
| --- | --- | --- |
| Direct | Delivery | What should change on the board, and the business consequence of leaving it wrong |
| Prepare | Chief | Is this a named operation, on this repository, with a whole payload? Preparing is never permission to run |
| Execute | Chief | Does a live grant cover it right now, and did the issue move since it was prepared? |
| Read back | Chief | Does the board actually say what was asked for? |

Nine operations exist and no others: create and update an issue, set labels,
set assignees, set and remove a parent, add and remove a blocker, and change
state with a recorded reason. Comments, announcements, releases, workflow
dispatches and arbitrary queries have **no executor at all**. A change nobody
listed is not a change that needs approval; it is one nothing can perform.

A brief line about a board change names the effect and the consequence, not
the request: "Issue 14 is now blocked by 12, so the invitation work cannot
start before the account split lands" rather than "added a blocker".

### What is automatic, and what is not

**On the company's private board**, every one of the nine runs without asking,
under the setup grant the owner gave once. Ordinary grooming is not a decision.

**On a public repository**, only the metadata operations run: labels,
assignees, parent, blockers, and state with its reason. Anything that writes
prose a reader would take as the company speaking — a new issue body, a
changed title or body — is **prepared and handed to the owner** with its exact
content, and the action stays unexecuted. Board maintenance consent is not
permission to publish.

**On a repository whose visibility could not be read**, nothing is assumed. An
unread board is treated as one that could be public: prose is prepared for the
owner, and metadata runs only if the owner declared the board private *and* an
earlier live read agreed. With no live reading ever, nothing is automatic and
setup is re-run once the repository can be reached.

Two changes need something beyond the setup grant whatever the repository is:

- **Closing an issue as completed** needs its acceptance verdict — a QA pass
  recorded against **the exact head the assignment reported**. A pass from
  before the last change does not close a ticket, because the code QA looked
  at is not the code that is there now. Delivery's reading of done is not a
  verdict, and Engineering reporting a fix is not one either.
- **Closing an issue as not planned when it is in the approved batch** needs
  the owner's recorded decision. Dropping it changes an approved outcome.

### Directing a change means saying what you saw

A board change names what it believes it is changing: the ticket's timestamp,
and the current value of every field it is about to set. That is not
bookkeeping. The executor re-reads the ticket immediately before it writes and
compares; with nothing to compare, a write cannot notice that somebody edited
the ticket while the action waited, and it would report success for having
overwritten them. A change that states nothing is refused before it reaches
the board.

The one exception is Cabinet's own managed block, which changes only the text
between its markers. Replacing a whole ticket body is the destructive case, and
that one has to quote the body it is replacing.

### What a write refuses, and what to do about it

| Refusal | What actually happened | What comes next |
| --- | --- | --- |
| The change said nothing about what it believes it is changing | It was directed without reading the ticket first | Read it, record the timestamp and the fields in play, and direct the change against those |
| The issue moved since the action was prepared | Somebody edited the ticket while the action waited | Re-read, and direct the change again against what the ticket now says. Never re-send the stale body |
| The repository's visibility is unknown | The live read of the repository failed | Prose waits for the owner. Metadata waits for a repository that can be read; re-run setup |
| The graph is too wide or too deep to walk | The adapter cannot prove the edge closes no cycle | Nothing was written. The ordering question is a real one; answer it before asking again |
| The edge would close a cycle | The parent or blocker being added is already downstream of the issue | The ordering itself is wrong; that is Delivery's to resolve, not the board's |
| The account cannot be assigned | A role name is not a GitHub account | Ownership stays in Cabinet's assignment record. Cabinet never invents a username |
| The board could not be read whole | A page did not arrive | Nothing dispatches. What is startable is unknown until the board reads clean |
| The write timed out | It may already have happened | Reconcile by reading. A create is settled by its own marker; a retry before that can create a second ticket |

A body edit changes only Cabinet's managed block and leaves every other line
of the ticket alone. Replacing a whole body means overwriting somebody's
writing, so it happens only against a replacement that was reviewed as text.

## Dispatching an assignment into an isolated workspace

Nothing about an implementation worker is a matter of intention. A batch is
approved, an assignment is reserved, a workspace is created at the exact
approved revision, a worker is launched into it with a verified profile, and
the worker registers itself before it is anything more than a process. Each of
those is a recorded step, and skipping one does not produce a faster start; it
produces a worker nobody can account for.

The order is fixed:

1. **Reserve the assignment.** One work item and one path set, claimed. A
   second claim on paths somebody already holds waits — it does not race, and
   it is not a reason to widen the first assignment's paths so both fit.
2. **Create the workspace.** The approved base revision is pinned to a fixed
   ref and read back before anything is branched from it. A moving branch name
   is never the base: what the owner approved was a revision.
3. **Launch the worker.** The command line comes from the verified profile,
   and the instruction comes from a context file written once and left
   read-only. Neither is assembled from anything a model said.
4. **Wait for registration.** The assignment is `starting`, not `running`. A
   terminal that started is not a worker.

### The worker context

Every worker is launched with all of this, and a worker missing any of it says
which field and stops rather than inferring it:

| Field | What it is |
| --- | --- |
| `assignment_id` | Its identity across restarts and replacements |
| `generation` | The lease generation the assignment was reserved at |
| `outcome`, `goal`, acceptance criteria | The approved result, verbatim |
| `issue` | The work item it owns |
| `owned paths` | The paths inside the workspace it may change |
| `workspace` | The absolute path of the worktree, and the only one |
| `base revision` | The exact 40-character revision the work starts from |
| `check profiles` | The approved checks, for a test runner |
| `chief` | The address it registers with, and its only route out at first |
| `peers` | The registered addresses it may talk to once registered |

### What registration has to prove

A registration is not an announcement. It is checked against the record the
service issued at launch **and** against what the provider can see right now,
and all three have to agree:

    assignment_id      the assignment it claims
    generation         the generation that assignment was reserved at
    native_session_id  its own session
    native_address     the session name it can be reached at
    workspace_id       the workspace it is running in
    terminal_id        the process it is running as
    actual_base_sha    the revision its workspace is actually at
    profile_digest     the launch profile it was started with

A stale generation is a worker from a previous attempt. A mismatched terminal
is a different process. A claim the provider cannot see is a session that
found us rather than one we started. None of the three becomes `running`, and
a name on its own never was sufficient.

If no registration arrives inside the startup window, the dispatch failed. It
did not quietly succeed and go unnoticed: an assignment with no registration
is blocked and said out loud, because a worker believed to be working is worse
than one known to be absent.

### Follow-ups, stopping, and what is never deleted

Follow-up text goes over native messaging, addressed to the session. It never
goes to the terminal. A terminal whose Claude process has exited is a shell,
and text typed into a shell is a command; the fact that the last thing running
there was a worker does not make the next thing typed a message.

A pause commits first, so nothing new starts. Reservations that never became a
process are cancelled outright — there is nothing running to disagree. A
worker that *is* running is asked to stop and moved to `cancel_requested`, and
it stays there until it reports. Recording the request is not the same as the
worker having stopped, and reporting it as cancellation would be this company
claiming somebody else's action as finished.

Closing a terminal is scoped to the assignment registered against it. The
worktree is never removed, whatever state it is in: uncommitted work in it is
somebody's, and deciding it is disposable is not a dispatcher's call.

### When a workspace cannot be created here

Two refusals are prerequisites rather than faults, and both name what is
missing instead of falling back to something else:

- **No usable workspace provider.** The mechanism the setup grant names cannot
  create an isolated workspace on this host — most often because it is not
  authenticated. Nothing silently substitutes a different mechanism: which one
  runs is a decision the owner made at setup, and changing it because
  something failed is exactly the substitution this refuses.
- **Setup isolation unavailable.** The project runs a setup command when a
  workspace is created, and that command runs before the sandbox exists.
  Containment is not established, so no worker is created and the isolation
  claim is not made.

## Extended by

O5 (the correction loop and the integration candidate).
