# The files Muster keeps

Every role in this plugin is a fresh dispatch: a new context each run, no
memory of the last one. The files below are the memory. They are also the
whole of Muster's state — there is no database, no cache, and nothing you
cannot read in a text editor with the plugin uninstalled.

## Two layers, and why

```
~/.muster/founder.md          about the person — not committed
.muster/                      about this project — committed
  company.md                  the charter
  decisions.md                the open queue and its history
  money.md                    the ledger
  <role>.md                   one notebook per hired role
```

`founder.md` holds what is true across every project the owner runs: how they
work, their risk posture, what they will never compromise, and that they are
the only one who spends money. Written once. The second repository they set up
asks almost nothing, because only the project half is new.

`.muster/` holds this project. It is committed on purpose — judgement should
survive a fresh clone, be diffable, and be readable by a person who does not
have this plugin installed.

Note the location. An earlier design put these under `.claude/`, which many
repositories ignore wholesale, so the memory would never have been committed
at all. If your `.gitignore` covers `.muster/`, the plugin will tell you.

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

## The ledger, `money.md`

Two tables: what is recurring and approved, and what is open awaiting the
owner. Every row carries the amount, whether it recurs, the deadline or gate,
who raised it, and the owner's decision with its date.

Nothing reaches the recurring table except through the owner reporting a
completed purchase with `/muster:decide <n> --done`. No agent buys anything,
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
  they are looking at. Run `/muster:hire`.
- **No GitHub tools are available.** Roles say so and stop, or clearly label a
  partial answer derived from the tree alone. They never invent board state.
