# F4 service smoke — the MCP surface, observed

Recorded by task F4b on 2026-09-10, on the owner's macOS machine (Darwin
25.6.0, arm64), from worktree `codex/cabinet-company-design` at `05b9bc3` plus
the F4b working tree. Claude Code 2.1.267, resolved at `~/.superset/bin/claude`.

Everything below ran against a **synthetic company**: a scratch checkout whose
`origin` is `https://github.com/demo/company.git`, with `CABINET_HOME` pointed
at a scratch directory. No real company directory was opened, and
`~/.cabinet/repos/amitbaz-career-platform` was never touched. Paths are
abbreviated to `<scratch>`; nothing here contains a capability, a token or
another session's name.

Status is `supported`, `unsupported` or `not_run`. `not_run` never means
"probably fine".

| Item | What was probed | Status |
| --- | --- | --- |
| a | `cabinet-service` under a scripted stdio client | supported |
| b | `claude -p` lists and calls the tool over `--mcp-config` | supported |
| c | The chief's `--tools` value and the MCP tool names | supported — settles F4a concern 1 |
| d | `cabinet-launch --dry-run` | supported |
| e | An owner dialog from a `-p` session | **unsupported in print mode** |
| — | A real owner dialog in an interactive session | **not_run — awaiting the owner** |

## a. The service, driven by a scripted client

`python3 <scratch>/smoke_client.py` starts the real
`plugins/cabinet/scripts/cabinet-service` as a subprocess with
`CABINET_HOME=<scratch>/cabinet` and the scratch checkout as its working
directory, then speaks the protocol directly. The service resolved its own
identity from `git remote get-url origin`, opened
`<scratch>/cabinet/repos/demo-company`, and served. Exit status 0 on stream
close.

Long results are elided at `…`; the shapes are verbatim.

```
client {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{"elicitation":{"form":{}}},"clientInfo":{"name":"cabinet-smoke","version":"1"}}}
server {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-11-25","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"cabinet","version":"0.9.0"}}}
client {"jsonrpc":"2.0","method":"notifications/initialized"}
client {"jsonrpc":"2.0","id":2,"method":"ping"}
server {"jsonrpc":"2.0","id":2,"result":{}}
client {"jsonrpc":"2.0","id":3,"method":"tools/list"}
server {"jsonrpc":"2.0","id":3,"result":{"tools":[{"name":"cabinet_snapshot","description":"Company identity, the current batch, …","inputSchema":{"type":"object","properties":{"limit":{"type":"integer"}},"required":[],"additionalProperties":false},"annotations":{"readOnlyHint":true,"openWorldHint":false}}, … ]}}
client {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"cabinet_doctor","arguments":{}}}
server {"jsonrpc":"2.0","id":4,"result":{"content":[{"type":"text","text":"{\"checks\":[{\"check\":\"store\",\"status\":\"open\",…},{\"check\":\"identity\",\"status\":\"bound\",\"detail\":\"demo/company\"},{\"check\":\"launch\",\"status\":\"ordinary\",\"detail\":\"reads only; mutation needs a verified launch\"},{\"check\":\"tools\",\"status\":\"ok\",\"detail\":\"4 of 19 operations exposed\"}],\"ok\":true}"}],"structuredContent":{…},"isError":false}}
client {"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"cabinet_propose_batch","arguments":{"body":{"batch_id":"B001"}}}}
server {"jsonrpc":"2.0","id":5,"result":{"content":[{"type":"text","text":"{\"error\":{\"code\":\"RESTRICTED_SESSION_REQUIRED\",\"message\":\"cabinet_propose_batch needs the verified restricted launch; this connection may only read\"}}"}],"structuredContent":{"error":{"code":"RESTRICTED_SESSION_REQUIRED",…}},"isError":true}}
client {"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"cabinet_snapshot","arguments":{}}}
server {"jsonrpc":"2.0","id":6,"result":{"content":[{"type":"text","text":"{\"batch\":{\"batch_id\":\"B001\",\"digest\":\"c6359c83dd4b…\",\"state\":\"proposed\",…},\"company\":{\"connection\":\"ordinary\",\"holds_lease\":false,\"repo\":\"demo/company\",…}}"}],…,"isError":false}}
client {"jsonrpc":"2.0","id":7,"method":"nope/nope"}
server {"jsonrpc":"2.0","id":7,"error":{"code":-32601,"message":"unknown method nope/nope"}}
```

Four things this settles. The ordinary connection lists **4 of 19** operations,
because it holds no launcher context. A writing name called anyway comes back
as an MCP tool error carrying `RESTRICTED_SESSION_REQUIRED`, not as a protocol
error and not as a silent failure. The server declares `tools` and nothing
else. An unknown method is `-32601`.

## b. Claude lists and calls the tool

Run from the scratch checkout:

```
claude -p --restricted --strict-mcp-config \
  --mcp-config <scratch>/ordinary-mcp.json \
  --allowedTools "mcp__cabinet__cabinet_doctor" \
  --output-format json "Call the cabinet_doctor tool once and reply with its JSON only."
```

