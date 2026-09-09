# Handoff to the Cabinet implementation agent

Paste the following prompt into the implementation session with this branch
available. The prompt does not depend on remembering the design conversation.

```text
Implement the Cabinet AI Company plan in this repository.

Read AGENTS.md, then:
1. docs/superpowers/specs/2026-09-09-cabinet-company-design.md
2. docs/superpowers/plans/2026-09-09-cabinet-ai-company.md
3. docs/superpowers/plans/2026-09-09-cabinet-contracts.md
4. docs/superpowers/plans/2026-09-09-cabinet-progress.md
Follow the master into the foundation, operating-team and acceptance task files.

The target is a Claude Code plugin that operates as my AI company. I am the
founder. I approve proposed batches; staff then coordinate implementation,
GitHub management and QA without me forwarding their messages or interpreting
technical details. I receive business-language opening and closing briefs and
can step in when needed. Only I make financial commitments. External publication
and releases require my approval. Product recommends what the company does next.

The existing Cabinet is substantially below this target. Do not conclude that
its notebooks, FOR-role sections, standups or read-only roles are sufficient.
Reuse them only where they pass the new behavioral requirements. Active
communication and recovery across sessions are mandatory in the first usable
core, alongside Assistant, Product, Delivery, Engineering and QA. Preserve the
wider department vision even when those departments are activated later.

Execute the numbered tasks and update the progress/evidence record after each
reviewable unit. Use executing-plans; do not delegate plugin coding to additional
agents unless I authorize it. The native staff/worker sessions explicitly required
by the acceptance scenarios are part of testing the plugin. Keep interfaces
consistent. Do not reduce the scope or
replace missing live proof with mocks, prose, or “good enough for now.” If a
platform assumption fails, record the blocker, continue independent work, and
propose a replacement that preserves the required outcome.

My authorization to implement this plugin is not approval for an arbitrary
Career Platform business batch, financial action, public message, push, or
release. Ask only for those concrete approvals or genuinely missing prerequisites.
Normal implementation decisions inside this plan do not need repeated approval.

Completion must show R01–R18 evidence, including a QA-to-Engineering correction
without my message forwarding and a fresh session recovering the same company
goals, approved scope and unfinished work. Distinguish local implementation,
unit tests, native integration proof and the separately approved business pilot.
Begin with the first unfinished task; do not restart the vision discussion.
```

The planning branch is `codex/cabinet-company-design`. Transfer the entire branch
or all linked documents, not only this prompt. The owner authorized publishing
this planning branch as a draft PR. Another worktree must start from a commit
containing the plan; an unrelated checkout of main will not contain it.
