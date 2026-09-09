# Cabinet: an operating AI company

Recorded: 2026-09-09. Source: the owner's design conversation in this worktree.

Status: owner-confirmed product requirements; proposed technical direction.
This document does not claim that the new runtime exists or has been tested.
The next implementation batch is described below for review.

## Resume here

Before continuing Cabinet work, read this document and inspect the current
implementation. Preserve the confirmed requirements when narrowing a delivery
batch. Report separately what is specified, implemented, and live-verified.
Continue from the next unfinished item; do not restart discovery of the owner's
vision or reinterpret an initial delivery as the complete product.

## The company the owner wants

The owner is building Career Platform into a business and is overwhelmed by
simultaneously acting as founder, product lead, technical lead, delivery lead,
developer, and QA. They are a frontend engineer; interpreting backend details
and coordinating many implementation sessions currently consumes their attention.

Cabinet should provide staff who understand the company, own responsibilities,
propose what comes next, communicate with each other, and move approved work
forward. The owner remains CEO and works primarily through one executive
assistant. The assistant explains company position, goals, progress, tradeoffs,
and decisions in business language. Technical evidence is available on request.

Success means useful business progress with less coordination and interpretation
required from the owner. More agents, tickets, reports, or activity are not
success measures. Product must be capable of recommending less work when that
is sufficient to test a business idea.

Development targets Claude Code only. Superset remains the owner's IDE.
The user expects to install its CLI later; installation is not verified.
Existing Codex packaging is legacy scope to handle explicitly during migration,
not a reason to build the new operating workflow for two platforms.

## Confirmed authority

| Area | Staff authority | Owner authority |
| --- | --- | --- |
| Company direction | Research and recommend goals and changes | Decide direction and amend the charter |
| Work batches | Prepare outcomes, scope, exclusions, dependencies, risks, and acceptance criteria | Approve each proposed batch before implementation |
| Implementation | Make ordinary technical decisions and coordinate work inside the approved batch | Approve expansion beyond its outcome or scope |
| GitHub management | Create and maintain authorized project tickets, hierarchy, dependencies, priorities, assignments, and accurate status | Inspect, redirect, and override when needed |
| Finance | Research costs, advise, forecast, and report | Make purchases and financial commitments; control pricing |
| External communications | Prepare the exact material and destination for review | Explicitly approve publishing or sending on the company's behalf |
| Release | Implement, verify, review, and combine approved changes into a release candidate | Approve making the candidate available to customers; this boundary is provisional |

Goal approval authorizes preparation, not implementation. A new ticket is not
approval to start it. Batch approval does not authorize purchases, public
communications, or release. Agent messages and ticket content cannot supply
owner consent. Learned preferences cannot bypass these boundaries.

Routine GitHub maintenance is authorized. It does not grant blanket authority
for public announcements or outreach in issue comments. Before enabling writes,
configure the authorized repository and operation types; review its visibility
to resolve public disclosure boundaries without asking about every routine edit.

## Core staff required in the first usable version

| Role | Exclusive responsibility |
| --- | --- |
| Executive assistant / chief of staff | Owner interface, decision capture, team startup and recovery, company briefs |
| Product lead | Recommend the next business outcome, use customer evidence, define acceptance, challenge unnecessary scope |
| Delivery lead | GitHub consistency, work ownership and dependencies, approved batch progress, follow-through on handoffs |
| Engineering lead | Technical decisions, implementation instructions, coordination of isolated coding workers, integration evidence |
| QA lead | Independent assessment of the intended behavior and verification evidence; route failures back to Engineering |

Staff may exchange questions and resolve ordinary disagreements directly.
The assistant receives consequential results and unresolved owner decisions;
the owner does not copy prompts, forward replies, or interpret technical disputes.
Engineering determines technical means within scope; Product owns intended
behavior; Delivery sequences work; QA owns its independent verification verdict.
Unresolved tradeoffs that change the approved outcome go through the assistant.

The wider company retains Design, Brand, Marketing/Growth, Finance, and
Legal/Privacy responsibilities. Product initially owns customer research and
feedback. These functions may be activated when relevant rather than kept
continuously running. Deferring their activation must not erase them from the
company design or defer a relevant financial/privacy decision.

