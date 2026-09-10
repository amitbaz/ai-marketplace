---
description: Open the company. In an ordinary session it diagnoses the company read-only and hands you the one command that starts the restricted chief; in the chief's own session it resumes the operating loop where the last session left it.
argument-hint: "[--status-only]"
---

# /cabinet:company

Load `Skill(skill: "cabinet:coordination-rules")` first. It owns the execution
order this command resumes; nothing about that order is repeated here.

This command behaves differently in two kinds of session, and **the difference
is not a preference — it is what the session is allowed to do**. Find out which
one you are in before doing anything else. Never guess from the fact that a
Cabinet tool answered: the read tools answer everywhere.

## 1. Diagnose, always, in both cases

Call `mcp__cabinet__cabinet_doctor`. It takes no arguments and changes nothing.

If the tool is not present at all, this session has no Cabinet connection: say
that the plugin is installed but its service is not connected here, point at
`/cabinet:help`, and stop. Do not fall back to reading company files by hand —
a picture assembled that way looks identical to a real one and is not.

Read these checks out of what it returns. Their names and values are the
service's, not yours:

| Check | What its value tells you |
| --- | --- |
| `identity` | `bound` names the company's repository; `unbound` means no company exists here yet |
| `store` | `open` or `read_only` |
| `lease` | `held` by this process, `elsewhere`, or `absent` |
| `pause` | `paused` carries the reason; `running` does not |
| `launch` | `restricted` is a qualified chief; `ordinary` and `refused` are not |
| `dialog` | whether this client could show the owner a form at all |

**`launch: restricted` together with `lease: held` is the qualified chief.
Anything else is a broad session.** A `refused` launch is the interesting one:
it means something tried to present a launch context and the service rejected
it, and the detail carries the code. Report that verbatim rather than treating
it as an ordinary session.

With `--status-only` in `$ARGUMENTS`, report what section 2 describes and stop
there, whichever kind of session this is. It is the cheap read.

## 2. In an ordinary session — report, then hand over

This is the normal case when the owner types the command, and it is a
**read-only** one. Do not call any writing tool from here. They stay callable
and they will refuse with `RESTRICTED_SESSION_REQUIRED`; producing that error
on purpose teaches the owner that Cabinet is broken when it is working.

Report, in the owner's language and in this order:

1. **Which company this is** — the repository `identity` named, or that no
   company is set up here and `/cabinet:hire` is what sets one up.
2. **Whether there is anything to resume** — a current batch and its state, the
   last checkpoint and when it was taken, and how many handoffs are unresolved.
   Take these from `mcp__cabinet__cabinet_snapshot`; say plainly when a field is
   absent rather than rendering absence as zero.
3. **Whether work is paused**, and the reason the pause carries.
4. **That this session is not the chief.** Say it as a capability: this session
   can read the company and cannot change it, so nothing here can approve a
   batch, dispatch anyone, or record a decision.

Then hand over the launcher, exactly once, as a command to run in a terminal:

```
python3 "${CLAUDE_PLUGIN_ROOT}"/scripts/cabinet-launch --repo <owner/repo>
```

`--repo` may be omitted when the terminal's working directory is the company's
repository; the launcher reads `git remote get-url origin` itself. Add
`--dry-run` to see the profile, the files it would write and the argv without
starting anything. Do not invent any other flag, and do not assemble a `claude`
command of your own: the launcher mints a per-launch capability and verifies
the profile, and an argv written by hand carries neither, so it produces a
session that looks like a chief and can write nothing.

**Say once what the launcher is, and do not repeat it after that.** It is
setup — the way the company session is started, the same way a program is
started. It is not a message-passing step, and the owner is not expected to
copy anything between sessions afterwards. If the owner has already been told
this in the current conversation, hand over the command with no explanation.

The launcher replaces itself with the Claude process, so it cannot be run from
inside this session: it is for the owner's own terminal. Say that in one line
if the owner asks why you did not just run it.

## 3. In the qualified chief session — resume the loop

`launch: restricted` and a held lease mean this session is the chief. Resume
the skill's execution order from the top, and **in its order**:

- Reconcile before proposing. The skill's second step exists because a session
  ending never completed anything, and an old session id is not a live worker.
  Nothing new is proposed, and no role is dispatched into new work, until live
  work has been reconciled against its actual sources.
- Then start and register the staff the current state needs, each with the
  company context from `mcp__cabinet__cabinet_context` and its own remit.
- Then give the opening brief in the shape the briefing reference defines.

Two failures to check for before any of that, because both look like a working
session until they bite:

- **`pause: paused`.** Report the reason and resume nothing. A pause stops new
  dispatch; it is lifted by the owner, not by the chief noticing it.
- **`lease: elsewhere`.** Another lead holds this company. Say which generation
  and stop. Two leads writing to one company is the state the lease exists to
  prevent, and taking it over is an explicit act, not a recovery step.

When the state carries a proposed batch awaiting approval, say so and point at
`/cabinet:batch --present`. Do not present it from here; one command owns that
conversation so the owner sees the same body twice, not two paraphrases.

## 4. What this command never does

- It never approves anything, in either kind of session. There is no approval
  method an agent can call, and the owner's dialog is the only grant.
- It never dispatches a role from an ordinary session, including a read-only
  one. A role dispatched outside the chief has nowhere to record what it
  returns, and an unrecorded answer is one that will be asked for again.
- It never reports a company as healthy because the tools answered. `ok` in
  the doctor result covers the store and the identity binding, and nothing
  else; say what it actually covers when you quote it.
