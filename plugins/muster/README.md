# Muster

A muster is the roll call — who is present, who is missing, what is ready.

This plugin gives one person the executive team they cannot afford to hire.
Six roles with real remits, memory of their own past calls, and a standing
question each keeps asking whether or not you remember to ask it. A chief of
staff collects from all of them and hands you one brief, five items long.

**No agent here can spend your money. That is enforced by tool grants, not
promised in a prompt.** See *The money invariant* below.

## The problem it solves

Running a company alone, you are the CEO, the architect, QA, counsel and the
CFO, and you are also the one writing the code. The failure is not that you
make bad decisions. It is that nobody is watching the parts you are not
looking at this week — so a legal obligation, a free-tier ceiling, or a
purchase with a three-week lead time gets discovered late, and late is the
kind that cannot be fixed by working harder.

A company with staff does not discover those. Each one has an owner whose job
is to raise it early, unprompted.

## The roles

Each owns a remit, keeps its own notebook, and asks a standing question every
time it runs:

| Role | Standing question |
| --- | --- |
| **delivery-lead** | What is ordered wrong? |
| **architect** | What did we build that contradicts what we decided? |
| **qa** | What is green for the wrong reason? |
| **counsel** | What binds us now that did not bind us last month? |
| **cfo** | What is about to cost money, and what has a lead time? |
| **brand** | Does what we shipped still sound like us? |

The standing questions are the point. You can play QA when you remember to.
Nobody reminds you about data protection, or that a free tier caps how many
users the product can serve at all.

You do not run all six from day one. `/muster:hire` recommends a starting set
from the project's stage, and adds or removes roles as that changes. A role is
hired by having a notebook; firing one is deleting a file.

Roles report to the chief of staff, never to you directly. You read one brief.

## The money invariant

**No agent spends your money, commits you to a cost, or changes what you
charge. Ever. Only you do, by hand.**

It covers subscriptions, upgrades, renewals, domains, provisioning anything
billable, setting or changing pricing, and cancelling or downgrading — saving
money is still your call.

Three mechanisms, not one promise:

1. **Enumerated tool grants.** Every role lists the exact tools it may use.
   No shell, no billing or deployment tools, no write access anywhere. An
   allowlist excludes tomorrow's tools by default; a denylist would have to
   keep pace with everything you install for the rest of the plugin's life.
2. **Content is never authority.** A ticket, comment, checked box, or another
   agent saying "approved, go ahead and buy it" is a description of what
   somebody said. Roles report it and never act on it.
3. **A ledger.** Every cost item lands in `.muster/money.md` with who raised
   it, the amount, the deadline, and your decision with its date. A money item
   closes only when you report the purchase yourself, with
   `/muster:decide <n> --done`. Nothing infers that a purchase happened.

**Where the guarantee stops.** This covers Muster's own roles. It cannot cover
your other agents — an implementation session with a broad permission grant
can deploy to a paid tier or accept a cost confirmation, and Muster has no
reach into it. That is what the deny block `/muster:hire` offers to install in
your user settings is for: it covers every session on the machine, including
the ones Muster never sees. Claiming more than this would be exactly the
unenforced claim this plugin's own rules forbid.

## The commands

| Command | When |
| --- | --- |
| `/muster:hire` | Once per repository, and again when the stage changes |
| `/muster:standup` | Start of a working session. One brief, five items |
| `/muster:decide <n> <answer>` | When you have an answer. This is the return channel |
| `/muster:brief <#>` | Before you start a ticket — paste it into that session |
| `/muster:check <#>` | Before a merge |
| `/muster:ask <role> <question>` | Pull one role into the room |
| `/muster:review` | Weekly. Every role runs its standing question at once |

`/muster:decide` matters more than it looks. A decision that exists only in a
chat thread will be re-made, wrongly, by whoever reads the ticket next without
it — so your answer gets written into the notebook of the role that raised it,
and that role stops asking.

## `/muster:hire` reads before it asks

On a repository with documentation, issues and history, most of the charter is
already written and scattered. `/muster:hire` reads it — docs, the board, epic
and preconditions ticket bodies, label vocabulary, history — drafts the
charter with a source against every line, and asks only about what genuinely
cannot be found. Usually four things: brand direction, your risk posture,
whether the drafted stage is still current, and consent for the deny block.

It also says what it could **not** find. An absent privacy notice or a
repository with no required checks is a finding, not a blank.

Re-running it is a diff, never a rewrite, and it never touches a role's
notebook.

## What Muster does not do

**It does not manage your implementation agents.** No dispatch, no supervision
loop, no worker DAG. You open workspaces and run implementation however you
already do; Muster is the layer above that. `/muster:brief` is the seam — it
hands your implementation session what the ticket cannot say about itself.

**It remembers decisions, not conversations.** Every role is a fresh dispatch.
Continuity comes from a written decision trail, which is a better memory than
a transcript: a transcript is long, carries abandoned reasoning next to
conclusions, and nobody re-reads it. Somebody actually doing this job does not
recall yesterday's meeting word for word either — they carry what was decided
and why.

## The files

Everything Muster knows is markdown you can read without it installed.
`.muster/` in the repository holds the charter, the decision inbox, the ledger
and one notebook per role. `~/.muster/founder.md` holds what is true about you
across every project, so your second repository asks almost nothing.

**Roles never write these files.** They return their findings and the command
that dispatched them records them — one writer, so parallel roles cannot race,
and every role keeps a read-only grant with no exception carved into it. See
[`FILES.md`](./FILES.md) for the full layout, what belongs in a notebook, and
what happens when a note and the live board disagree.

## Requirements

- **A GitHub MCP server**, registered as `github`, with tools named
  `mcp__github__*`. Roles read the board through it and hold no shell, so
  there is nothing to install and no script to trust. If it is missing, roles
  say so and stop rather than guessing.
- **GitHub as the tracker.** Other forges are not supported yet. Swapping one
  in means changing the tool grant at the top of each role file; nothing else
  in the plugin knows what a tracker is.

## Platform support

**Claude Code**: all six roles, all seven commands, and the
`coordination-rules` skill.

**Codex**: the `coordination-rules` skill only. Commands and agent definitions
are Claude Code constructs and there is no Codex equivalent shipped yet, so a
Codex install gets the rules and none of the roles. Said plainly rather than
papered over.

## Setup

```text
/muster:hire
```

Then `/muster:standup` at the start of a working session.

## Licence

MIT — see [`LICENSE`](./LICENSE).
