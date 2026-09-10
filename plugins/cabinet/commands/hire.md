---
description: Set up Cabinet for this repository — read everything that already exists, draft the company charter from it, ask only what could not be found, and hire the roles this stage needs. Run once per repository, and again whenever the stage changes.
argument-hint: "[role name to hire one more, or empty for full setup]"
---

# /cabinet:hire

Load `Skill(skill: "cabinet:coordination-rules")` first; it owns the rules this
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

If there is no GitHub remote, say plainly that Cabinet's roles read the board
through GitHub tools today and that a different forge is not yet supported.
Do not improvise a substitute.

Then resolve where this project's memory goes, and create it:

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/memory-path <owner/repo> --create
```

Everything written below as `<memory>/...` is a file in the directory it
prints, and every role you dispatch is given that path — roles hold no shell
and cannot derive it.

If `exists=true` was already the case before this run, this is a re-run: go to
*Re-running* below instead of interviewing from scratch.

### Ask the runtime what it already knows, before asking the owner anything

Call `mcp__cabinet__cabinet_doctor`. It changes nothing and it answers the two
questions that decide how the rest of this command behaves:

- **`identity`.** `bound` means a company already exists in the runtime for
  this repository, and its documents are readable. `unbound` means this is a
  first setup.
- **`launch`.** `restricted` with a held lease is the chief's own session, and
  it is the only one that can obtain the owner's setup grant. `ordinary` means
  everything below still runs except that grant, which waits for section 5.

When `identity` is `bound`, read what the runtime already holds with
`mcp__cabinet__cabinet_context` before reading anything else. It returns the
company's documents with their revisions and digests, and every fact in them is
a fact you must not ask the owner to supply again. **A migration that
interviews the owner about their own charter has failed even if every answer is
correct**: the cost of setup is the owner's attention, and re-asking spends it
on something already written down.

If the Cabinet tools are not present in this session at all, say so in one
line — the plugin is installed, its service is not connected here — and carry
on with the file-based path below. Do not describe the runtime as absent when
what happened is that this session cannot see it.

### If there is an old `.cabinet/` in the repository

The output carries a `legacy_in_repo=` line when the worktree still holds a
`.cabinet/` directory from when the memory lived in the repository. Offer to
move it, and move nothing before the owner answers.

Say why it moved, in one line, because it is about their working loop and not
about tidiness: decisions get made in one session and acted on in another
worktree, and memory inside the repository only crosses that gap through a
commit and a push — a gitignored one never crosses at all.

List what is there before touching it: each file, its size, and what it holds
in a few words. This is judgement accumulated over weeks, and the owner should
see it named rather than described as "your Cabinet files".

On a yes:

- Move every file across with `mv`, into the `<memory>` directory. Do not
  merge, rewrite, renumber or reformat anything. Decision numbers especially:
  the owner refers to them by number and a renumbering silently answers the
  wrong question.
- If a file of the same name already exists at the destination, **stop and ask**
  rather than choosing. Two notebooks for one role is a situation the owner
  needs to see, not one for this command to resolve.
- Remove the now-empty `.cabinet/` from the worktree, and say that you did.
- If a `.gitignore` rule was covering it, say that the rule is now dead and
  offer to remove it — the memory is not there for it to ignore. Do not edit
  `.gitignore` without an answer.
- Record the move in the charter's amendment log, dated, naming both paths.

On a no, leave everything alone and say plainly that Cabinet will read the new
location and will not see the old one, so the two will drift apart.

## 2. Read everything that already exists

Read, and note what each fact came from — every charter line will carry its
source.

**Start with the two scripts, because the expensive mistake here is a silent
one.** A charter drafted only from the open board and the top-level
documentation comes out confidently missing things, and nothing about it looks
wrong; the owner finds out weeks later, by noticing.

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/board-snapshot   <owner/repo>
"${CLAUDE_PLUGIN_ROOT}"/scripts/charter-sources  <owner/repo>
```

