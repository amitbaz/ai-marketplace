---
description: Ask QA whether "done" actually holds for a ticket or pull request — whether a green check is green for the right reason, and whether anything actually gates the merge.
argument-hint: "<ticket or PR number>"
---

# /cabinet:check

Load `Skill(skill: "cabinet:coordination-rules")` first.

Run this before a merge, before closing a ticket, or whenever "it's green"
needs to mean something.

`$ARGUMENTS` is the ticket or pull request number. With no argument, check
every open pull request.

## Resolve the memory before anything else

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/memory-path <owner/repo>
```

Take `owner/repo` from `git remote get-url origin`. The script prints
`memory=<path>`; everything written below as `<memory>/...` is a file in that
directory, and **every role you dispatch is given that path in its prompt** —
roles hold no shell and cannot derive it, so a role not told the path cannot
read its own notebook.

If `exists=false`, this project has no Cabinet memory yet: say so, suggest
`/cabinet:hire`, and stop rather than improvising a picture without it.

If the output carries a `legacy_in_repo=` line, an old in-repo `.cabinet/` is
still sitting in the worktree from before the memory moved out. Say so in one
line and point at `/cabinet:hire`, which is the command that moves it. Do not
move it yourself: that directory is judgement, and relocating it is the
owner's call to make once, not a side effect of running a daily command.

## 1. Dispatch QA

Dispatch `cabinet:qa` for the named ticket or PR. It reads the suite, the CI
configuration, and the reported results — it has no shell and cannot run
anything, and it will say which of the three each conclusion came from.

## 2. Record

Append QA's `## NOTEBOOK` content to `<memory>/qa.md`, newest first, dated. A
known-hollow suite recorded once is caught by every later run; the same
discovery made weekly is wasted work.

Add anything from its `## DECISIONS` to `<memory>/decisions.md`, numbered and
dated, attributed to QA. Anything in `## MONEY` goes to `<memory>/money.md`
under open.

Route the rest of the role's sections too: `## PROPOSALS` into
`<memory>/proposals.md`, and each `## FOR <role>` into that role's notebook as
inbound. Keep the role's prediction of the owner's answer alongside any
decision item — that is what `/cabinet:decide` scores later.

## 3. Report

QA's verdict, unchanged: actually done, green but hollow, or not done — with
the specific mechanism named when hollow. Then, in one line each, any
known-hollow suite from the notebook that touches this change and is still
unfixed.

Do not soften the verdict. "Green but hollow" is the finding this role exists
to produce, and rewording it as a suggestion defeats the point.
