---
description: Pull one role into the room for a specific question — counsel on an obligation, the CFO on a cost, brand on a name, the architect on a spec, QA on a suite, the delivery lead on ordering.
argument-hint: "<role> <question>"
---

# /cabinet:ask

Load `Skill(skill: "cabinet:coordination-rules")` first.

`$ARGUMENTS` begins with a role name — `delivery-lead`, `architect`, `qa`,
`counsel`, `cfo`, or `brand` — followed by the question.

If the first word is not a role name, infer the right role from the question,
say which one you picked and why in one line, and continue. If two roles both
own part of it, ask both and present both answers side by side rather than
merging them into one voice: the owner should be able to tell who said what.

## 1. Snapshot the board, unless the question is narrower than the board

Most questions worth asking a role are about the board — what to start next,
what is ordered wrong, what is about to bind us. Those need the whole board,
and a role holds no shell to fetch it quickly. So unless the question names one
specific ticket or pull request, run

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/board-snapshot <owner/repo>
```

first, show the counts it prints on one line, and pass `board=` — plus `epics=`
when the question touches ordering or what was already decided — in the
dispatch prompt.

Skip it when the question is genuinely about one thing the role can read
directly. Fetching the whole board to answer a question about a single pull
request is its own kind of waste.

## 2. Dispatch

Dispatch the role with the owner's question verbatim. Do not rewrite it, and
do not add your own framing — a role's answer is worth less when it is
answering a question the owner did not ask.

If the role has not been hired — no `.cabinet/<role>.md` exists — say so, and
offer `/cabinet:hire <role>`. Do not answer on the role's behalf: an
unaccountable answer with a role's name on it is worse than no answer.

## 3. Record

Append the role's `## NOTEBOOK` content to its own file, newest first, dated.
This matters most for brand: a proposal considered and rejected is only useful
later if the reasoning and the reopening condition were written down when they
were fresh.

Add `## DECISIONS` items to `.cabinet/decisions.md` and `## MONEY` items to
`.cabinet/money.md`, both attributed to the role.

Route the rest of the role's sections too: `## PROPOSALS` into
`.cabinet/proposals.md`, and each `## FOR <role>` into that role's notebook as
inbound. Keep the role's prediction of the owner's answer alongside any
decision item — that is what `/cabinet:decide` scores later.

## 4. Report

The role's answer, in its own voice, with its name on it. Then one line on
what was recorded, so the owner knows the answer will still exist next week.

The answer is written for the owner: a capability and what it costs, never the
mechanism. If the role's answer names a file, function or line number, that is
the one thing you rewrite — not its framing, not its conclusion, only its
vocabulary — and the mechanism stays in its notebook where the next run reads
it. A role that cannot say what its finding costs has not finished thinking;
say that plainly instead of passing the mechanism through.
