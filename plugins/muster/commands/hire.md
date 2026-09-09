---
description: Set up Muster for this repository — read everything that already exists, draft the company charter from it, ask only what could not be found, and hire the roles this stage needs. Run once per repository, and again whenever the stage changes.
argument-hint: "[role name to hire one more, or empty for full setup]"
---

# /muster:hire

Load `Skill(skill: "muster:coordination-rules")` first; it owns the rules this
command enforces.

**Read before you ask.** A repository with documentation, issues, and history
has already answered most of the charter. Arriving with a blank interview is
insulting and slow. Draft from evidence, present the draft for correction, and
ask only about what genuinely cannot be found. Correcting a draft is faster
than composing an answer, and it surfaces a wrong inference immediately.

If `$ARGUMENTS` names a single role, skip to *Hiring one more role* at the end.

## 1. Establish where you are

Run `git remote get-url origin` and derive `owner/repo`. Roles have no shell,
so this is the one fact they cannot derive for themselves — it goes in the
charter and every role reads it from there.

If there is no GitHub remote, say plainly that Muster's roles read the board
through GitHub tools today and that a different forge is not yet supported.
Do not improvise a substitute.

Check whether `.muster/` already exists. If it does, this is a re-run: go to
*Re-running* below instead of interviewing from scratch.

## 2. Read everything that already exists

Read, and note what each fact came from — every charter line will carry its
source:

- `README`, `AGENTS.md`, `CLAUDE.md`, any documentation directory, any
  architecture decision records.
- The open board via `mcp__github__list_issues`, and the bodies of anything
  that looks like an epic, a meta-ticket, or a launch/preconditions document.
  These carry stated intent in the owner's own words and are the richest
  source in the repository.
- The label vocabulary actually in use, whether assignees are used at all,
  branch naming, and whether any check is required.
- Recent history via `mcp__github__list_commits`, for cadence and conventions.
- Whatever project memory the harness exposes, read fresh, treated as one more
  source and never as authority.

Also note what is **absent** — no privacy notice, no licence, no required
checks. An absence is a finding and counsel and QA will want it.

## 3. Draft the charter and present it for correction

Show the draft in the terminal with a source against every line, then ask only
about the gaps. Typically only four things cannot be found anywhere:

1. **Brand direction** — the repository holds the current name, not the
   intent behind the next one.
2. **Risk posture** — when speed and caution conflict, which wins. Nothing in
   a repository says this.
3. **Whether the drafted stage is still current**, if the source for it is
   more than a few weeks old.
4. **Consent for the purchase deny block** — never inferred, asked every time,
   on every repository.

Ask nothing you already found. If the repository answered all four, say so and
confirm rather than interviewing.

## 4. Write the two layers

Use Write to create both. The split is what makes the second repository nearly
free to set up.

**`~/.muster/founder.md`** — about the person, not the project. Who they are,
that they are running this alone by choice, their risk posture, what they will
never compromise, how they want to be escalated to, and the money invariant as
it applies to them. If this file already exists, read it and change nothing
without asking: it was written for all their projects, not this one.

**`.muster/company.md`** — about this project:

- What it is, in one line, to someone who would pay for it
- **Stage**, and what would end it — this is the most load-bearing line in the
  file, because most "fine for now" judgements are conditioned on it
- What must never be compromised
- Brand direction, and the current name's status
- Who the users are
- `owner/repo`, the dispatch signal (which label or condition means a ticket is
  ready to start), the branch convention, and whether assignees mean anything
- What is absent that a role will ask about

Every line carries its source and, where it can go stale, the condition that
would end it:

```markdown
- **Stage:** pre-launch, single user, no revenue.
  Source: #201 (2026-09-09), owner's words.
  Ends when: a second account exists, or any revenue arrives.
```

The charter is a living document, not a snapshot taken once. End the file with
an **amendment log** — empty at first — and say in the file that superseded
lines stay, marked superseded, rather than being overwritten. Amendments are
made with `/muster:charter`; roles propose them and only the owner makes them.

Then create the empty scaffolding: `.muster/decisions.md` with an empty open
queue, `.muster/money.md` with empty recurring and open tables, and
`.muster/proposals.md` with an empty list and a one-line header saying it holds
what the roles suggested that nobody asked for.

**Check that `.muster/` will actually be committed.** Run
`git check-ignore -q .muster/company.md`; if it exits 0, the path is ignored
and every judgement written here would be lost on a fresh clone. Say so
plainly, name the `.gitignore` rule responsible, and ask whether to add a
negation for `.muster/` or leave the memory local. Do not edit `.gitignore`
without an answer.

## 5. Hire the roles this stage needs

Six ship with the plugin: `delivery-lead`, `architect`, `qa`, `counsel`,
`cfo`, `brand`. Recommend a starting set from the stage rather than turning
all of them on, explain each in one line, and let the owner change it.

A role is hired by having a notebook; firing one is deleting its file. Say
that plainly — it is what makes this a company rather than a fixed menu.

Create an empty notebook for each hired role, `.muster/<role>.md`, with a
one-line header naming the role and the date it was hired.

## 6. Offer the purchase deny block

Ask before touching anything:

> Muster's own roles hold no tool that can spend — that is enforced by their
> tool grants. It cannot enforce anything about your other agents. A deny
> block in your user settings covers every session on this machine, including
> the implementation sessions Muster never sees. May I add one?

If yes, read `~/.claude/settings.json`, **merge** into `permissions.deny`
without disturbing anything else, show the exact diff before writing, and use
Edit. Cover the purchase and provisioning tools actually present in the
environment — Vercel's `buy_*`, Supabase's `confirm_cost` and `create_project`,
and anything equivalent from other connected servers. If the file does not
exist, create it with only this block.

If no, record in the charter that the block was declined, so no later run
re-asks as though it were new.

## 7. Report

Decisions first, one screen:

1. **Needs a decision** — anything that blocked setup. Omit if nothing did.
2. The charter, as written, one line per field
3. Roles hired, and which were deliberately not hired at this stage
4. Deny block: installed, declined, or not applicable
5. What you could not determine — say it plainly rather than leaving it implicit
6. Next: run `/muster:standup`

Then say, in one line, that the charter is expected to change as the company
does, and that `/muster:charter` is how — so the owner does not treat what was
just written as permanent.

## Re-running

`/muster:hire` on an existing install is a **diff**, never a rewrite. Re-read
the sources, compare against the current charter, and report only what moved.

Never touch a role's notebook — those hold judgement and this command has no
business writing them.

Report which charter lines have had their ending conditions met since the last
run — those are the lines the company has already outgrown.

If **stage** changed, that is the important case. Say which charter lines were
conditioned on the old stage, flag every one of them for re-decision rather
than deleting or silently updating them, and propose the staffing change the
new stage implies. Ask before hiring or firing anyone.

## Hiring one more role

With `$ARGUMENTS` naming a role: confirm it is one of the six, create its
notebook, note in the charter when and why it was hired, and say in one line
what it will now start doing.
