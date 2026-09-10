# Cabinet implementation — session handoff (2026-09-10)

Written by the controller session at 94% context, while Task O4 was still being
implemented by a subagent. The owner asked to pause after O4 is delivered.
Read this first, then the SDD ledger, then the plan ledger.

## Where everything is

| What | Path |
| --- | --- |
| Branch / worktree | `codex/cabinet-company-design` at `/Users/amitbaz/.superset/worktrees/amitbaz/codex/cabinet-company-design` (PR #29, draft) |
| Master plan | `docs/superpowers/plans/2026-09-09-cabinet-ai-company.md` (+ foundation / operating-team / acceptance task files, contracts) |
| Plan ledger (per task rows, R01–R18 rows) | `docs/superpowers/plans/2026-09-09-cabinet-progress.md` |
| SDD controller ledger (rulings, reviews, deferred minors) | `.superpowers/sdd/2026-09-09-cabinet-ai-company/progress.md` (git-ignored; first line names the plan) |
| Per-task briefs, dispatch briefs, reports, reviews, diffs | same directory: `task-<ID>-brief.md`, `task-<ID>-dispatch.md`, `task-<ID>-report.md`, `review-<ID>-report.md`, `review-<base>..<head>.diff` |
| Live evidence | `docs/cabinet/acceptance/{environment,f4-service-smoke,o1-roles-scenario,o2-native-exchange,o3-github}.md` (O4 adds `o4-workers.md`) |
| Runtime code | `plugins/cabinet/scripts/cabinet_runtime/` (errors, contracts, store, migration, exports, approval, policy, processes, profiles, rpc, service, github, boardcli; O4 adds superset + git), entrypoints `scripts/cabinet-service`, `scripts/cabinet-launch`, `scripts/cabinet-hook`, `hooks/hooks.json`, `.mcp.json` |
| Tests / checks | `tests/cabinet/` (793 tests at eb42aa8); `scripts/check-cabinet.py` (+ `--self-test`); `scripts/check-adapter-boundary.py`; `bash plugins/cabinet/scripts/board-snapshot --self-test`; `plugins/cabinet/scripts/cabinet-hook --self-test` |

Test command (all suites, output must be pristine):

```sh
PYTHONPATH=plugins/cabinet/scripts:tests/cabinet python3 -m unittest discover -s tests/cabinet -p 'test_*.py'
```

## Process used

superpowers:subagent-driven-development, with the owner's authorization to use
subagents. One implementer per task (Opus for design-heavy, Sonnet for small
re-reviews), a task review, then scoped re-reviews per fix round. Dispatch briefs
live in files so the controller's context stays small. The chief of staff and
its teammates/workers were exercised live where the plan requires native proof.

## Task state at handoff

| Task | State | Commits | Notes |
| --- | --- | --- | --- |
| F1 capability contract | complete, review clean | 05b9bc3..3ed5a9c | `--tools` narrows tools (`--allowedTools` does not); no `--max-turns`; teammates cannot spawn teammates; cross-session inbound needs `crossSessionInbound: accept`; idle wake works from a main session |
| F2 transactional state | complete (1 fix round) | 3ed5a9c..21ee04a | SQLite store, implicit lease on first mutation, migration, exports, backup |
| F3 approval + policy | complete (1 fix round) | 21ee04a..3ab2a36 | frozen-revision consent via elicitation; action-kind classes; setup grants |
| F4a profiles/hook | complete (2 fix rounds) | 3ab2a36..d5b232f | argv derived from profile and re-verified; credential files denied; hook via settings for workers |
| F4b service/rpc/launcher | complete (1 fix round) | d5b232f..b2a73ed | MCP stdio service, restricted launcher, signed launch record; live smoke a–d supported, print-mode elicitation unsupported |
| O1a roles/skill/checker | complete (1 fix round) | b2a73ed..92bb609 | operating skill + 5 references, 11 staff + 2 worker agents, `check-cabinet.py` |
| O1b commands + scenario | complete, review clean | 92bb609..9194479 | `/cabinet:company`, `/cabinet:batch`, hire/ask updated; live Product/Engineering scenario verified |
| O2 active handoffs | complete (2 fix rounds) | 9194479..045849c | handoff lifecycle, retries, peers.json, wait_events; live chief exchange H001/H002 recorded→resolved (R05 evidence) |
| O3 GitHub ownership | complete (1 fix round) | 045849c..eb42aa8 | scoped board writes with readback; live reads verified; **live writes BLOCKED awaiting owner fixture repo** |
| O4 isolated workers | IN PROGRESS (subagent `impl-O4`, base eb42aa8) | — | Superset unauthenticated → local worktree provider ruling; see below |
| O5, A1, A2, A3, A4 | not started | — | dispatch brief for O5 already written: `task-O5-dispatch.md` |

## How to resume O4

1. `git status` / `git log --oneline -3`. If commits after eb42aa8 exist, read
   `.superpowers/sdd/2026-09-09-cabinet-ai-company/task-O4-report.md`; if it is
   missing or the tree is dirty, the implementer was interrupted: run the test
   suite, inspect the diff, and either resume with a fresh implementer using
   `task-O4-dispatch.md` (tell it what already exists) or finish by hand.
2. Review loop: `review-package PLAN eb42aa8 <head>` (script under the
   superpowers subagent-driven-development skill), dispatch a reviewer with the
   dispatch brief + O4 plan brief + contract, fix rounds as needed, then append
   `Task O4: complete (...)` to the SDD ledger and update the plan ledger row.
3. Then stop (owner asked to pause after O4). Next task is O5 via
   `task-O5-dispatch.md` (base = O4's final head; update the "base HEAD" line).

## Owner actions that gate live proof

- Superset login (`superset auth login`) — O4's Superset path, R07 on Superset.
- Authorize a private GitHub fixture repository for O3/A4 live writes (R06).
- Answer one real approval dialog in an interactive restricted chief (F3/F4, R04):
  `python3 plugins/cabinet/scripts/cabinet-launch --repo <owner/repo>` from a
  synthetic company, then `/cabinet:batch --present`.
- Approve the real Career Platform pilot batch (A4) — separate business decision.
- Account usage: the weekly/monthly usage limit was hit once mid-O2 fix; work
  resumed after reset. Budget the remaining tasks.

## Rulings made so far (each with what it costs if wrong)

1. F2 also implements `Store.close()` and `get_action()` (needed by its own test and O4). Cost: none.
2. F4 creates `cabinet-hook`/`hooks.json`; A1 extends. Cost: none.
3. AGENTS.md stale sentences are amended minimally as they become false; A3 does the full rewrite. Cost: none.
4. Live gates needing owner action are recorded BLOCKED/awaiting and batched into one owner request; native local probes are authorized by the handoff prompt. Cost: none.
5. Stdlib/no-build invariant binds everything under `plugins/cabinet`; tests are plain unittest. Cost: none.
6. Prefer Sonnet where briefs are concrete, Opus for design-heavy tasks (usage limit). Cost: slower loops.
7. F1's two controller-requested evidence commits skipped re-review. Cost: a misstated evidence row.
8. Empty lease table: first mutation binds an implicit lease to the mutating process (keeps the brief's tests, closes the window). Cost: F4 startup ergonomics.
9. Scope-path symlink checking deferred to O4 (no checkout in F2). Cost: none if O4 did it — verify.
10. Approval dialog shows owned paths, base SHA and check profiles (spec: exact scope revision). Cost: a longer dialog.
11. F4 and O1 each split into two dispatches. Cost: an extra review seat each.
12. Credential rule: deny `~/.claude/**` except the loaded plugin root; deny `~/.cabinet/**/runtime/**`; views readable. Cost: an over-broad read on the plugin cache.
13. Worker profiles register the hook through the profile's `--settings`; profiles carry `env`. Cost: none.
14. Staff tool registry is the target set; advisory roles lost `WebSearch/WebFetch/mcp__github__*` (contract). Cost: brand/cfo/counsel cannot check external facts — surfaced to the owner as a design proposal (an on-demand read-only researcher role).
15. Chief `--tools` may exclude MCP names → explicit option; F4b proved `--tools` does not gate MCP names, option stays off. Cost: none.
16. Chief profile pre-allows its own tools in `permissions.allow` and sets `crossSessionInbound: accept`; owner authority lives in the elicitation dialog. Cost: none.
17. O2: required evidence claims added to the brief's two verbatim tests (sender checks are mandatory). Cost: plan example tests differ by one field.
18. O2: `--bg` chief has no launcher ancestry → capability + signed record + 120 s window. Cost: weaker host binding for background chiefs (documented).
19. O3: live writes not authorized; read probes only. Cost: R06 write evidence pending.
20. O3: until O5 records an integration SHA, closing as completed needs a QA pass at the assignment's reported head. Cost: stricter close gate until O5.
21. O4: Superset unauthenticated → add `LocalWorktreeProvider` (git worktree from base_sha + `claude --bg` restricted worker) behind the same adapter interface; Superset path implemented against the fake, live gate BLOCKED awaiting login. Cost: a second provider to maintain.

## Deferred minors (for the final whole-branch review)

Listed per task in the SDD ledger (`Task <ID>: minor (deferred)` lines). Recurring
themes: `store.py` (~1.6k lines), `profiles.py` (~870), `github.py` (~1.2k) exceed
the size guidance; several docstrings/prose drift items; `_require_whole_board`
300 s staleness; unbounded `_cancelled` set in rpc.py.

## Known hazards observed

- API 500 bursts killed one implementer three times; host memory pressure killed
  background tasks (MemPalace watcher, sleeps). Keep one live claude process at a
  time; stop and `claude rm` every `--bg` session.
- A refused launch once created an empty company directory under the real
  `~/.cabinet` (fixed in O2: the fallback no longer creates anything). The real
  `~/.cabinet/repos/amitbaz-career-platform` was verified intact.
- A bare SendMessage name shared by a teammate and a peer session resolved to the
  peer; worker sessions are named `cabinet-worker-<assignment>`.
