---
description: Pull one role into the room for a specific question — product on what to build next, engineering on how, QA on whether done holds, delivery on ordering, counsel on an obligation, the CFO on a cost, brand on a name, the architect on a spec, design on a flow, marketing on how anyone hears about it.
argument-hint: "<role> <question>"
---

# /cabinet:ask

Load `Skill(skill: "cabinet:coordination-rules")` first. It owns what a role
returns and who owns which answer; this command supplies the dispatch and the
recording.

## The roles you can ask for

The whole registry, not the advisory six. Each name is addressed as
`cabinet:<name>`.

| Core staff | What it owns |
| --- | --- |
| `product` | What the company should do next, for whom, and whether the evidence is real |
| `engineering` | How something is built, what it depends on, and what could go wrong |
| `qa` | Whether a claim of done holds, and what would have caught it if it did not |
| `delivery-lead` | What order work happens in, what blocks what, and what has stalled |

| On demand | What it owns |
| --- | --- |
| `architect` | Whether the plan still matches the system |
| `design` | How it looks and how a person moves through it |
| `brand` | What something is called, how it sounds, and what was already rejected |
| `marketing` | How anyone hears about it |
| `cfo` | What something costs and when the money is needed |
| `counsel` | What binds the company legally, and from when |

The chief of staff is not on this list. It is the session, not a role you ask.

`$ARGUMENTS` begins with one of those names, followed by the question. If the
first word is not a role name, infer the right role from the question, say
which one you picked and why in one line, and continue. If two roles both own
part of it, ask both and present both answers side by side rather than merging
them into one voice: the owner should be able to tell who said what.

## Which session you are in changes what happens afterwards

Call `mcp__cabinet__cabinet_doctor` first. It changes nothing, and `launch`
plus `lease` decide whether this run can record anything.

**In the chief's own session** — `launch: restricted` with a held lease — a
role's answer is company work. Dispatch it with the company context, and record
what it returns.

**In any ordinary session** — the normal case when the owner types this — the
role runs read-only against the public company views and the repository, its
answer is shown, and **nothing is written**. Say that in one line when you
report, so the owner knows the answer will not be there next week unless they
put it there. Do not work around it by writing the notebook file yourself: one
writer is what keeps parallel roles from racing on the same append, and a
second one appearing during an ordinary session is exactly the race.

## 1. Give the role its context

A role holds no shell and cannot derive where anything is. Hand it what it
needs and nothing more:

- The company context from `mcp__cabinet__cabinet_context`, which returns the
  charter and the company's documents with their revisions. Pass the `name` of
  a single document when the question is narrow, rather than the whole set.
- The current batch and its state from `mcp__cabinet__cabinet_snapshot`, when
  the question touches work in flight. Fetch it once and hand the same view to
  both roles if you are asking two — a role never re-derives what it was given,
  and two roles working from two snapshots produce a disagreement that is about
  the snapshots.
- The owner's question, verbatim. Do not rewrite it and do not add framing. A
  role's answer is worth less when it is answering a question the owner did
  not ask.

When the runtime is not reachable from this session, say so and fall back to
the public company views on disk. A thinner answer said to be thinner is fine;
a thin answer presented as a full one is not.

## 2. Dispatch

One role, one question. If the role's answer needs something from another role,
that is a handoff and it belongs to the chief's own session — say what the role
needs and who owns it, rather than quietly asking the second role yourself and
presenting a merged answer nobody is accountable for.

If a role names evidence its grant cannot reach — a price on a public page, a
name collision, a provider's terms — it says so and names exactly what it would
want checked. That is the correct behavior, not a failure. Report the gap; do
not fill it with something plausible.

## 3. Record — in the chief's session only

The role returns its sections and the chief records them. Route each one:

- `## NOTEBOOK` to that role's own notebook, newest first, dated. This matters
  most for brand and counsel: a proposal considered and rejected is only useful
  later if the reasoning and the reopening condition were written down while
  they were fresh.
- `## DECISIONS` to the decision record, attributed to the role, keeping the
  role's prediction of the owner's answer and its confidence alongside the
  item — that pairing is what `/cabinet:decide` scores later.
- `## MONEY` to the money ledger, with who raised it, the amount and the
  deadline.
- `## PROPOSALS` to the proposals record, each with the cost of not doing it or
  an explicit note that no cost was named.
- `## HANDOFFS` recorded before anything is sent, so that an unacknowledged one
  stays open rather than disappearing with the session.
- `## FOR <role>` to that role's notebook as inbound.

Nothing here reaches the owner because it was written down. What reaches them
is section 4.

## 4. Report

The role's answer, in its own voice, with its name on it. Then one line on what
was recorded — or, in an ordinary session, that nothing was.

The answer is written for the owner: a capability and what it costs, never the
mechanism. If the role's answer names a file, function or line number, that is
the one thing you rewrite — not its framing, not its conclusion, only its
vocabulary — and the mechanism stays in the notebook where the next run reads
it. A role that cannot say what its finding costs has not finished thinking;
say that plainly instead of passing the mechanism through.