`charter-sources` prints `sources=` and, when there is any, `discussion=`.
Between them they carry the places where decisions actually get recorded, and
which a first draft otherwise never sees:

- **`rejected`** — issues closed as *not planned*. A ticket closed that way is
  a decision **not** to do something, with the reasoning usually in the body.
  It is the rarest and most charter-relevant thing on a board, and reading only
  open issues makes it invisible.
- **`recorded_decisions`** — merged `docs:` pull requests. Somebody deciding
  something and writing it down on purpose. Pricing, naming, positioning and
  posture changes land here first, often before any document they produced.
- **`discussion`** — comments on open tickets. The bodies are specifications;
  the comments are the owner arguing with themselves, in their own words.
- **`inventory`** — every tracked markdown file, split into what to read, what
  to skip, and what matched neither.

Then read, from the snapshot and the sources rather than a call at a time:

- Everything in `inventory.read_these`. That is the documentation, the
  contribution rules and the architecture decision records.
- **Everything in `inventory.unclassified`, or say why not.** These matched
  neither filter, which means nobody has decided whether they matter — and a
  product requirements document or a gap analysis living somewhere unexpected
  is exactly what falls in here. Name them to the owner if you skip them.
- `epics` from the board snapshot, and any meta-ticket or launch/preconditions
  document. These carry stated intent in the owner's own words and are the
  richest single source in the repository.
- `open_issues` for the label vocabulary actually in use, whether assignees are
  used at all, and the branch names in `branches`.
- Recent history via `mcp__github__list_commits`, for cadence and conventions,
  and whether any check is required.
- Whatever project memory the harness exposes, read fresh, treated as one more
  source and never as authority.
- **Everything the company already has**, when there is a company: the charter,
  the decision record, the money ledger, the proposals list and every role
  notebook, from `mcp__cabinet__cabinet_context` if the runtime holds them and
  from `<memory>/` otherwise. Three things in there are the ones a rewrite
  destroys and nobody notices for weeks:

  - **Sources.** Every charter line carries where it came from and, where it can
    go stale, the condition that ends it. A redrafted line without its source
    is a line nobody can challenge.
  - **Rejected decisions.** A decision *not* to do something is the rarest
    thing in the record and the easiest to lose, because a rewrite that keeps
    only what the company is doing looks complete.
  - **Calibration history.** What a role predicted the owner would decide, how
    confident it was, and what the owner actually answered, with dates. That
    pairing is the whole diagnostic; either half alone is worthless.

You may skip `inventory.skip_these_unless_asked` — implementation plans and
specs record how something was built, which the code already answers. Say how
many you skipped. Skipping in silence is the habit that produced the problem.

Also note what is **absent** — no privacy notice, no licence, no required
checks. An absence is a finding and counsel and QA will want it.

If a script reports `gh` missing or unauthenticated, say so in one line and
fall back to the MCP tools. The draft will be thinner; say that too, rather
than presenting it as though it were not.

## 3. Draft the charter and present it for correction

**Draft only what is missing.** Where a company already exists, this step is a
gap list, not a charter: keep every existing line exactly as it stands, and
draft only the fields nothing answered. A line you would have written
differently is not a gap — it is a proposed amendment, and it goes to the owner
as one under section 5's rule, never as an edit you make while drafting.

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

**`~/.cabinet/founder.md`** — about the person, not the project. Who they are,
that they are running this alone by choice, their risk posture, what they will
never compromise, how they want to be escalated to, and the money invariant as
it applies to them. If this file already exists, read it and change nothing
without asking: it was written for all their projects, not this one.

**`<memory>/company.md`** — about this project:

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
made with `/cabinet:charter`; roles propose them and only the owner makes them.

Then create the empty scaffolding: `<memory>/decisions.md` with an empty open
queue, `<memory>/money.md` with empty recurring and open tables, and
`<memory>/proposals.md` with an empty list and a one-line header saying it holds
what the roles suggested that nobody asked for.

