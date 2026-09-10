# The files Cabinet keeps

Every role in this plugin is a fresh dispatch: a new context each run, no
memory of the last one. The files below are the memory. They are also the
whole of Cabinet's state — there is no database, no cache, and nothing you
cannot read in a text editor with the plugin uninstalled.

## Two layers, and why

```
~/.cabinet/founder.md                    about the person
~/.cabinet/repos/<owner>-<repo>/         about one project
  company.md                            the charter, and its amendment log
  decisions.md                          the open queue and its history
  money.md                              the ledger
  proposals.md                          what the roles suggested that nobody
                                        asked for
  <role>.md                             one notebook per hired role, plus that
                                        role's inbound notes and calibration
                                        record
```

`founder.md` holds what is true across every project the owner runs: how they
work, their risk posture, what they will never compromise, and that they are
the only one who spends money. Written once. The second repository they set up
asks almost nothing, because only the project half is new.

`repos/<owner>-<repo>/` holds one project. Under `repos/` so it cannot collide
with `founder.md` or anything else that lands at that root later.

**Neither is inside the repository, and that is the point.** Decisions get made
in one session and acted on in a different worktree. Memory kept in the
repository only crosses that gap through a commit and a push, so every decision
cost a round trip before anything could act on it — and a `.cabinet/` that had
been gitignored, which is what happened in practice, never crossed at all.
Outside the worktree, every session on the machine reads the same files
immediately, with nothing to push.

**A role is told this path; it cannot find it.** Roles hold no shell, so they
can neither expand `~` nor derive the slug, and they cannot read the charter to
learn the location because the charter is the file at the end of the path. The
dispatching command resolves it with `scripts/memory-path` and passes
`memory=<path>` in the prompt, exactly as it passes `board=`.

## What moving it gave up

Stated rather than quietly dropped, because this document used to claim the
opposite. Memory in the repository was **committed, diffable, readable without
this plugin installed, and survived a fresh clone.** Outside it, none of those
hold: `~/.cabinet/` is a plain directory with no history, nothing to restore
from after a deletion, and no visibility from any other machine.

For one person on one machine that costs nothing today, which is why the move
was worth making. A teammate, or a second machine, starts blank. What should
replace those four properties is an open design question that has been
deliberately deferred rather than answered — so nothing here claims a
durability that does not exist. Rule six applies to this file first.

## The files that are not memory

```
$TMPDIR/cabinet-board-<owner>-<repo>.json              the board, as of a moment
$TMPDIR/cabinet-epics-<owner>-<repo>.json              the epic bodies, same moment
$TMPDIR/cabinet-charter-sources-<owner>-<repo>.json    what carries decisions
$TMPDIR/cabinet-charter-discussion-<owner>-<repo>.json comments, same moment
```

A role holds no shell — that is what makes the money invariant structural — so
a role asking the board a question pays a network round trip per page of
tickets, and another for every body it reads. The commands do have a shell, so
they fetch once and hand roles a file.

`scripts/board-snapshot` takes the board for `standup`, `review`, `ask` and
`now`. Epic bodies are split into their own file because they are usually most
of the bytes and only ordering work reads them.

- `scripts/local-sessions` — Enumerates every worktree of this repository on
  this machine and attributes each to a ticket from evidence on disk, so the
  delivery lead can see work that was never pushed. Passed to roles as
  `sessions=`.
- `commands/now.md` — `/cabinet:now`. What is in flight and what merged since
  the last standup. Reads only: no roles dispatched, nothing written.

`scripts/charter-sources` is for `/cabinet:hire`, and gathers the places where
decisions actually get recorded rather than where work does: issues closed as
*not planned*, merged `docs:` pull requests, comments on open tickets, and an
inventory of every tracked markdown file split into read, skip, and
matched neither. Hire drafted charters from the open board and the top-level
documentation alone for as long as it existed, which came out confidently
incomplete and looked finished either way.