`subtype: success`, `is_error: false`, `num_turns: 3`, `duration_ms: 6063`. The
reply was the doctor payload verbatim, including
`{"check":"tools","status":"ok","detail":"4 of 19 operations exposed"}`.

**The first attempt, without `--allowedTools`, was denied**: `I don't have
permission to use the cabinet_doctor tool — the call was denied.` That is the
permission layer, not the tool layer — a restricted print-mode session has no
way to answer a permission prompt. It matters for the chief, whose profile sets
`permissions.defaultMode: "manual"`: every Cabinet tool call in an interactive
chief session will raise a permission prompt unless the profile also allows
those names. Recorded as a decision for O1 rather than changed here, because
widening `permissions.allow` is a profile change with its own review.

## c. `--tools` does not gate MCP tool names

This settles F4a's first concern. Same command as (b) plus the chief's exact
`--tools` value:

```
claude -p --restricted --strict-mcp-config --mcp-config <scratch>/ordinary-mcp.json \
  --tools Read,Grep,Glob,Skill,Agent,SendMessage,ListAgents \
  --allowedTools "mcp__cabinet__cabinet_doctor" --output-format json \
  "Call the cabinet_doctor tool once. Reply with its JSON only, or with exactly NO_CABINET_TOOL if no such tool is available to you."
```

The child called the tool and returned its JSON. `num_turns: 2`,
`duration_ms: 5239`.

The control run, same flags without `--allowedTools`, asked the child to name
every tool it could call. Verbatim:

```
Agent, Glob, Grep, ListAgents, Read, SendMessage, Skill,
mcp__cabinet__cabinet_context, mcp__cabinet__cabinet_doctor,
mcp__cabinet__cabinet_snapshot, mcp__cabinet__cabinet_wait_events
```

So `--tools` did narrow the built-in set to exactly the seven named — no
`Write`, no `Edit`, no `Bash`, no `WebFetch` — and left every MCP tool the
server offered. **Decision: `include_service_tools_in_tools_flag` stays
`False`**, which is the brief's argv. `cabinet-launch` records that decision as
a named constant, so a future change to it is deliberate.

## d. The launcher, dry run

```
CABINET_HOME=<scratch>/cabinet cabinet-launch --dry-run --repo demo/company \
  --assignment smoke --claude ~/.superset/bin/claude --plugin-root <repo>/plugins/cabinet
```

Exit 0. The printed `argv` is the F4a chief command line exactly:

```
~/.superset/bin/claude --restricted --strict-mcp-config
  --mcp-config <company>/runtime/profiles/<launch>.mcp.json
  --settings   <company>/runtime/profiles/<launch>.settings.json
  --plugin-dir <repo>/plugins/cabinet
  --agent cabinet:chief-of-staff
  --add-dir <company>/views --add-dir <repo>/plugins/cabinet
  --tools Read,Grep,Glob,Skill,Agent,SendMessage,ListAgents
  --session-id <uuid> --name cabinet-chief-smoke
```

The child environment carried `CABINET_PROFILE_KIND=chief`,
`CABINET_CHIEF_NAME=cabinet-chief-smoke` and `CABINET_PEER_REGISTRY`, plus an
allowlisted `PATH`, `HOME`, `LANG`, `TERM` and `TMPDIR`. Five files were
written at mode 0600 under `runtime/profiles/`, except the peer registry which
sits under `views/` so a sandboxed worker can still read it.

**No capability appears in the argv, in the environment, or in the printed
report.** The launcher asserts that itself before printing: `_refuse_to_reveal`
fails the launch rather than emitting a description the capability can be read
out of. Only the capability's SHA-256 goes into the launch record.

## e. The owner dialog from a print-mode session

The restricted launch was exercised end to end. Using the MCP configuration
`cabinet-launch` had just written, from the scratch checkout:

```
claude -p --restricted --strict-mcp-config --mcp-config <company>/runtime/profiles/<launch>.mcp.json \
  --tools Read,Grep,Glob,Skill,Agent,SendMessage,ListAgents \
  --allowedTools "mcp__cabinet__cabinet_doctor mcp__cabinet__cabinet_acquire_lead mcp__cabinet__cabinet_request_owner_approval" \
  --output-format json "…call doctor, then acquire_lead, then request_owner_approval for B001 revision 1…"
```

`subtype: success`, `num_turns: 4`, `duration_ms: 9455`. Two results, verbatim:

```json
{"check":"launch","status":"restricted","detail":"role chief-of-staff"}
```

```json
{"error": {"code": "ELICITATION_UNSUPPORTED",
           "message": "the connected client cannot show the owner a form dialog, so nothing can be approved from this session"}}
```

Read both. The first says the capability handshake worked: the service read the
launch record and the capability from their private files, verified the digest,
and served the writing surface. `cabinet_acquire_lead` then took the lease under
the launcher's session id, which the event log confirms:

