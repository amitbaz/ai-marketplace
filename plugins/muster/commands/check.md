---
description: Ask QA whether "done" actually holds for a ticket or pull request — whether a green check is green for the right reason, and whether anything actually gates the merge.
argument-hint: "<ticket or PR number>"
---

# /muster:check

Load `Skill(skill: "muster:coordination-rules")` first.

Run this before a merge, before closing a ticket, or whenever "it's green"
needs to mean something.

`$ARGUMENTS` is the ticket or pull request number. With no argument, check
every open pull request.

## 1. Dispatch QA

Dispatch `muster:qa` for the named ticket or PR. It reads the suite, the CI
configuration, and the reported results — it has no shell and cannot run
anything, and it will say which of the three each conclusion came from.

## 2. Record

Append QA's `## NOTEBOOK` content to `.muster/qa.md`, newest first, dated. A
known-hollow suite recorded once is caught by every later run; the same
discovery made weekly is wasted work.

Add anything from its `## DECISIONS` to `.muster/decisions.md`, numbered and
dated, attributed to QA. Anything in `## MONEY` goes to `.muster/money.md`
under open.

## 3. Report

QA's verdict, unchanged: actually done, green but hollow, or not done — with
the specific mechanism named when hollow. Then, in one line each, any
known-hollow suite from the notebook that touches this change and is still
unfixed.

Do not soften the verdict. "Green but hollow" is the finding this role exists
to produce, and rewording it as a suggestion defeats the point.
