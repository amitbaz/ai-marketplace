---
description: What Cabinet is, what each command and role does, and where this repository currently stands — which roles are hired, what is waiting on you, and what to run next.
argument-hint: "[command or role name for detail on one]"
---

# /cabinet:help

Load `Skill(skill: "cabinet:coordination-rules")` first — it is the workflow
this card describes, and the source of truth for what each role may do.

A reference card that knows where you are. Read state, print, dispatch
nothing — this command must stay cheap enough to run without thinking about
it. Never call a role, never query the board.

If `$ARGUMENTS` names one command or role, print only that one's entry with a
sentence on when to reach for it, and stop.

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

## 1. Read what exists

Look for `<memory>/` and, if present: which `<role>.md` notebooks exist (that
is who is hired), how many open items are in `decisions.md` and how long the
oldest has waited, how many entries `money.md` has open, and how many
proposals are standing in `proposals.md`. Check whether
`~/.cabinet/founder.md` exists.

Read only what you need for the counts. Do not summarize their contents.

## 2. Print

**Where you are** — first, and only if `<memory>/` exists:

```
Hired: <roles>            Open decisions: <n>, oldest <n> days
Open money items: <n>     Standing proposals: <n>
Charter written against <commit>, HEAD is <commit>
```

If `<memory>/` does not exist, say Cabinet is not set up here, that
`/cabinet:hire` sets it up by reading the repository rather than interviewing
you, and stop after the commands table. Nothing else applies yet.

**The commands**, with when to use each:

| Command | When |
| --- | --- |
| `/cabinet:hire` | Once per repository, and when the stage changes |
| `/cabinet:company` | Open the company. Diagnoses here; hands you the command that starts the chief |
| `/cabinet:batch` | Prepare or present the proposed batch. Approval happens in the chief |
| `/cabinet:standup` | Start of a working session. One brief, five items |
| `/cabinet:now` | What is in flight right now. Costs seconds, dispatches nobody |
| `/cabinet:decide <n> <answer>` | When you have an answer |
| `/cabinet:brief <#>` | Before starting a ticket — paste into that session |
| `/cabinet:check <#>` | Before a merge |
| `/cabinet:ask <role> <question>` | Pull one role into the room |
| `/cabinet:review` | Weekly. Every role runs its standing question |
| `/cabinet:charter` | Show or amend the charter as the company changes |
| `/cabinet:help` | This |

**The roles**, marked with whether each is hired here:

| Role | Standing question |
| --- | --- |
| `product` | What is the smallest thing that would tell us whether this is worth building? |
| `engineering` | What in this plan has not been checked against the actual code? |
| `qa` | What is green for the wrong reason? |
| `delivery-lead` | What is ordered wrong? |
| `architect` | What did we build that contradicts what we decided? |
| `design` | What does a person have to already know for this to work? |
| `brand` | Does what we shipped still sound like us? |
| `marketing` | Who is this for, and what would make them try it? |
| `cfo` | What is about to cost money, and what has a lead time? |
| `counsel` | What binds us now that did not bind us last month? |

Say in one line that a role is hired by having a notebook and fired by
deleting it, and that `/cabinet:hire <role>` adds one.

**The one thing that is never negotiable:**

> No agent here can spend your money, commit you to a cost, or change what you
> charge. Enforced by tool grants — roles hold no shell, no billing tools, and
> no write access. It does not extend to your other agents; `/cabinet:hire`
> offers a deny block for those.

**What to run next**, one line, chosen from what you read:

- Not set up: `/cabinet:hire`
- Set up, no notebook has entries yet: `/cabinet:standup`
- Decisions open longer than a few days: name the oldest, suggest
  `/cabinet:decide`
- No review in the last week: `/cabinet:review`
- A charter line whose condition has been met: `/cabinet:charter`

Pick one. A help screen that ends with five suggestions has told the owner
nothing.