```
1 lease.acquired implicit-8fc639590a21      (the seeding process)
2 batch.proposed B001
3 lease.acquired ba834641-…                 (generation 2, the launched session)
```

The second says **Claude Code 2.1.267 in `-p` (print) mode does not advertise
form elicitation**, so approval refuses. `grants` is empty and no
`approval.requested` event exists: the refusal happens before anything is
recorded, so a client that can never answer leaves no pending question behind.

This is the correct behaviour and it is also a real limit: **a print-mode
session can never approve a batch.** The chief must run interactively.

### The gate that is still open

A real owner dialog needs the owner. It was **not run**, and no attempt was
made to simulate one: an approval mechanism proved by a fabricated answer
proves nothing. What is missing is one interactive session, started by the
owner through `cabinet-launch`, calling `cabinet_request_owner_approval` on a
synthetic batch, and the owner answering it in the dialog. That is an approval
**mechanism** test on synthetic content, not approval of any business batch.

Until that runs, the approval path is `unit_verified` and its transport is
`native_verified` only up to the point where the client refuses. The ledger
records it as awaiting the owner.

---

# Fix round 1 — the launch binding, proved through a real exec

Recorded 2026-09-10, same machine and same synthetic `demo/company`.

The first F4b smoke never ran `cabinet-launch` for real: it used `--dry-run`
and then started Claude by hand. Binding the launch to the process that made it
meant that shortcut no longer proves anything, so the launcher was run for
real, with `--claude` pointing at a wrapper that `exec`s Claude with print mode
and a permission allowlist. **Both of those flags are the harness's, not the
launcher's.** `exec` keeps the process identifier, which is the whole point.

| Item | What was probed | Status |
| --- | --- | --- |
| f | A real `os.execve` launch reaches a working chief | supported |
| g | The launch binds to the process that made it | supported |
| h | A spent record replayed elsewhere | refused, read-only |
| i | Claude authenticating under an allowlisted environment | supported — needs `USER` and `LOGNAME` |

## i. The environment defect a real launch found first

The first real launch failed:

```
{"subtype":"success","is_error":true,"result":"Not logged in · Please run /login"}
```

The launcher hands the child an allowlisted environment, and that allowlist was
`PATH, HOME, LANG, LC_ALL, TERM, TMPDIR`. Measured directly, one variable set
per run, from a scratch directory:

```
('PATH','HOME')                    -> is_error=True   'Not logged in · Please run /login'
('PATH','HOME','USER','LOGNAME')   -> is_error=False  'OK'
```

`USER` and `LOGNAME` are now in the launcher's `INHERITED` tuple. They name the
account; the credential itself stays where the profile's deny rules already
keep it out of every file tool's reach. Every earlier probe in this document ran
Claude with the full inherited environment, so none of them could have found
this — the launcher's own exec path had never been exercised.

## f and g. The real launch

```
cd <scratch>/work
CABINET_HOME=<scratch>/cabinet cabinet-launch --repo demo/company \
  --assignment smoke --claude <scratch>/claude-print-wrapper \
  --plugin-root <repo>/plugins/cabinet
```

`subtype: success`, `num_turns: 6`, `duration_ms: 13540`. The chief called
`cabinet_doctor`, `cabinet_acquire_lead`, then `cabinet_doctor` again:

```json
{"check":"launch","status":"restricted","detail":"role chief-of-staff"}
generation from acquire_lead: 1
{"check":"lease","status":"held","detail":"generation 1"}
```

`launch: restricted` is the host binding passing: the spawned MCP server's
parent process was the process that wrote the launch record, matched on both
its identifier and its start time, across `cabinet-launch` → `execve` wrapper →
`exec` Claude → spawned server. The record on disk afterwards read
`lease_generation = 1`, so the generation renewal works and a reconnect under
the same record will still verify.

Before the harness added `--allowedTools`, the same launch answered: `the tool
permission for cabinet_doctor hasn't been granted in this session`. That
confirms item (b)'s finding on the real chief profile, and it is O1's decision.

## h. The spent record, replayed

After the launched session exited, its record and capability were pointed at a
new `cabinet-service` started from an ordinary shell:

```
cabinet-service: LAUNCH_HOST_MISMATCH: this server was started by process 92250, not by the launched session 91180
{'check': 'launch',  'status': 'refused',  'detail': 'LAUNCH_HOST_MISMATCH: …'}
{'check': 'lease',   'status': 'elsewhere','detail': 'another lead holds generation 1'}
{'check': 'tools',   'status': 'ok',       'detail': '4 of 19 operations exposed'}
```

Refused, degraded to the read-only surface, and `doctor` names the check that
failed. Possession of the two file paths is no longer sufficient to obtain a
writing connection.

## What is still not proved

The owner-dialog gate is unchanged and still **awaiting the owner**. Nothing in
this round approached it: print mode still advertises no form elicitation, and
no dialog answer was simulated.
