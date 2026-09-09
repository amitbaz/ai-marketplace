---
description: The weekly board meeting. Every hired role runs its standing question against the whole board at once, and the chief of staff reports what came out of it. Run weekly, or before a push.
argument-hint: "[no arguments]"
---

# /muster:review

Load `Skill(skill: "muster:coordination-rules")` first.

`/muster:standup` is a daily brief built mostly from memory. This is the
opposite: every role looks at the whole board at once and asks the question it
owns, whether or not anyone raised it.

This is where a launch-preconditions document gets written continuously, a few
findings at a time, instead of once in a panic. Running it weekly is the
difference between discovering a precondition early and discovering it late,
and the late ones are the expensive ones.

## 1. Read the memory first

`.muster/company.md`, `~/.muster/founder.md`, `.muster/decisions.md`,
`.muster/money.md`, `.muster/proposals.md`, and every notebook. Missing
charter: say so, suggest `/muster:hire`, and stop.

## 2. Run every hired role in parallel

Dispatch every role that has a notebook, at once, each on its own standing
question:

- **delivery-lead** — what is ordered wrong?
- **architect** — what did we build that contradicts what we decided?
- **qa** — what is green for the wrong reason?
- **counsel** — what binds us now that did not bind us last month?
- **cfo** — what is about to cost money, and what has a lead time?
- **brand** — does what we shipped still sound like us?

Do not hand them a topic. The standing question against the current board is
the whole instruction; narrowing it to what you already suspect is how a
review turns into a confirmation of what you already knew.

Wait for all of them before writing anything. Reacting to the first report
turns the later ones into footnotes, and the value of running six roles is
precisely that they disagree.

## 3. Each role reviews its own record

Before reporting, every role reads its own calibration record — what it
predicted the owner would decide, against what the owner actually decided —
and its own last few entries against what has since happened.

Two questions, answered honestly:

- What did I raise that turned out not to matter?
- What did I miss that I should have caught?

A role that has been consistently wrong about this owner says so and changes
how it decides what to raise. This is the mechanism that makes the brief
shorter over time instead of longer: a role that knows the owner will decline
something notes it rather than asking.

Report a role's self-assessment in one line, not a paragraph. It is a
correction to how it works, not an apology.

## 4. Proposals — the once-a-week airing

Read `.muster/proposals.md` in full. This is the only command that does.

Surface the two or three worth the owner's attention, ranked by the cost of
not doing them. For the rest, name the count.

Any proposal that has gone several reviews without an answer gets raised once
more with an explicit question — take it up or drop it — and then withdrawn by
its author, with the reason recorded. A file that only ever grows is a file
nobody opens.

`## FOR charter` proposals are read here too: a role saying a charter line no
longer matches how the owner actually decides. Present the evidence, and point
at `/muster:charter` — roles propose, only the owner amends.

## 5. Re-check what the stage conditioned

Every judgement recorded while the project was at an earlier stage was correct
only while that stage held. If the charter's stage line has changed since a
notebook entry was written, list the entries that the change reopens. Do not
re-decide them; name them and put them in front of the owner.

## 6. Write back

Append each role's `## NOTEBOOK` content to its own file, newest first, dated.
Add `## DECISIONS` items to `.muster/decisions.md`, numbered, dated,
attributed, with each role's prediction of the owner's answer kept alongside
it. Numbers only ever go up: never renumber an open item, never reuse a closed
one's number. Add `## MONEY` items to `.muster/money.md` under open, updating
days-open rather than duplicating anything already there. Add `## PROPOSALS`
items to `.muster/proposals.md`, and route `## FOR <role>` sections into the
receiving roles' notebooks as inbound.

## 7. Report

One block per role, its standing question and what it found, in its own voice
with its name on it. Then the chief of staff's own line: which two or three of
these belong in front of the owner at the next standup, and which are tracked.

```
BOARD REVIEW · <date>

 <ROLE> — <its standing question>
  · <finding>

 ...

 PROPOSALS: <n> standing, <n> new. Worth your attention: <the ranked few>.

 CHIEF OF STAFF: <n> items I would put in front of you next. The rest is
 tracked.
```

Never merge two roles' findings into one voice. Two roles reaching the same
conclusion independently is itself a finding, and saying so is more useful
than presenting it once.
