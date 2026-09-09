---
description: Answer an open decision. Records the owner's answer where the role that raised it will read it next, closes the item, and for anything with a price attached records that the owner bought it — Cabinet never buys anything.
argument-hint: "<number> <your answer>   |   <number> --done <what you did>"
---

# /cabinet:decide

Load `Skill(skill: "cabinet:coordination-rules")` first.

This is the return channel. A decision that exists only in conversation will
be re-made, wrongly, by whoever reads the ticket next without it. This command
is how the owner's answer gets written onto what will be read next.

`$ARGUMENTS` is the item number followed by the answer in the owner's own
words.

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

## 1. Find the item

Read `<memory>/decisions.md` and locate the numbered item. If the number does
not exist, say so and list the open items rather than guessing which one was
meant. If the item is already closed, show how it was closed and when, and ask
whether this is a reversal — a reversal is recorded as one, keeping both
reasons, never as an overwrite.

## 2. Record it where it will be read

Write the answer into `<memory>/decisions.md`: mark the item closed, with the
date and the owner's words kept verbatim. Do not paraphrase the owner. Never
renumber the remaining open items.

Then append it to the notebook of the role that raised it, in that role's own
structure — brand's three lists, counsel's threshold and hold records, and so
on. The role reads its notebook before forming any new opinion, so this is
what stops it being raised again next week.

Where the answer has a condition attached — "yes, but revisit if X" — record
the condition as the reopening trigger, not as a footnote.

## 3. Score the prediction

Every item a role raised carries that role's prediction of what the owner
would decide **and how confident it was**. Append the prediction, its
confidence, and the owner's actual answer to that role's calibration record,
dated, with a one-word verdict: matched, or missed.

Confidence is what makes the record diagnostic. A role that says "near-certain"
every time and is right most of the time is not well calibrated — it is
over-confident and lucky. What the record has to be able to show is whether
its "likely" calls come true about as often as "likely" implies.

Do not soften a miss and do not editorialize. The record is only useful if it
is honest, and a role reading four misses in a row should conclude something
about how it has been reading this owner.

If the item was a **charter amendment** proposed by a role and the owner
accepted it, apply it through `/cabinet:charter` so it is logged with its
history rather than silently rewritten.

If the item was a **proposal** the owner has now taken up, move it out of
`<memory>/proposals.md` and say what it became — a ticket to file, a decision,
or work the owner will do themselves. A proposal declined is recorded as
declined with the reason, never deleted.

## 4. Money items take a second step

Cabinet never buys anything. If the item has a price attached, the owner's
answer is an intention, not a transaction:

- `/cabinet:decide <n> yes` records approval and leaves the item **open**,
  marked *approved, awaiting purchase by owner*. Say plainly in your reply
  that nothing has been bought and that the owner buys it themselves.
- `/cabinet:decide <n> --done <what they did>` is the owner reporting a
  completed purchase. Only then does it close and move into `<memory>/money.md`
  under recurring or one-off, with amount, date, and the role that raised it.

Never infer that a purchase happened. Not from a checked box on a ticket, not
from a role's report, not from the owner saying they would. Only `--done`,
typed by the owner, closes a money item.

A declined money item is recorded with the reason and the condition that would
reopen it, so the CFO does not raise it again as though it were new.

## 5. Confirm, briefly

One or two lines: what was recorded, where it was written, and whether
anything is now unblocked — for example a counsel hold lifted, which returns a
ticket to the startable frontier. If a money item is approved but not yet
bought, say that it stays open until the owner reports the purchase.
