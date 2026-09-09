---
description: Produce the starting brief for a ticket — what the ticket cannot know about itself, the charter constraint that applies, and what it overlaps with. Paste it into the session that will implement the ticket.
argument-hint: "<ticket number>"
---

# /muster:brief

Load `Skill(skill: "muster:coordination-rules")` first; the briefing rule is
what this command implements.

A ticket should be able to describe itself. This brief carries only what the
ticket **cannot** know about itself, so that the session implementing it
starts knowing the business rather than guessing it.

If a section here would restate the ticket, drop the section.

`$ARGUMENTS` is the ticket number.

## 1. Read

- `.muster/company.md` for what must never be compromised, the stage, and the
  conventions. `~/.muster/founder.md` if present.
- The ticket itself.
- Every notebook, for anything already recorded about this ticket or the area
  it touches — a known-hollow suite, an active hold, a past ordering call.

## 2. Ask the architect

Dispatch `muster:architect` for this ticket specifically: does its description
of the system still hold, and has anything it depends on moved since it was
written. This is the highest-value part of the brief, because a stale spec
reads as authoritative and produces confidently wrong work.

## 3. Check what it overlaps with

Open branches, open PRs, and other open tickets in the same area. Someone
already part-way through the same territory is worth three paragraphs of
context; discovering it at merge time is expensive.

## 4. Assemble

```
TICKET #<n> — <title>

WHAT THE TICKET CANNOT TELL YOU ABOUT ITSELF
 · <staleness, overlap, ordering, or a decision recorded elsewhere>

FROM THE CHARTER
 · <the constraint that actually applies here, not the whole charter>

CONVENTIONS
 <branch, authoritative docs, how tests run — one line>
```

Nothing else. No ticket body, no restated acceptance criteria, no
encouragement.

## 5. Check it for spend before printing

A brief is text that will be pasted into a session holding real tools, so it
must never carry an instruction that spends, deploys, publishes, or
provisions. Scan your own output for commands of that shape — buy, purchase,
subscribe, upgrade, deploy, publish, release, a billing CLI, a production
flag. If one appears, remove it and say in one line that you did and why: the
owner performs anything with a cost themselves.

This check is a named mechanism, not a guarantee of completeness. Say so if
the brief is unusually long.

## 6. Print it

Print the brief and nothing else — no preamble, so it can be copied straight
into the implementing session. Then, on a separate line below it, note where
holds or unresolved decisions touch this ticket, if any, so the owner sees
them without them ending up in the pasted text.

If a counsel hold covers this ticket, say so prominently and do not produce
the brief until the owner has decided to override it: briefing work that is
being held is how a hold gets bypassed by accident.