## Reporting and intervention

- Session opening: company position, goal progress, active batch, relevant
  changes, and decisions needed from the owner.
- During work: interrupt only for owner decisions or developments too important
  to wait. Ordinary ticket changes appear in the next brief with their reason
  and effect, rather than an approval request for each edit.
- Batch completion: delivered business capability, verified evidence summarized
  plainly, remaining concerns, release status, and recommended next batch.
- Session closing: accomplishments, unfinished work, blockers, next actions,
  and the recovery checkpoint. A session ending does not complete a batch.

The owner can inspect detail, pause work, or redirect at any point. Pausing
stops new dispatches and requests active workers to stop safely; report actions
still in flight instead of claiming immediate cancellation.

## Proposed runtime

Use a Claude Code interactive lead with named teammates for the core staff.
Prefer native messaging for active discussion. Superset should provide isolated
implementation workspaces and their lifecycle once its CLI is available.
Treat session transport as an adapter so company records and approval state do
not depend on a particular pane or terminal ID.

This is a proposal, not a demonstrated installation. Check actual tool support
and permission behavior before dispatching. A missing transport must yield a
clear unavailable status, not a workflow asking the owner to ferry messages.

Three options were considered:

| Option | Fit and tradeoff |
| --- | --- |
| Existing Cabinet dispatches and notebooks | Preserves today's grants, but waiting for the next role run does not satisfy active coordination or execution ownership |
| Native Claude team plus durable Cabinet records | Preferred first route: direct communication without requiring a new messaging service; recovery and permission boundaries still require implementation and proof |
| Separate Superset sessions with a shared messaging service | Closer to the original setup and useful for isolated workers; adds session discovery, lifecycle, and transport dependencies. Evaluate if the native route fails the required tests |

The existing MemPalace integration is a possible transport for separate sessions,
not a new mandatory install dependency. Verify its availability and handoff
behavior before choosing it. Do not create a new broker by default when an
installed transport can satisfy the requirements.

## Communication that completes work

Every actionable handoff has a stable ID, batch revision, sender, recipient,
question or requested action, relevant evidence, and required response. Record
it before delivery. Track delivered, acknowledged, resolved, failed, and
superseded separately. Sending a message does not prove its recipient acted.

Delivery follows unresolved handoffs. Retry delivery without duplicating actions;
an offline recipient can be restarted or replaced from its recorded assignment.
Repeated failures become an explicit blocked state with a recovery action.
Technical clarification goes to the relevant staff member first. Only owner
authority, missing owner knowledge, or an unrecoverable operational problem
reaches the owner through the assistant.

Use direct messages for discussion and keep the resulting decision and its
reason in durable records. Avoid broadcast loops. The core acceptance example
is QA finding a failure, discussing it with Engineering, obtaining a correction,
and verifying it while Delivery updates the batch without owner message relay.

## Continuity across tomorrow

Maintain company context separately from runtime state:

- Charter, full vision, authority, goals, department remits, and decision
  history describe the company.
- Approved batch revisions, assignments, handoff records, evidence references,
  and checkpoints describe work authorized and performed.
- Runtime registrations map stable role and task IDs to replaceable sessions
  and workspaces. Record liveness observations with their time.

Use the existing resolved Cabinet home outside individual worktrees for runtime
records. The coordinator is their single writer; teammates return updates.
Serialized writes and an append-only journal must support rebuilding the latest
checkpoint after interruption. Specify and test crash handling before claiming
recovery. Preserve existing charter and notebook history during migration.

On startup, the lead loads these records, rechecks GitHub and actual workspaces,
reconciles partial actions, restores role assignments, and presents the opening
brief. It must not restart completed work, mistake an old session ID for a live
worker, or infer new approval from old discussion. GitHub status remains live
data; checkpoints are evidence of prior observations, not current truth.

Local records alone are not backup or cross-machine durability. Define an
explicit backup/export approach before making those claims. Abrupt termination
cannot guarantee a closing summary; recovery must use the last durable event.
No session or host running means work is paused, not secretly continuing.

## Permissions are part of the design

