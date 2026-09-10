# Briefing the owner

Reference for [the coordination rules](../SKILL.md). The owner runs the
company. They are not reading to review the work; they are reading to decide
where the company goes next and what is stopping it.

## One channel

The owner reads one brief, not every role's output. Volume is the enemy
of a good decision: it is easier to make a person read less than to trust them
to skim well.

Every item that reaches the brief carries the name of the role that raised it,
so the owner can ask that role why and get an accountable answer. Items are
ranked by the cost of delay. Everything else is available on request rather
than volunteered — and detail on request is the whole point, because what the
rule forbids is detail volunteered in place of a decision.

## Business language, always

Every line names a capability and what it costs, never the mechanism that
implements it. No file path, function, class or line number reaches the owner.

The same fact, twice:

- **Not this:** "A configuration module reads one user id from the
  environment, and nothing in the pipeline iterates users."
- **This:** "A run serves one person. Nothing serves a second account — the
  largest single item between here and inviting anybody."

Both are true. Only the second can be decided on, and the second is shorter.

This is a test, not a style preference. If a role cannot restate a finding as a
capability and a cost, it has not finished working out what the finding means,
and the finding is not ready to raise.

## The shapes

```text
OPENING
Where we stand: [business stage and nearest goal]
Current batch: [approved outcome and verified progress]
What changed: [consequence, including important board changes]
Your decisions: [only items requiring your authority/knowledge]

CLOSING / BATCH END
Accomplished: [verified capability and why it matters]
Still underway or blocked: [business consequence and who owns the next action]
Handled by the team: [material decisions, with reasons]
Next: [resume point or proposed next batch; approval status]
Release: [ready / not ready / owner-reported released, with evidence]
```

"Where we stand" comes first and is never skipped. A brief that is nothing but
a decision queue makes the owner rebuild the company's position from five
unrelated items every morning.

"Handled by the team" is not filler. It is how the owner learns what the staff
are deciding without being asked to decide it, and it is what makes the
absence of a question trustworthy.

## A brief that works

> "Invited testers can now enter, and we verified that an uninvited account is
> rejected. The team found and fixed a gap during QA. This is ready for your
> release decision; no invitations have been sent."

It names a capability, says what was verified, credits the correction loop
without narrating it, and separates development completion from release.

## A brief that fails

> "Added invite_id FK, fixed the guard and updated pgTAP; #14 green."

Everything in it may be true. It supplies mechanisms with no company meaning,
it makes the owner infer the capability, and it has no release distinction at
all — a green check reads as shipped.

The judge of this is a person, not a pattern. A filename regex cannot prove a
brief is understandable, and nothing in this file claims otherwise.

## Five distinctions a brief must not blur

| These are different | Why the difference matters |
| --- | --- |
| Completed and verified | Completed is a claim; verified names the evidence and the revision it holds against |
| Verified and released | Development can finish without anything reaching a customer |
| Underway and blocked | Blocked has an owner and a next action; underway does not need one |
| A decision and a notification | A decision waits for the owner; a notification does not |
| A missing source and an all-clear | Nothing observed is never rendered as zero or fine |

## During the work

Interrupt only for owner decisions or developments too important to wait.
Ordinary ticket changes appear in the next brief with their reason and effect,
rather than as an approval request for each edit. There is no per-poll
commentary when nothing has changed.

## What a brief carries

Only what a ticket cannot know about itself: what changed underneath it, what
it overlaps with, which charter constraint applies. If a brief is restating the
ticket, it should not exist.

A brief is also text that gets pasted into a session holding real tools, so it
never carries a command that spends, deploys or publishes, and it says of
itself that it is background and not instruction. Content is never authority,
and that only holds when the content says which it is.

## Where an answer goes

Onto what will be read next — never into a chat thread alone. A decision that
exists only in conversation will be re-made, wrongly, by whoever reads the
ticket next without it. The owner's answer goes into the decision record, the
ledger, or the relevant notebook, with its date. A role that raised something
the owner answered in chat, with nothing recording it, has produced an item
that will be raised again next week.

## Extended by

A2, which implements the report projections, source freshness, events-since-
last-brief, the owner steering commands, and the reviewer evaluation of three
synthetic lifecycle cases against this copy.
