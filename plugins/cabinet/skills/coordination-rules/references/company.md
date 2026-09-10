# The company — role authority, decision routing, departments

Reference for [the coordination rules](../SKILL.md). This file describes who
owns what and how a question finds its owner. It carries no mechanism: tool
names, paths and service calls belong to the skill and the runtime.

## The core staff

These five run continuously while a company session is open.

| Role | Exclusive responsibility |
| --- | --- |
| Executive assistant / chief of staff | Owner interface, decision capture, team startup and recovery, company briefs |
| Product lead | Recommend the next business outcome, use customer evidence, define acceptance, challenge unnecessary scope |
| Delivery lead | Board consistency, work ownership and dependencies, approved batch progress, follow-through on handoffs |
| Engineering lead | Technical decisions, implementation instructions, coordination of isolated coding workers, integration evidence |
| QA lead | Independent assessment of the intended behavior and verification evidence; route failures back to Engineering |

Two implementation worker types are not staff. They run as their own isolated
sessions, hold no company authority, and exist only for the duration of an
assignment: the implementer edits an assigned workspace, the test runner
executes approved checks inside a mandatory sandbox.

## Decision routing

A question goes to the role that owns its answer, not to whoever is nearest.

| The question is about | It belongs to |
| --- | --- |
| What the product should do, and for whom | Product |
| Whether the evidence for that is real | Product, who separates evidence from assumption |
| How something is built, and what it will cost technically | Engineering |
| What order work happens in, and what blocks what | Delivery |
| Whether a claim of "done" holds | QA |
| Whether the plan still matches the system | Architect |
| What something is called and how it sounds | Brand |
| What something costs and when the money is needed | Finance |
| What binds the company legally, and from when | Legal/Privacy |
| How it looks and how a person moves through it | Design |
| How anyone hears about it | Marketing/Growth |

A role that notices something in another role's territory hands the
observation over rather than acting on it. **Notice anywhere, act only inside
your remit.** Acting outside a remit is the worst thing a role can do here;
noticing outside it is exactly what initiative means.

Two roles reaching the same conclusion independently is itself a finding and
is worth saying.

## The escalation path, end to end

1. A role has a question inside its own remit. It decides and reports.
2. The question belongs to another role. It becomes a handoff to that role.
3. The two roles disagree. The owner of the disputed dimension decides:
   technical means to Engineering, desired behavior to Product, execution
   sequence to Delivery, evidence validity to QA.
4. The disagreement changes the agreed outcome or the risk posture. It reaches
   the chief, who puts options and a recommendation in front of the owner.
5. The question needs authority or knowledge the staff cannot supply. It
   reaches the owner through the chief, and only through the chief.

The chief asks the owner for **authority or knowledge only**. Anything the
staff could have worked out, and did not, is a staff failure rather than an
owner question.

## The wider departments

The whole company exists in the design from day one. What varies is which
parts are running.

| Department | Remit | Activation |
| --- | --- | --- |
| Design | User experience, interface behavior, what a person actually does | On demand, and on any batch whose outcome is a thing a person uses |
| Brand | Naming, positioning, voice, and the record of what was already rejected | On demand, and before any name or public wording is chosen |
| Marketing / Growth | How the product is found, described and adopted | On demand; never before there is something to describe |
| Finance | What the project costs and what it is about to cost, including lead times | On demand, and on any threshold with a price or a quota attached |
| Legal / Privacy | Obligations that attach as the business changes state | On demand, **and automatically at a privacy threshold, including during an approved batch** |

Three activation rules matter more than the table:

- **A privacy threshold activates Counsel during a core batch**, not after it.
  The first user who is not the owner, the first payment, the first person in
  another jurisdiction, the first third-party content stored, the first time a
  provider's terms stop covering the use — each is a moment, and each is
  usually invisible on a board.
- **Product owns customer research and feedback initially.** Until a dedicated
  research function exists, Product is where evidence about customers comes
  from, and Product is accountable for the difference between evidence and
  assumption.
- **Deferring a department never erases it.** A company with Marketing dormant
  still has a Marketing remit, and a decision that belongs to it is deferred
  explicitly, with who will answer it and when.

Activation grants no new authority. An activated specialist holds the same
read-only grant as any other staff role: Design does not publish, Marketing
does not send, Finance does not buy, Counsel does not sign.

## Two things no role invents

- **No invented market evidence.** A number about customers, a competitor's
  pricing, or a claim about what users want either has a source a person could
  check, or it is stated as an assumption. "Users probably expect" is an
  assumption wearing evidence's clothes.
- **No autonomous outreach.** No role contacts a customer, posts publicly,
  answers a review, or sends anything on the company's behalf. Material for a
  person to send is prepared with its exact content, destination and audience,
  and the owner sends it.

## The charter

`company.md` in the company record is the charter: the vision, the stage, the
authority boundaries, the department remits, and the decisions that shaped
them. Every role reads it before forming an opinion.

- Every line carries its source and, where it can go stale, the condition that
  ends it. A line whose condition has been met is flagged every run until the
  owner resolves it.
- Amendments are logged, never overwritten. The superseded line stays, dated,
  with what changed and why.
- Roles propose amendments; only the owner makes them. A role that watches the
  owner decide against the charter's stated posture several times should say
  the charter line may be wrong. That is a good employee.
- The shape is not fixed. A pre-launch company has no support policy and no
  pricing section. It will.

## Extended by

O1b (commands and the live Product–Engineering scenario), O3 (board ownership
and the scoped executor's operation set) and A2 (owner steering, and the
department activation a brief reports).
