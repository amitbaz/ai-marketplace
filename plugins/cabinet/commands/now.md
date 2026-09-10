---
description: Where things stand right now — what is in flight on this machine, what merged since the last standup, and what the board looks like. Reads only; dispatches no roles and writes nothing.
argument-hint: ""
---

# /cabinet:now

Load `Skill(skill: "cabinet:coordination-rules")` first — this command reports
to the owner, so the briefing rule applies to every line it prints.

The standup is a run: it dispatches roles, ranks what reaches you, and writes
to the notebooks. This is not that. It answers one question — what is true
right now — and costs seconds.

Use it when you have opened a workspace, merged something, or come back to
the terminal and want the picture refreshed without paying for a brief.

**This command writes nothing.** Not to the notebooks, not to the decision
inbox, not to the board. If something here deserves a decision, say so and
point at `/cabinet:standup`; do not record it yourself.

Do not narrate the steps. Produce the report.

## 1. Resolve the memory

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/memory-path <owner/repo>
```

`owner/repo` comes from `git remote get-url origin`. If `exists=false`, say
this project has no Cabinet memory, suggest `/cabinet:hire`, and stop.

Read `<memory>/company.md` for the stage and the gate. Read the newest dated
entry in `<memory>/delivery-lead.md` for when the last run happened — that
date is the change window.

## 2. Take both snapshots

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/board-snapshot <owner/repo> --since <that date>
"${CLAUDE_PLUGIN_ROOT}"/scripts/local-sessions <owner/repo> --board <board path>
```

Use seven days ago when there is no prior entry, and omit `--since` when
there is no usable date at all. If either script reports no signal, say which
one and carry on.

## 3. Report

The `In flight` block has two kinds of lines, and they come from two
different places — never blend them or infer one from the other:

- A **local** line — a worktree with unpushed commits, uncommitted files, or
  otherwise not yet a pull request — comes only from `local-sessions`' own
  `worktrees[]`, named by its ticket (or "unattributed local work" when
  `local-sessions` could not attribute it) and its age.
- A **pull request** line comes only from `board-snapshot`'s own open pull
  requests. `local-sessions` cannot see GitHub state, so it never supplies a
  PR line, and a worktree whose branch has an open PR is reported as the PR,
  not as local work.

Never report a pull request that the board snapshot did not return, and
never report a worktree as "in flight" beyond what `local-sessions` itself
marked `in_flight`.

The standup's position block covers exactly the same two signals; it prints
them as one line where this prints a block, and that layout is the only
difference between them.

```
NOW · <date> <time>

<stage>. <named gate> not crossed.

In flight
  #179 — local, 1 commit, 5 files dirty, last touched 3h ago
  #204 — pull request open, checks green

Since <window>
  3 merged: #171, #180, #183.

Board
  67 open · 0 pull requests.
```

Every number in this report comes off one of the two snapshots. There is no
startable count here: the frontier is computed by the delivery lead against
epic bodies, blockers and counsel's holds, this command dispatches nobody, and
a number nobody derived is exactly the invention the brief is not allowed to
make either.

When there is nothing in flight, the block reads:

```
In flight
  none
```

When the run had no local signal, the block reads:

```
In flight
  unknown — no local signal this run
```

— the same words `standup.md` §9 uses for these two states, laid out as a
block instead of inline because this report is a block throughout.

Rules, the same ones the brief runs under:

- **Written for the owner, not an engineer.** No file path, function or line
  number. A worktree is named by its ticket and its age, never by its
  directory.
- **A ticket with no attribution is reported as unattributed local work.**
  Never attach it to a guess.
- **A workspace the scan reported as gone or unreadable is neither in flight
  nor clean.** Say which of the two it is, in the owner's words: the workspace
  was deleted, or it could not be read this run.
- **A zero that means "I could not see" is worse than saying so** — use the
  `unknown — no local signal this run` line above when the scan found
  nothing to read.
- **Nothing is described as having changed unless `recently_merged` says so.**
  With no window, say the window is unknown.
- **Stalled work is named** with its age. Work claimed and abandoned holds
  the frontier closed while looking like progress.

Close with one line: `/cabinet:standup` for the startable frontier and what to
do about any of it.
