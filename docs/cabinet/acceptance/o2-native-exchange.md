# O2 live evidence — a Product → Engineering → QA exchange over native messages

Recorded 2026-09-10 on the owner's macOS machine (Darwin 25.6.0, arm64), Claude
Code 2.1.267, worktree `codex/cabinet-company-design` at implementation commit
`3d5bc9c`. Everything below ran against a **synthetic** company under a scratch
`CABINET_HOME`; the real company directory was never opened and the repository
`demo/o2-company` does not exist.

This closes acceptance item **R05**: an actionable exchange between three staff
roles, recorded and acknowledged through the service, with no technical message
relayed by the owner. The owner wrote one instruction file and read the result.

## What was run

```
CABINET_HOME=<scratch>/o2/cabinet python3 plugins/cabinet/scripts/cabinet-launch \
  --repo demo/o2-company --assignment o2probe \
  --prompt-file <scratch>/o2/prompt.txt --bg
```

The launcher printed `backgrounded · efc97e1a · cabinet-chief-o2probe`. The
chief ran unattended for three minutes and forty-two seconds, spawned Product,
Engineering and QA as its own teammates, ran two clarification handoffs end to
end, exported the company views, checkpointed and stopped. The session was then
stopped and removed.

## The record, read from outside the chief

Read directly from `runtime/cabinet.sqlite3` in read-only mode after the
session ended. Sixteen events, no gaps.

| seq | event | time (UTC) | what it says |
| --- | --- | --- | --- |
| 1 | `lease.acquired` | 04:18:15 | generation 1, session `e46469f0…` |
| 2 | `batch.proposed` | 04:18:19 | B001 revision 1 |
| 3–6 | `session.registered` | 04:18:21–23 | chief at `cabinet-chief-o2probe`, product at `product`, engineering at `engineering`, qa at `qa` |
| 7 | `handoff.recorded` | 04:18:45 | H001 product → engineering, `clarification`, digest `cf81953cc4d6…`, truncated false |
| 8 | `session.registered` | 04:21:08 | chief **re-registered at `main`** — see *What the roles discovered* |
| 9 | `handoff.state_changed` | 04:21:29 | H001 recorded → sent, attempts 1, next probe 04:21:59 |
| 10 | `handoff.state_changed` | 04:21:31 | H001 sent → acknowledged |
| 11 | `handoff.state_changed` | 04:21:33 | H001 acknowledged → resolved |
| 12 | `handoff.recorded` | 04:21:36 | H002 qa → engineering, `clarification`, digest `e429fd93edaf…` |
| 13 | `handoff.state_changed` | 04:21:48 | H002 recorded → sent, attempts 1, next probe 04:22:18 |
| 14 | `handoff.state_changed` | 04:21:49 | H002 sent → acknowledged |
| 15 | `handoff.state_changed` | 04:21:53 | H002 acknowledged → resolved |
| 16 | `checkpoint` | 04:21:57 | `session_close` |

Event IDs (first eight hex characters): `e93b5325`, `96354e93`, `c275c227`,
`bf368338`, `62855f86`, `dee04e95`, `4a31d41a`, `e30aa169`, `8d593033`,
`2c18a65e`, `fc8ab4d5`, `ae6f8374`, `1e149ff6`, `6cdcf190`, `da5e2cce`,
`b187b40e`.

### The transition evidence, verbatim from the event payloads

```json
H001 recorded -> sent      {"transport":"native","recipient":"engineering","result":"sent",
                            "native_sender":"product",
                            "message_id":"127b960f-315c-4bb2-9e0b-d21683f0b63b"}
H001 sent -> acknowledged  {"native_sender":"engineering","revision":1}
H001 acknowledged -> resolved
                           {"native_sender":"engineering",
                            "response":"Invitation codes are single-use; a second use of the
                                        same code is refused."}
H002 recorded -> sent      {"transport":"native","recipient":"engineering","result":"sent",
                            "native_sender":"qa",
                            "message_id":"1f3ff707-1050-4f16-873c-efaef2985d62"}
H002 sent -> acknowledged  {"native_sender":"engineering","revision":1}
H002 acknowledged -> resolved
                           {"native_sender":"engineering",
                            "response":"Refusal for AC1 goes through the invitation-check gate
                                        at entry, before any account or session is created."}
```

The two `message_id` values are the `msg_id` the native `SendMessage` tool
returned to the sending teammate. They were reported to the chief by the
sender and recorded as the transport receipt; the owner neither saw nor
relayed either message.

### The chief's own closing line

```
H001 resolved sent_by=product acked_by=engineering msg_id=127b960f-315c-4bb2-9e0b-d21683f0b63b
H002 resolved sent_by=qa      acked_by=engineering msg_id=1f3ff707-1050-4f16-873c-efaef2985d62
```

It matches the database exactly. That is the check that matters: the summary a
model produces and the record a reader can audit say the same thing.

### The exported view

`views/handoffs.md`, written by `cabinet_export_company`:

```
| Handoff | Batch | From | To | State |
| --- | --- | --- | --- | --- |
| H001 | B001 r1 | product | engineering | resolved |
| H002 | B001 r1 | qa | engineering | resolved |
```

### The peer registry the service wrote

`runtime/peers.json`, mode 0600:

```json
{"addresses": {"chief-of-staff": "main", "engineering": "engineering",
               "product": "product", "qa": "qa"},
 "chief": "cabinet-chief-o2probe",
 "peers": ["architect", "brand", "cabinet-chief-o2probe", "cfo",
           "chief-of-staff", "counsel", "delivery-lead", "design",
           "engineering", "main", "marketing", "product", "qa"]}
```

## What the roles discovered, and why it is the interesting part