All four are the opposite of a notebook and are treated as such. They are
derivable state, so nothing in them is ever copied into one; they live outside
the repository so they cannot be committed by accident; they carry a `taken_at`
because they describe one moment and not the present; and deleting them costs
nothing, because the next run takes another.

## The runtime, and what it keeps private

The advisory roles above need none of this. It exists for the operating
company: one lead process, a transactional record of what was agreed, and a
single typed writer instead of prose commands editing Markdown.

```
plugins/cabinet/
  .mcp.json                     the ordinary connection: read-only diagnosis
  scripts/cabinet-service       the stdio server both connections start
  scripts/cabinet-launch        writes a private launch, then starts the chief
  scripts/cabinet-hook          the mechanical dispatch and recipient check
  scripts/cabinet_runtime/
    rpc.py                      protocol, owner dialog, worker pool
    service.py                  the named operations and their schemas
    store.py, approval.py, policy.py, profiles.py, processes.py, …
~/.cabinet/repos/<owner>-<repo>/
  runtime/                      the database, launch profiles, backups
  views/                        the same company, as Markdown anyone can read
```

Two of those lines carry the boundary. `runtime/` is **not** an agent-readable
directory: it holds the database, the generated launch profiles and the
per-launch capability, and every profile denies reading it. `views/` is the
readable half — company context, the current batch, handoffs, the latest brief
— written from stored state and holding no approval internals, no lease
identity and no credentials. A role reads the views; nothing reads the runtime
except the service.

The capability is the one genuine secret. `cabinet-launch` mints it per launch,
writes it to an owner-only file under `runtime/profiles/`, and records only its
digest. It reaches the service through the generated MCP configuration, so it
appears in no command line, no prompt, no tool result, no exported view and no
file in the repository. A session that cannot present it may read and nothing
else.

## What belongs in a notebook

Judgements and reasoning that cannot be re-derived. Not facts a live query
already answers.

| Belongs in the notebook | Re-derive instead, never cache |
| --- | --- |
| Why a proposal was rejected, and what would change that | Ticket status, labels, assignees |
| A decision reversed, with the reasoning for both positions | Blocking and blocked-by relationships |
| A confidence downgrade and the condition that would restore it | Open PR list, check results |
| A suite that is green for a named wrong reason | Anything one query answers today |
| A threshold identified, or a hold declared and why | What the tree currently looks like |

Rule of thumb: if a live query can answer it, re-deriving is safer than
trusting a note. **A stale copy of a derivable fact is worse than no copy.**

Writing nothing is a correct outcome. A role that checked and found everything
still true has nothing worth keeping.

## Who writes them

**Not the roles.** Every role is granted read-only tools and cannot write
anywhere. Roles end their output with three sections — `## NOTEBOOK`,
`## DECISIONS`, `## MONEY` — and the command that dispatched them records
those.

This is deliberate, and better than granting each role a pen:

- One writer, so several roles running in parallel cannot race on appends.
- Every role keeps a read-only grant with no exception carved into it, which
  is what makes the money invariant enforceable rather than promised.
- The owner sees every judgement before it is written.

History is never deleted. A superseded entry stays, marked superseded, so the
graveyard of rejected ideas and reversed decisions remains searchable by a run
that was not there.

## A notebook holds three things

Beyond the role's own judgements, each `<role>.md` carries:

- **Inbound notes from other roles.** A role that notices something in
  another's territory addresses it to them rather than to the owner, and the
  command routes it here. The receiving role reads it on its next run and
  decides whether it matters. This never reaches the owner unless it does.
- **A calibration record.** When a role puts something in front of the owner,
  it records what it expects the owner to decide **and how confident it is** —
  near-certain, likely, even odds, unlikely. `/cabinet:decide` appends the
  owner's actual answer with a one-word verdict: matched, or missed. Over time
  the role reads its own record and adjusts — a role that knows the owner will
  decline something notes it rather than asking, which makes the brief shorter
  rather than longer.

  The confidence is what makes the record diagnostic rather than a tally. A
  role that says "near-certain" every time and is usually right is not
  calibrated, it is over-confident and lucky; what the record must be able to
  show is whether its "likely" calls land about as often as "likely" implies.

