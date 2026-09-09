---
description: Produce the starting brief for a ticket — what the ticket cannot know about itself, the charter constraint that applies, and what it overlaps with. Paste it into the session that will implement the ticket.
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

## 1. Read

- `.cabinet/company.md` for what must never be compromised, the stage, and the
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
