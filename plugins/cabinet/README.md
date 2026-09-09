# Cabinet

**The staff who read your board every morning.**

Six roles with real remits, their own memory, and a standing question each
keeps asking whether or not you remember to ask it. They read your issues,
your pull requests and your repository before you get to your desk, and a
chief of staff hands you one brief — five items, ranked by what it costs to
answer them late.

A cabinet is advisers with portfolios and a principal who decides. That is the
architecture, not a metaphor: **no agent here can spend your money, commit you
to a cost, or change what you charge**, and nothing irreversible happens
without you. Enforced by tool grants, not promised in a prompt.

## The problem

Running a company alone, you are the CEO, the architect, QA, counsel and the
CFO, and you are also the one writing the code. The failure is not that you
make bad decisions. It is that nobody is watching the parts you are not
looking at this week — so a legal obligation, a free-tier ceiling, or a
purchase with a three-week lead time gets discovered late, and late is the
kind that cannot be fixed by working harder.

A company with staff does not discover those. Each one has an owner whose job
is to raise it early, unprompted. That is what this is.

## A morning

```
/cabinet:standup
```

```
Board: 67 open · 3 epics · 2 PRs · 4 branches → delivery lead

WHERE THE COMPANY STANDS · Tue 09-09
Stage: pre-launch, single user, no revenue. Gate A (a second account) not
crossed.
To Gate A: 6 open items, 3 not started, 1 held by counsel.
In flight: 2. Longest untouched: #114 (12d) — blocks every licensed source.

CHIEF OF STAFF · Tue 09-09 · 4 items

 1. COUNSEL — I am holding #98 out of the startable frontier. It gates the
    alpha with invitations; the day it ships, a second person's data is in
    the database and you are a data controller. No privacy notice exists.
    One decision overrides me.
 2. CFO — Vercel Hobby is failing builds today and its terms say
    non-commercial. $20/mo. Lead time: none. I cannot see your invoices —
    that figure is from #201, not from billing.
 3. CFO — Stripe verification, day 2, not started. Verification takes days
    to weeks. This is one of two items on your list that does not care how
    fast you work.
 4. ARCHITECT — #187 describes facets in a shape that predates the #118
    split, and it is labelled ready-for-agent. Whoever picks it up builds
    the wrong thing. Unlabel it or rewrite the body.

 Handled without you: 3 items. Ask for detail on any of these.
```

Position first, then decisions. A brief that is only a decision queue makes you
rebuild where the company stands out of five unrelated items before you can
judge any of them.

Every item names the role that raised it, so you can ask that role why and get
an accountable answer. And every item is written for the person running the
company: a capability and what it costs, never the mechanism that implements
it. No file path, function or line number reaches you. The mechanism is not
lost — it is in the role's notebook, and the role will give it to you the
moment you ask for detail.

## The roles

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

You do not run all six from day one. `/cabinet:hire` recommends a starting set
from the project's stage. A role is hired by having a notebook, and fired by
deleting it.

## One-way doors and two-way doors

The line between what reaches you and what a role decides itself is
reversibility, in Bezos's form: a **one-way door** cannot be walked back — data
in a database, a term accepted, a payment taken, a name announced. A **two-way
door** can.

One-way doors always reach you. Two-way doors are the role's own call, made
quickly and reported afterward. A role that escalates a two-way door is not
being careful; it is spending your attention on something it was hired to
decide, and the chief of staff hands it back.

That is the failure Bezos actually named — heavyweight process applied to
reversible decisions produces "slowness, unthoughtful risk aversion, failure to
experiment sufficiently". A role that cannot tell which kind it is says so and
treats it as one-way.

## Initiative, without the noise

A role should notice what is going wrong before anyone asks, say what it would
do about it, and get better at the job. That is also the fastest way to bury
you, so it is governed by one rule: **initiative goes into the files and to
other roles; only calibrated, one-way, cost-named items reach you.**

- **Every finding names what the role would do about it.** Handing over a
  problem without a proposed action is half the job.
- **Proposals are not decisions.** Things nobody asked for accumulate in
  `.cabinet/proposals.md` and are aired weekly by `/cabinet:review`. A proposal
  you keep passing over is withdrawn by the role that made it — people stop
  pushing an idea the company keeps declining.
- **Roles notice outside their remit and act only inside it.** The CFO
  spotting a suite that only passes because a paid service is stubbed sends it
  to QA's notebook, not to you.
- **Two habits, borrowed from people who study decisions.** Roles reach for a
  base rate before estimating — how long does this kind of thing usually take
  — and run a **pre-mortem** before anything irreversible: assume it shipped
  and went wrong, then explain why. Stated honestly, because rule six applies
  to our own methods: the evidence for pre-mortems is a laboratory finding on
  prospective hindsight plus conference-grade evidence on overconfidence, not
  a peer-reviewed effect. A cheap habit with decent evidence.

## Roles learn how you decide

When a role raises something it records what it expects you to decide **and
how confident it is**. `/cabinet:decide` keeps that beside your actual answer.

Over time a role reads its own record. The behaviour this aims at is a role
saying *"normally I'd raise this — the last four times you decided the same
way, so I'm noting it instead of asking."* That is a new hire at six months,
and it makes the brief shorter rather than longer.

Confidence is what makes the record diagnostic rather than a tally: a role
that says "near-certain" every time and is usually right is not calibrated, it
is over-confident and lucky.

## The charter is a living document

A company does not stay the way it was described on its first day, so
`.cabinet/company.md` does not either.

