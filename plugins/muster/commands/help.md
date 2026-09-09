---
description: What Muster is, what each command and role does, and where this repository currently stands — which roles are hired, what is waiting on you, and what to run next.
argument-hint: "[command or role name for detail on one]"
---

# /muster:help

A reference card that knows where you are. Read state, print, dispatch
nothing — this command must stay cheap enough to run without thinking about
it. Never call a role, never query the board.

If `$ARGUMENTS` names one command or role, print only that one's entry with a
sentence on when to reach for it, and stop.

## 1. Read what exists

Look for `.muster/` and, if present: which `<role>.md` notebooks exist (that
is who is hired), how many open items are in `decisions.md` and how long the
oldest has waited, how many entries `money.md` has open, and how many
proposals are standing in `proposals.md`. Check whether
`~/.muster/founder.md` exists.

Read only what you need for the counts. Do not summarize their contents.

## 2. Print

**Where you are** — first, and only if `.muster/` exists:

```
Hired: <roles>            Open decisions: <n>, oldest <n> days
Open money items: <n>     Standing proposals: <n>
Charter written against <commit>, HEAD is <commit>
```

If `.muster/` does not exist, say Muster is not set up here, that
`/muster:hire` sets it up by reading the repository rather than interviewing
you, and stop after the commands table. Nothing else applies yet.

**The commands**, with when to use each:

| Command | When |
| --- | --- |
| `/muster:hire` | Once per repository, and when the stage changes |
| `/muster:standup` | Start of a working session. One brief, five items |
| `/muster:decide <n> <answer>` | When you have an answer |
| `/muster:brief <#>` | Before starting a ticket — paste into that session |
| `/muster:check <#>` | Before a merge |
| `/muster:ask <role> <question>` | Pull one role into the room |
| `/muster:review` | Weekly. Every role runs its standing question |
| `/muster:charter` | Show or amend the charter as the company changes |
| `/muster:help` | This |

**The roles**, marked with whether each is hired here:

| Role | Standing question |
| --- | --- |
| `delivery-lead` | What is ordered wrong? |
| `architect` | What did we build that contradicts what we decided? |
| `qa` | What is green for the wrong reason? |
| `counsel` | What binds us now that did not bind us last month? |
| `cfo` | What is about to cost money, and what has a lead time? |
| `brand` | Does what we shipped still sound like us? |

Say in one line that a role is hired by having a notebook and fired by
deleting it, and that `/muster:hire <role>` adds one.

**The one thing that is never negotiable:**

> No agent here can spend your money, commit you to a cost, or change what you
> charge. Enforced by tool grants — roles hold no shell, no billing tools, and
> no write access. It does not extend to your other agents; `/muster:hire`
> offers a deny block for those.

**What to run next**, one line, chosen from what you read:

- Not set up: `/muster:hire`
- Set up, no notebook has entries yet: `/muster:standup`
- Decisions open longer than a few days: name the oldest, suggest
  `/muster:decide`
- No review in the last week: `/muster:review`
- A charter line whose condition has been met: `/muster:charter`

Pick one. A help screen that ends with five suggestions has told the owner
nothing.
