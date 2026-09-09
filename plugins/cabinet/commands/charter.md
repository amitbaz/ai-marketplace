---
description: Show or amend the company charter. Reports which lines have outgone their conditions and what the roles have proposed changing, and records every amendment with the line it replaced. Roles propose; only the owner amends.
argument-hint: "[what to change, in your own words]"
---

# /cabinet:charter

Load `Skill(skill: "cabinet:coordination-rules")` first.

A company does not stay the way it was described on its first day, so neither
does `<memory>/company.md`. This command is how it changes — with a history, so
that anyone reading it later can see what moved and when.

Roles propose amendments. Only the owner makes them. That is not ceremony:
every role reads this file before forming an opinion, so a role editing it
could quietly rewrite its own instructions.

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

## With no arguments — show the charter and its health

1. Read `<memory>/company.md`. Missing: say so, suggest `/cabinet:hire`, stop.
2. **Check every line's ending condition against reality.** Each line carries
   a source and, where it can go stale, an "Ends when" condition. Use the
   board and the repository to check each one. Report three states per line:
   holding, **condition met** (the line is now wrong and needs the owner), or
   unverifiable from here — say which, never assume holding.
3. **Report age.** Name the commit and date each line was written against, and
   how far the repository has moved since. Drift being visible is the point;
   a charter that looks permanent is one nobody re-checks.
4. **Show what the roles have proposed.** Read `<memory>/proposals.md` for
   entries marked as charter amendments — a role saying the owner's decisions
   have repeatedly contradicted a stated line. Present the evidence each role
   gave.
5. **Point out what is missing for this stage.** A pre-launch charter has no
   pricing section, no support policy, and no incident practice. It will need
   them. If the stage has moved past what the charter's shape covers, say
   which sections are now absent rather than waiting to be asked.

## With arguments — amend it

`$ARGUMENTS` is what the owner wants changed, in their own words.

1. **Find the line or section it affects.** If it is ambiguous, ask which one
   rather than guessing — an amendment applied to the wrong line is worse than
   no amendment, because every role will read it as settled.
2. **Never overwrite.** The superseded line stays, marked superseded, with its
   date and the reason it changed. Write the new line above it with today's
   date, its source (the owner, this decision), and its own ending condition
   if it has one. Ask for that condition if the owner did not give one and the
   line is the kind that can go stale.
3. **Append to the amendment log** at the end of the file: date, what changed,
   from what to what, and why in the owner's words.
4. **Say what this reopens.** A charter line rarely changes alone. Name the
   notebook entries and open decisions that were conditioned on the old line,
   and put them in front of the owner rather than silently letting them stand.
   For a **stage** change, say so prominently and recommend `/cabinet:review`,
   so every role re-runs its standing question against the new stage.
5. If the amendment came from a role's proposal, mark that proposal accepted
   in `<memory>/proposals.md` and credit the role in the log. A role whose
   proposals are never acknowledged learns nothing about whether it is useful.

## Adding a section

The charter's shape is not fixed at six fields. When the owner asks for
something the current shape has no home for — a pricing policy, a support
commitment, a hiring plan — add the section, and note in the log that it was
added and at what stage. That record is what makes it possible to see the
company growing rather than just a file changing.

## Report

Short. What changed, what it reopened, and what the owner should do next
(usually `/cabinet:review` if the stage moved, nothing otherwise).

Never print the whole charter after an amendment. Print the line that changed
and the line it replaced.