The calibration record is evidence, not impression: the owner's own answers,
with dates. A role that has been wrong four times running should say so.

## Proposals, `proposals.md`

Initiative has to go somewhere that is not the owner's attention.

A **decision** is something the owner must answer. A **proposal** is something
nobody asked for — an improvement, a convention worth adopting, work worth
dropping. Proposals accumulate here and are aired once a week by
`/cabinet:review`. One reaches the daily brief only when the role that made it
named the cost of *not* doing it.

Each entry carries the role that made it, the date, the cost of delay or an
explicit "no cost named", and how many runs it has gone without an answer. A
proposal the owner keeps passing over is withdrawn by its author with the
reason recorded — people stop pushing an idea the company keeps declining, and
a file that only grows is a file nobody opens.

Charter amendments proposed by roles live here too, marked as such.

## The charter, `company.md`

A map of what this project is and what is true about it, with a source against
every line and, where it can go stale, the condition that ends it:

```markdown
- **Stage:** pre-launch, single user, no revenue.
  Source: #201 (2026-09-09), owner's words.
  Ends when: a second account exists, or any revenue arrives.
```

Stage is the load-bearing line. Most "this is fine for now" judgements in a
young project are conditioned on it, and when it changes they all need
re-checking rather than silently continuing to apply.

The charter also records `owner/repo`. Roles have no shell, so this is the one
fact they cannot derive for themselves.

**It is a living document.** A company does not stay the way it was described
on its first day. Lines whose ending condition has been met are reported every
run until the owner resolves them. Amendments are made with `/cabinet:charter`,
never by overwriting: the superseded line stays, marked superseded and dated,
and the amendment log at the end of the file records what changed and why. The
shape is not fixed either — a pre-launch charter has no pricing section or
support policy, and gains them when the company grows into needing them.

Roles propose amendments; only the owner makes them. Every role reads this
file before forming an opinion, so a role that could edit it would be
rewriting its own instructions.

## The ledger, `money.md`

Two tables: what is recurring and approved, and what is open awaiting the
owner. Every row carries the amount, whether it recurs, the deadline or gate,
who raised it, and the owner's decision with its date.

Nothing reaches the recurring table except through the owner reporting a
completed purchase with `/cabinet:decide <n> --done`. No agent buys anything,
and no agent may infer that a purchase happened — not from a checked box on a
ticket, not from a role's report, not from the owner saying they intended to.

## The inbox, `decisions.md`

Numbered open items, each with the role that raised it, the date, and why it
matters now. Numbers are stable: the owner refers to items by number, so
closing one never renumbers the rest.

Closed items stay, with the owner's answer kept verbatim and the date. An
answer with a condition attached — "yes, but revisit if X" — records the
condition as a reopening trigger.

## Failure modes, handled explicitly

- **A file is missing or empty.** A normal first run. The role says "no prior
  notes — cold read" and derives everything fresh. Missing and
  nothing-to-report are different states and the role must say which one it is
  in. Never read silence as all-clear.
- **A file is stale** — it references a ticket that no longer exists, or
  predates a change it should have accounted for. Flagged, not discarded and
  not silently trusted.
- **A file disagrees with the live source.** The live source wins on facts,
  the file wins on reasoning, and the contradiction is reported rather than
  silently resolved. A role that quietly picks a side manufactures a confident
  wrong answer, which is the failure this whole design exists to avoid.
- **The charter is missing.** Roles stop rather than guess which repository
  they are looking at. Run `/cabinet:hire`.
- **A charter line has outlived its condition.** Reported at every standup,
  and by `/cabinet:charter`, until the owner amends it. It is never silently
  updated and never quietly ignored — a line the company has outgrown is worse
  than a missing one, because roles act on it.
- **No GitHub tools are available.** Roles say so and stop, or clearly label a
  partial answer derived from the tree alone. They never invent board state.