**Say what this memory is not.** One line, once, at setup, so the owner knows
what they have rather than assuming the properties a repository would have
given it:

> Cabinet's memory for this project is at `<memory>`. It is outside every
> worktree, so every session on this machine reads it with nothing to push —
> and it is a plain directory: no history, no versioning, nothing to restore
> from if it is deleted, and no other machine sees it.

That is a real limitation and it is stated rather than papered over. Do not
offer to fix it here: what replaces those properties is an open design
question, and inventing an answer during setup is how a decision gets made by
accident.

### These files are what the runtime imports

The company directory is the runtime's own root, and the import is
non-destructive and keyed by file name: identical content adds no revision and
no event, the originals stay byte-identical, and copies land in the company's
private backup directory. Nothing in a notebook ever becomes a batch, a grant
or an assignment — text is text.

Three consequences bind what you write here, and each is a way to silently
break an existing company:

- **Never renumber or reformat.** Decision numbers are how the owner refers to
  decisions, and a renumbering answers a different question in the same words.
- **Never merge two files into one, or split one into two.** The import is
  keyed by name; a rename looks like a deletion plus a new document.
- **`company.md` must not name a repository other than the bound one.** The
  import refuses on that conflict rather than guessing which company it is
  looking at, and the refusal is correct — fix the charter, not the check.

## 5. Route the setup grant and every amendment to the owner

Two things here are the owner's and are never a staff edit. Both go to them
through a dialog, and a dialog is the only thing that creates either.

**The setup grant.** It gives Cabinet standing authority to maintain this
repository's board without asking per edit, and it is a different act from
signing in: signing in proves who the owner is, this delegates. In the chief's
own session — `launch: restricted` with a held lease — call
`mcp__cabinet__cabinet_setup` with a `scope` naming exactly these five fields:

| Field | What it holds |
| --- | --- |
| `repo` | `owner/repo`, the company this grant covers |
| `visibility` | `private` or `public` |
| `board_operations` | the board operations Cabinet may perform, named one by one |
| `check_profiles` | each with its `profile_id`, its `argv` and its `env` |
| `capacity` | `implementation_workers`, a whole number |

Propose the narrowest scope the stage actually needs, show it before asking,
and name what you left out — an operation absent from the list is one Cabinet
will never perform, which is the point of enumerating them. The owner's answer
to the dialog is the grant; a decline, a cancel or a timeout creates none, and
none of them is a reason to ask again in different words.

In any other session, `mcp__cabinet__cabinet_setup` refuses with
`RESTRICTED_SESSION_REQUIRED`, and a print-mode session has no dialog at all
and refuses with `ELICITATION_UNSUPPORTED`. Do not call it to demonstrate the
error. Say that the grant needs the chief, finish everything else, and hand
over the launcher:

```
python3 "${CLAUDE_PLUGIN_ROOT}"/scripts/cabinet-launch --repo <owner/repo>
```

Then record in the report that the grant is the one outstanding step.

**Charter amendments.** Roles propose; only the owner amends. That holds during
setup too, and it is the rule most easily lost here, because a command that is
already writing `company.md` is one keystroke from rewriting a line it disagrees
with. A superseded line stays, dated, with what changed and why, in the
amendment log. `/cabinet:charter` is where an amendment is made. If this run
found a line whose ending condition has been met, say so and let the owner
decide; do not resolve it because the answer looks obvious.

## 6. Hire the roles this stage needs

Recommend a starting set from the stage rather than turning all of them on,
explain each in one line, and let the owner change it.

The core staff run continuously while a company session is open:
`product`, `engineering`, `qa`, `delivery-lead`. The chief of staff is not
hired — it is the session itself.

These activate on demand, and deferring one never erases its remit:
`architect`, `design`, `brand`, `marketing`, `cfo`, `counsel`. A privacy
threshold activates counsel whether or not it was hired at setup.