**A teammate cannot reach its chief by the chief's session name.** Engineering
reported, in its own words:

> I've hit a routing snag: my task said to report to a chief at address
> `cabinet-chief-o2probe`, but that address resolves to my own session, and
> neither `team-lead` nor `main` are registered company peers.

Product refused to work around it rather than pretend:

> I attempted to complete this per the instructions but ran into a routing
> dead end that I don't think I should paper over.

This is the F1 name-collision hazard in a second form. From *inside* an
in-process teammate, the chief's own session name resolves to the session the
teammate belongs to. The address that reaches the chief's main conversation is
`main`, which matches F1's subagent-to-parent probe.

Two things followed, and both are the mechanism working rather than failing:

- The dispatch hook **denied** the messages, because `main` was not in the
  registry. A refusal is what an unregistered recipient is supposed to get.
- The chief called `cabinet_register_staff` again with
  `{"role": "chief-of-staff", "native_address": "main"}` (event 8, 04:21:08),
  the service rewrote `peers.json`, and every later message went through. The
  registry is the single place that had to change, which is the property the
  design was aiming for.

**The owner's instruction file was wrong about this address and the company
corrected itself.** No owner intervention was needed between 04:18 and 04:22.

## Two environment facts this run established

| Capability | Status | Evidence |
| --- | --- | --- |
| `claude --bg` ignores `--session-id` | **confirmed** | Launcher stderr, verbatim: `warning: --bg manages the session id; ignoring --session-id (use --resume <id> to continue an existing session)`. The launch record's `session_id` is therefore Cabinet's own identifier for the launch, not the native session id. The lease is taken under it and the company is consistent, but the two are not the same number. |
| A `--bg` session has **no process ancestry** back to its launcher | **confirmed** | First attempt failed with `BLOCKED: LAUNCH_HOST_MISMATCH: this server was started by process 38776, not by the launched session 38748`. `ps` afterwards: pid 38748 was gone, and 38776 was a `claude bg-spare` process whose own parent was 38768. The launcher's `os.execve`'d process exits and the background service is reparented. |
| A teammate addresses its chief as `main`, not by the chief's session name | **confirmed** | Quoted above, reported independently by two teammates. |
| The chief's permission allowlist removes per-call prompts | **confirmed** | Sixteen service tool calls, three `Agent` dispatches and repeated `SendMessage` calls under `permissions.defaultMode: manual`, with no permission prompt and no stall. Before this change F4b's concern was that manual mode would prompt on every call. |
| `--agent cabinet:chief-of-staff` under `--plugin-dir` | **warned, then worked** | Launcher stderr said `warning: no agent named 'cabinet:chief-of-staff' — spawning with default template`, but the session header showed `@cabinet:chief-of-staff` and the chief loaded `Skill(cabinet:coordination-rules)` successfully. The warning appears to be emitted before plugin agents are resolved. Recorded as observed rather than explained. |

### What the second finding changed in the code

The foreground host binding — "this MCP server's parent process is the process
that wrote the launch record" — cannot hold for a detached session, and
asserting it anyway would be the unenforced claim rule six forbids. So a
background launch record now carries `background: true` and `written_epoch`,
and `cabinet-service.check_background_host` binds it to **the per-launch
capability plus a 120-second window** instead. A record left behind in a shell
profile and picked up an hour later is refused; the foreground path is
unchanged and still requires the parent. This is a weaker binding than the
foreground one, it is weaker on purpose, and `cabinet_doctor` says so in its
launch line.

## What was not observed

| Item | Status | Why |
| --- | --- | --- |
| Idle-wake toward a `--bg` peer that is not a child process | **not_run** | F1's open caveat asks specifically for a *Superset-launched* worker, because a plain `--bg` peer started from this session's shell is still a child of it and would re-answer the question F1 already answered. Superset authentication is unavailable (`superset auth whoami` → `Not logged in`), which is O4's recorded prerequisite, so the probe that would settle it cannot be run yet. |
| The owner approval dialog | not run here | Unchanged from F4b. This exchange deliberately used clarification handoffs, which need no batch approval. |
| Retry, blocked transport and correction resolution over native transport | not run here | Both delivery attempts succeeded on the first try, so no probe came due. These paths are `unit_verified` in `tests/cabinet/test_handoffs.py`, not `native_verified`. |
| A worker (`implementer`, `test-runner`) registering its address | not run here | Workers are O4's, and their launch is blocked on Superset authentication. `cabinet_register_session` is `unit_verified`. |

## One side effect worth knowing about

The **failed** first launch created a directory under the owner's real
`~/.cabinet`. When the restricted launch was refused, the service degraded to
an ordinary read-only connection, and an ordinary connection resolves its
repository from `git remote get-url origin` in the working directory — this
worktree. It therefore opened `~/.cabinet/repos/amitbaz-ai-marketplace/`, and
opening a company creates it.

What was created: an empty schema-2 database and an `identity.json`, zero rows
in every table, no owner content. The owner's real company
(`amitbaz-career-platform`) was not opened and not modified. The directory was
moved to the session scratchpad rather than deleted, so it is recoverable.

The generalisation matters more than the incident: **a refused restricted
launch does not stop, it falls back to a read-only connection on whatever
company the current directory implies, and that fallback can create a company
directory as a side effect of a failure.** A diagnosis connection arguably
should not create anything. Recorded here for whoever owns that decision.

## Reproducing it

The synthetic company, the instruction file and the launch outputs live under
the session scratchpad and are not committed. To repeat: write an instruction
file, point `CABINET_HOME` at an empty directory, run the launcher command at
the top of this page, read the database read-only, then `claude stop` and
`claude rm` the session. Do not point it at a real company.
