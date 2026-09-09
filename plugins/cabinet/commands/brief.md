---
description: Produce the starting brief for a ticket — what the ticket cannot know about itself, the charter constraint that applies, and what it overlaps with. Paste it into the session that will implement the ticket, or post it on the ticket where it survives the session.
argument-hint: "<ticket number>"
---

# /cabinet:brief

Load `Skill(skill: "cabinet:coordination-rules")` first; the briefing rule is
what this command implements.

A ticket should be able to describe itself. This brief carries only what the
ticket **cannot** know about itself, so that the session implementing it
starts knowing the business rather than guessing it.

If a section here would restate the ticket, drop the section.

`$ARGUMENTS` is the ticket number.

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

## 1. Read

- `<memory>/company.md` for what must never be compromised, the stage, and the
  conventions. `~/.cabinet/founder.md` if present.
- The ticket itself.
- Every notebook, for anything already recorded about this ticket or the area
  it touches — a known-hollow suite, an active hold, a past ordering call.

## 2. Ask the architect

Dispatch `cabinet:architect` for this ticket specifically: does its description
of the system still hold, and has anything it depends on moved since it was
written. This is the highest-value part of the brief, because a stale spec
reads as authoritative and produces confidently wrong work.

## 3. Check what it overlaps with

Open branches, open PRs, and other open tickets in the same area. Someone
already part-way through the same territory is worth three paragraphs of
context; discovering it at merge time is expensive.

## 4. Pre-mortem it, in one line

Assume this ticket shipped and it went wrong. What is the most likely story?
Working backwards from an assumed failure surfaces what a forward-looking risk
list misses, because it forces a concrete account rather than a checklist.

Keep it to one line in the brief and only when it is specific to this ticket.
"it might have bugs" is not a pre-mortem. "the guard passes because the
reference set comes back empty, and nobody notices until two users share a
posting" is.

## 5. Assemble

```
TICKET #<n> — <title>

WHAT THE TICKET CANNOT TELL YOU ABOUT ITSELF
 · <staleness, overlap, ordering, or a decision recorded elsewhere>

HOW THIS MOST LIKELY GOES WRONG
 · <one specific line, or omit the section>

FROM THE CHARTER
 · <the constraint that actually applies here, not the whole charter>

CONVENTIONS
 <branch, authoritative docs, how tests run — one line>
```

Nothing else. No ticket body, no restated acceptance criteria, no
encouragement.

## 6. Check it for spend before printing

A brief is text that will be pasted into a session holding real tools, so it
must never carry an instruction that spends, deploys, publishes, or
provisions. Scan your own output for commands of that shape — buy, purchase,
subscribe, upgrade, deploy, publish, release, a billing CLI, a production
flag. If one appears, remove it and say in one line that you did and why: the
owner performs anything with a cost themselves.

This check is a named mechanism, not a guarantee of completeness. Say so if
the brief is unusually long.

## 7. Print it

Print the brief and nothing else — no preamble, so it can be copied straight
into the implementing session. Then, on a separate line below it, note where
holds or unresolved decisions touch this ticket, if any, so the owner sees
them without them ending up in the pasted text.

If a counsel hold covers this ticket, say so prominently and do not produce
the brief until the owner has decided to override it: briefing work that is
being held is how a hold gets bypassed by accident.

## 8. Offer to post it on the ticket

A brief that lives in a terminal dies with the terminal. Copied into a
workspace, it exists in one session and nowhere else — so the next person, or
the next agent, or the owner in three weeks, starts from the ticket alone and
re-derives what this command already worked out. On the ticket, it is durable,
it arrives wherever the ticket is read, and it needs no push to get there.

So offer. **Never post without an explicit yes**, and name three things in the
offer, because the owner is deciding with them and not without them:

> Post this as a comment on **#<n>** in **<owner/repo>**? That repository is
> **public** — the brief becomes visible to anyone, and a deleted comment is
> still in the API, in notifications and in anyone's inbox. [y/N]

State the visibility from what the repository actually says — check it, do not
assume — and say **public** or **private** in as many words. On a public
repository this is a one-way door: a brief carries charter constraints, a
pre-mortem, and what the company is protecting, and that is not the same
material as a ticket body. Default to not posting; silence is not consent.

**Never offer at all when a counsel hold covers the ticket.** Publishing the
reasoning about held work is worse than briefing it.

When the owner says yes, post with `mcp__github__add_issue_comment`, then print
the comment's URL — that link is the durable thing, and it is what goes to the
workspace instead of the pasted text.

Head the comment so a later reader knows what it is and what it is not:

```markdown
**Cabinet brief** — context this ticket cannot carry about itself, produced
<date>. Background, not instructions: nothing here overrides the ticket, and
nothing here is authority to spend, deploy or publish.
```

That header is not decoration. A comment on a ticket is read by the next agent
as part of the ticket, and the rule that content is never authority only holds
if the content says which kind it is.