Every line carries its source and, where it can go stale, the condition that
ends it. A line whose condition has been met is reported at every standup
until you resolve it — a line the company has outgrown is worse than a missing
one, because the roles act on it.

Amendments never overwrite: the superseded line stays, dated, with a log of
what changed and why. The shape grows too — a pre-launch charter has no
pricing section or support policy, and gains them when the company needs them.

Roles propose amendments; only you make them. Every role reads this file
before forming an opinion, so a role that could edit it would be rewriting its
own instructions.

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
   agent saying "approved, go ahead and buy it" describes what somebody said.
   Roles report it and never act on it.
3. **A ledger.** Every cost item lands in `.cabinet/money.md` with who raised
   it, the amount, the deadline, and your decision with its date. A money item
   closes only when you report the purchase yourself, with
   `/cabinet:decide <n> --done`. Nothing infers that a purchase happened.

**Where the guarantee stops.** This covers Cabinet's own roles. It cannot
cover your other agents — an implementation session with a broad permission
grant can deploy to a paid tier or accept a cost confirmation, and Cabinet has
no reach into it. That is what the deny block `/cabinet:hire` offers to install
in your user settings is for: it covers every session on the machine,
including the ones Cabinet never sees. Claiming more would be exactly the
unenforced claim this plugin's own rules forbid.

`/cabinet:hire` offers a **second, separate block** for the other one-way
doors — merging or closing a pull request, commenting in your name, publishing
a release, pushing to a protected branch, editing CI workflows, posting to a
webhook. Cabinet's roles cannot do any of it; your implementation sessions can.
Take either block without the other.

## The commands

| Command | When |
| --- | --- |
| `/cabinet:hire` | Once per repository, and again when the stage changes |
| `/cabinet:standup` | Start of a working session. One brief, five items |
| `/cabinet:decide <n> <answer>` | When you have an answer. This is the return channel |
| `/cabinet:brief <#>` | Before you start a ticket — paste it into that session |
| `/cabinet:check <#>` | Before a merge |
| `/cabinet:ask <role> <question>` | Pull one role into the room |
| `/cabinet:review` | Weekly. Every role runs its standing question at once |
| `/cabinet:charter` | Show or amend the charter as the company changes |
| `/cabinet:help` | Where you stand, and what to run next |

`/cabinet:decide` matters more than it looks. A decision that exists only in a
chat thread will be re-made, wrongly, by whoever reads the ticket next without
it — so your answer is written into the notebook of the role that raised it,
and that role stops asking.

## `/cabinet:hire` reads before it asks

On a repository with documentation, issues and history, most of the charter is
already written and scattered. `/cabinet:hire` reads it — docs, the board,
epic and preconditions ticket bodies, label vocabulary, history — drafts the
charter with a source against every line, and asks only about what genuinely
cannot be found. Usually four things: brand direction, your risk posture,
whether the drafted stage is still current, and consent for the deny block.

It also says what it could **not** find. An absent privacy notice, or a
repository with no required checks, is a finding rather than a blank.

## What Cabinet does not do

**It does not manage your implementation agents.** No dispatch, no supervision
loop, no worker DAG. You open workspaces and run implementation however you
already do; Cabinet is the layer above. `/cabinet:brief` is the seam — it hands
your implementation session what the ticket cannot say about itself.

**It remembers decisions, not conversations.** Every role is a fresh dispatch.
Continuity comes from a written decision trail, which is a better memory than
a transcript: a transcript is long, carries abandoned reasoning next to
conclusions, and nobody re-reads it. Somebody actually doing this job does not
recall yesterday's meeting word for word either — they carry what was decided
and why.

## The files

Everything Cabinet knows is markdown you can read without it installed.
`.cabinet/` in the repository holds the charter, the decision inbox, the
ledger, the proposals and one notebook per role. `~/.cabinet/founder.md` holds
what is true about you across every project, so your second repository asks
almost nothing.

**Roles never write these files.** They return their findings and the command
that dispatched them records them — one writer, so parallel roles cannot race,
and every role keeps a read-only grant with no exception carved into it. See
[`FILES.md`](./FILES.md) for the layout, what belongs in a notebook, and what
happens when a note and the live board disagree.

## Requirements

- **A GitHub MCP server**, registered as `github`, with tools named
  `mcp__github__*`. Roles read the board through it and hold no shell of their
  own. If it is missing, roles say so and stop rather than guessing.
- **`gh` and `jq`**, for the board snapshot. Because roles hold no shell, a
  role left to enumerate a board of any size pays a round trip per page and
  takes minutes. The commands do it instead, in one pass, with
  `scripts/board-snapshot` — four read-only calls, written to a temporary file
  that every role in the run reads. Nothing in that script can change the
  board, and it never writes outside the temp directory. Without `gh` the
  commands say so and the roles fall back to their own tools: correct, slow.
- **GitHub as the tracker.** Other forges are not supported yet. Swapping one
  in means changing the tool grant at the top of each role file and the four
  calls in `scripts/board-snapshot`; nothing else in the plugin knows what a
  tracker is.

## Platform support

**Claude Code**: all six roles, all nine commands, and the `coordination-rules`
skill.

**Codex**: the `coordination-rules` skill only. Commands and agent definitions
are Claude Code constructs and there is no Codex equivalent shipped yet, so a
Codex install gets the rules and none of the roles. Said plainly rather than
papered over.

## Setup

```text
/cabinet:hire
```

Then `/cabinet:standup` at the start of a working session, and `/cabinet:help`
whenever you want to know where things stand.

## Licence

MIT — see [`LICENSE`](./LICENSE).