A role is hired by having a notebook; firing one is deleting its file. Say
that plainly — it is what makes this a company rather than a fixed menu.

Create an empty notebook for each hired role, `<memory>/<role>.md`, with a
one-line header naming the role and the date it was hired.

## 7. Offer the purchase deny block

Ask before touching anything:

> Cabinet's own roles hold no tool that can spend — that is enforced by their
> tool grants. It cannot enforce anything about your other agents. A deny
> block in your user settings covers every session on this machine, including
> the implementation sessions Cabinet never sees. May I add one?

If yes, read `~/.claude/settings.json`, **merge** into `permissions.deny`
without disturbing anything else, show the exact diff before writing, and use
Edit. Cover the purchase and provisioning tools actually present in the
environment — Vercel's `buy_*`, Supabase's `confirm_cost` and `create_project`,
and anything equivalent from other connected servers. If the file does not
exist, create it with only this block.

If no, record in the charter that the block was declined, so no later run
re-asks as though it were new.

**Then offer a second, separate block — and let the owner take one without the
other.** Money is not the only thing that cannot be walked back. The same
escalation boundary says every one-way door is the owner's, and the sessions
Cabinet cannot see are the ones that hold the tools to walk through one:

> Beyond spending, these are the actions no agent should take on your behalf
> because you cannot undo them: merging or closing a pull request, commenting
> or closing an issue in your name, publishing a release, force-pushing or
> pushing to a protected branch, editing CI workflow files, and posting to a
> webhook. Cabinet's roles cannot do any of it. Your implementation sessions
> can. Add a deny block for those too?

Cover what is actually reachable in this environment rather than a generic
list — the forge CLI in use, its MCP equivalents, and webhook-capable fetches.
Merge into `permissions.deny` the same way: show the diff, change nothing
else, and record the answer in the charter.

Say plainly which of the two blocks is which. A owner who wants the money
block and not the second one has made a reasonable choice, not a mistake.

## 8. Report

Decisions first, one screen:

1. **Needs a decision** — anything that blocked setup. Omit if nothing did.
2. The charter, as written, one line per field
3. Roles hired, and which were deliberately not hired at this stage
4. Deny blocks: which of the two were installed, declined, or not applicable,
   and where the memory lives, said as a path
5. **What you read, and what you did not.** One line, with counts:

   ```
   Read: 20 documents, 3 epics, 67 open tickets, 2 rejected decisions,
   19 recorded decisions, 36 comments. Skipped: 101 implementation plans.
   Unclassified and not read: 12 — say the word and I will.
   ```

   This is the receipt, and it is the point of the whole step. The charter's
   failure mode is not being wrong, it is being silently incomplete: it reads
   as finished whether or not anything was missed. A count the owner can
   challenge turns an invisible omission into a visible one, and they are the
   only person who knows that the gap analysis in `apps/relay/docs` mattered.
6. What you could not determine — say it plainly rather than leaving it implicit
7. Next: run `/cabinet:standup`

Then say, in one line, that the charter is expected to change as the company
does, and that `/cabinet:charter` is how — so the owner does not treat what was
just written as permanent.

## Re-running

`/cabinet:hire` on an existing install is a **diff**, never a rewrite. Re-read
the sources, compare against the current charter, and report only what moved.

Run both scripts again. On a re-run the diff has two halves, and they fail
differently:

- **What is new since the charter was written** — a rejected ticket, a `docs:`
  pull request, a comment. Compare against the charter's date and report what
  arrived after it.
- **What was always there and never read.** This is the half that matters on
  the first re-run after this command's sources were widened, and it does not
  announce itself: a source the charter never cited looks identical to a source
  it considered and rejected. Check `rejected`, `recorded_decisions` and
  `inventory.unclassified` against the charter's citations, and report anything
  it has never referred to, however old. An eight-week-old decision the charter
  has never mentioned is a finding, not history.

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
