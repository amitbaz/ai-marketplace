# Resume, reconcile, pause, close

Reference for [the coordination rules](../SKILL.md). A company outlives its
sessions. What a new session must not do is reconstruct the company from a
conversation, or from what it remembers, or from the owner.

## The one thing this file protects

**A fresh session recovers the same vision, approved scope, unresolved
handoffs and verified results without asking the owner to reconstruct them.**

Everything below is in service of that sentence.

## What persists, and in what layer

- **The company**: charter, full vision, authority boundaries, goals,
  department remits, decision history. This describes who the company is and
  changes slowly.
- **The work**: approved batch revisions, assignments, handoff records,
  evidence references, checkpoints. This describes what was authorized and
  what was performed.
- **The runtime**: which replaceable session or workspace currently stands
  behind a stable role or assignment ID, and when each was last observed
  alive.

The first two are durable facts. The third is an observation with a time on
it, and it is the only layer a new session is entitled to distrust.

## The order a session resumes in

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

Four rules inside that order carry most of the weight:

- **Reconcile before proposing.** A session that proposes new work before it
  knows what is already running will duplicate it. Step 2 of the execution
  order exists for this.
- **Never infer approval from old discussion.** A conversation in which the
  owner sounded enthusiastic is not a grant. The grant is the recorded
  approval of an exact revision and digest, or there is none.
- **Adopt, do not relaunch.** A worker that is verifiably alive keeps its
  assignment. Starting a second worker on the same assignment is the failure
  this step prevents, and a duplicate message must never create a duplicate
  ticket or a duplicate worker.
- **An old session ID is not a live worker.** Liveness is checked against the
  actual process and workspace, with the time of the check recorded. A terminal
  that exists, or has gone idle, is never proof that work completed.

## Uncertainty is preserved, never resolved by optimism

An external operation that timed out after it may have been dispatched is
`uncertain`, not failed and not succeeded. It is read back against the provider
before anything is retried. Inventing a completion is worse than reporting that
the company does not know, because the invented one propagates.

Persisted check evidence is invalidated when its source revision moved. A green
verdict against a revision that no longer exists proves nothing about the one
that does.

## Pause

The owner can pause at any moment. Pausing:

- **fences new dispatches immediately** — nothing further starts;
- **asks active workers to stop safely** — a request, not a guarantee;
- **reports what is still in flight**, rather than claiming immediate
  cancellation.

Work that was mid-flight when the pause landed is reported as in flight. A
paused company is not a stopped one until the reports come back.

Resuming returns each active batch to its stored prior state, after
reconciliation, never straight into dispatch.

## Close

A session close records a checkpoint and pauses by default. It states what was
accomplished, what is unfinished, what is blocked, the next actions, and the
recovery point.

**A session ending does not complete a batch.** These are separate facts and a
closing brief that conflates them is wrong even when everything in it is true.

Abrupt termination cannot guarantee a closing summary at all. Recovery uses the
last durable event, which is why every transition commits with its event rather
than after it. **No session and no host running means work is paused, not
secretly continuing.**

## What this does not give you

Local records are not backup and not cross-machine durability. A company record
on one machine is one machine's worth of durability, and calling it more than
that is exactly the unenforced claim rule six forbids.

## Extended by

A1, which implements the ordered recovery, the reconcile adapters, the lifecycle
hooks and the interrupted-state tests, and proves adoption by killing a chief
during a running worker.