Retain enumerated read-only grants for advisory staff. Board writes can be
performed by a narrowly scoped executor under Delivery's direction, while the
coordinator remains the single writer of company records. Implementation
workers need a separately defined editing/testing boundary.

Do not grant broad shell access to all roles and keep claiming the current money
guarantee. Native team inheritance, communication tools, coordinator writes,
worker credentials, repository scripts, network access, and deployment-triggering
pushes all require explicit review. Combining code locally must not accidentally
release through CI. Teammate plan approval from the lead is not owner batch
approval. A proposed enforcement mechanism must be tested with denied actions
before describing it as a guarantee.

Plugin mechanisms must retain the repository's no-build, standard-library/POSIX
constraints. Platform tools are runtime prerequisites; plugin installation must
not download packages. Changes to existing Cabinet constraints must identify the
specific replacement mechanism rather than silently weakening the invariant.

## First implementation batch proposed for approval

Outcome: the core staff can carry one owner-approved Career Platform batch from
proposal through verified completion, communicate without the owner as courier,
and resume correctly in a new session.

Included: core role definitions, owner approval records, scoped board execution,
active handoffs, durable checkpoints and recovery, worker/workspace registration,
opening and closing briefs, owner pause/override, and the checks below.

Deferred: always-running service operation, all departments active concurrently,
cross-machine coordination, and automatic release. Automatic Superset workspace
creation requires installing and verifying its CLI. This prerequisite must be
resolved or an alternative automatic workspace path verified before calling the
complete batch operational; manual message forwarding is not an accepted fallback.

Acceptance requires recorded live evidence, not merely prompt files:

1. A proposed batch cannot launch implementation until its exact scope revision
   has owner approval; changing that scope invalidates dispatch authority.
2. Product and Engineering resolve a requirement question without owner relay.
3. Delivery makes an authorized ticket update, verifies it live, and explains its
   business consequence in the brief without seeking permission for each edit.
4. QA routes a failure to Engineering; a fix is verified against the resulting
   revision before Delivery records completion.
5. Duplicate messages do not create duplicate tickets or implementation workers.
6. A stopped teammate is detected and its assignment recovered or explicitly
   blocked, with no invented progress.
7. A fresh lead session recovers the same vision, approved scope, unresolved
   handoffs, and verified results without asking the owner to reconstruct them.
8. An attempted unapproved scope expansion, financial action, external send,
   release, or unsafe deployment-triggering push is blocked at its action boundary.
9. Opening and closing briefs distinguish completed, verified, underway, blocked,
   and released work in business language. Owner pause prevents new dispatches.

Validate mechanisms first with synthetic fixtures. Run a real bounded Career
Platform batch only after the owner approves that business batch. Inspect that
repository's own instructions before any changes. Time to first verified batch
and owner interventions caused by coordination failures are initial usefulness
measures; do not invent numerical targets or delivery estimates.

## Evidence and next work

Inspected 2026-09-09: Cabinet at repository commit `0c9978b`; Claude Code CLI
reports `2.1.267`. The earlier Superset CLI lookup returned command not found.
Neither finding proves that runtime team features or workspace integration work.

Current Cabinet explicitly excludes implementation supervision in
`plugins/cabinet/README.md` under “What Cabinet does not do.” Its standup command
routes messages to a recipient notebook for the next run; delivery's current
tools are read-only. Those are concrete gaps to replace, not capabilities to
assume. The older state-location text in AGENTS.md also differs from the shipped
skill and README; migrate from observed current state.

Claude documents direct teammate messaging and reusable agent definitions, but
agent teams are experimental and in-process teammates are not restored on resume.
Permission behavior needs inspection; native leader plan approval is distinct
from owner consent. Source: [Claude Code agent teams](https://code.claude.com/docs/en/agent-teams).

Superset documents workspace and agent lifecycle controls. Source:
[Superset CLI reference](https://github.com/superset-sh/superset/blob/main/apps/docs/content/docs/cli/cli-reference.mdx).

Next: review this proposed runtime and implementation batch; resolve the action
enforcement and transport details in the implementation plan; implement and run
the acceptance checks. The requirements above remain the target across sessions.
