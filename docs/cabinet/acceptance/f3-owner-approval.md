# Owner approval dialog — native evidence (R04)

Recorded 2026-09-10. macOS, Claude Code 2.1.267, plugin commit 1f67df3, synthetic
company `demo/company` (created for this probe, deleted afterwards). Chief launched
by the owner in an interactive terminal:

```sh
python3 plugins/cabinet/scripts/cabinet-launch --repo demo/company --model haiku \
  --prompt-file <scratchpad>/approval-probe/chief-prompt.md
```

The prompt asked the chief to acquire the lead, propose synthetic batch T001 r1,
request approval (owner intends to approve), propose r2, request approval again
(owner intends to decline), then report a snapshot. This is a mechanism test, not a
business approval.

## What the owner saw and did

Two MCP elicitation dialogs, one per revision. The owner answered the first with
approve = true and the second with decline. The chief's final report:
grant `G430a9fe5c997` for r1; r2 declined, no grant; r1's grant revoked when r2 was
proposed; 11 events. It then printed `APPROVAL PROBE DONE` and stopped.

## Read back from outside the chief (read-only SQLite open)

| seq | event | entity | time (UTC) |
| --- | --- | --- | --- |
| 1 | lease.acquired | chief-of-staff r1 | 08:07:31 (attempt 2, lease taken) |
| 2 | batch.proposed | T001 r1 | 08:07:36 |
| 3 | lease.acquired | generation 2 (attempt 3) | 08:10:20 |
| 4 | approval.requested | AR218e8baed8aa r1 | 08:10:28 |
| 5 | approval.granted | AR218e8baed8aa r1 | 08:10:54 (owner answered after 26 s) |
| 6 | batch.state_changed | T001 r1 → approved | 08:10:54 |
| 7 | batch.proposed | T001 r2 | 08:10:58 |
| 8 | batch.state_changed | T001 r1 → superseded | 08:10:58 |
| 9 | approval.revoked | G430a9fe5c997 | 08:10:58 |
| 10 | approval.requested | AR2eac31dbfc08 r2 | 08:11:00 |
| 11 | approval.declined | AR2eac31dbfc08 r2 | 08:11:07 |

Grants table: one row, `G430a9fe5c997` (T001 r1, approved_seq 5, revoked_seq 9).
Batches: T001 r1 `superseded`, T001 r2 `proposed`. No grant exists for r2.

## Verdict

- A grant appeared only after the owner's own dialog answer (seq 4 → 5, 26 s apart), never from the tool call itself: PASS.
- Decline created no grant and no pending request survived: PASS.
- Proposing a new revision revoked the earlier grant (dispatch authority invalidated by a scope change): PASS.
- The mechanism is `native_verified`. Not covered here: cancelled/timed-out dialogs live (unit_verified only), and the F1 hazard that `Elicitation` hooks could synthesize answers (the restricted profile excludes user hooks; managed policy unchecked on this machine).

## Defects found on the way (all fixed before this run)

1. The probe prompt initially omitted `cabinet_acquire_lead`; the chief correctly refused to proceed without a lease.
2. Claude Code 2.1.267 declares `"elicitation": {}` under MCP 2025-11-25; the service required a `form` key and refused with `ELICITATION_UNSUPPORTED` (fixed in 1f67df3, evidence in `environment.md`).
3. Observation: the lease row for attempt 3 carries a model-supplied session id (`test-session`) — `cabinet_acquire_lead` accepts a caller-chosen id. The launch record, not the lease id, is what binds the session; still, the lease id should come from the launcher context. Deferred to A1 (recovery), where session identity matters.
4. The chief's first tool call in attempt 3 failed with "Invalid tool parameters" (a Skill or doctor call shape); it recovered unaided.
