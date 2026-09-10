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

Two changes need something beyond the setup grant whatever the repository is:

- **Closing an issue as completed** needs its acceptance verdict. A QA pass at
  the revision the work produced is what opens that gate; Delivery's reading of
  done is not, and Engineering reporting a fix is not.
- **Closing an issue as not planned when it is in the approved batch** needs
  the owner's recorded decision. Dropping it changes an approved outcome.

### What a write refuses, and what to do about it

| Refusal | What actually happened | What comes next |
| --- | --- | --- |
| The issue moved since the action was prepared | Somebody edited the ticket while the action waited | Re-read, and direct the change again against what the ticket now says. Never re-send the stale body |
| The edge would close a cycle | The parent or blocker being added is already downstream of the issue | The ordering itself is wrong; that is Delivery's to resolve, not the board's |
| The account cannot be assigned | A role name is not a GitHub account | Ownership stays in Cabinet's assignment record. Cabinet never invents a username |
| The board could not be read whole | A page did not arrive | Nothing dispatches. What is startable is unknown until the board reads clean |
| The write timed out | It may already have happened | Reconcile by reading. A create is settled by its own marker; a retry before that can create a second ticket |

A body edit changes only Cabinet's managed block and leaves every other line
of the ticket alone. Replacing a whole body means overwriting somebody's
writing, so it happens only against a replacement that was reviewed as text.

## Extended by

O4 (assignment dispatch into isolated workspaces) and O5 (the correction loop
and the integration candidate).
