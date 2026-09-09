# AI Plugin Marketplace

A plugin marketplace for reusable AI coding-agent workflows. Supports **Claude Code** and **OpenAI Codex** with native packaging for each platform.

## Available Plugins

| Plugin | Version | Description |
| --- | --- | --- |
| [groundwork](./plugins/groundwork) | 1.8.1 | Extension for `obra/superpowers` that adds parallel reconnaissance, discussion, and planning before committing to code. **Requires Superpowers.** |
| [muster](./plugins/muster) | 0.2.0 | The executive team a solo founder cannot afford to hire: six roles with their own remits and memory, one chief-of-staff brief a day, and a money invariant enforced by tool grants. |

## Groundwork prerequisite: Superpowers

Groundwork extends [`obra/superpowers`](https://github.com/obra/superpowers); it does not bundle or replace it. Install Superpowers for the coding agent you use before installing Groundwork.

### Claude Code

```text
/plugin install superpowers@claude-plugins-official
```

### Codex CLI

Open the official plugin catalog:

```text
/plugins
```

Search for **Superpowers** and select **Install Plugin**.

In the Codex app, open **Plugins** in the sidebar and install **Superpowers** from Developer Tools.

## Install this marketplace

### Claude Code

Add the marketplace:

```text
/plugin marketplace add amitbaz/ai-marketplace
```

Install Groundwork:

```text
/plugin install groundwork@amitbaz
```

Install Muster:

```text
/plugin install muster@amitbaz
```

Adding the marketplace only registers the catalog. Plugins still need to be installed separately.

To refresh the marketplace after updates:

```text
/plugin marketplace update amitbaz
```

### Codex CLI

Add the GitHub marketplace:

```text
codex plugin marketplace add amitbaz/ai-marketplace --ref main
```

Install Groundwork:

```text
codex plugin add groundwork@amitbaz
```

Install Muster (Codex gets the `coordination-rules` skill only — see the
[Muster README](./plugins/muster/README.md)):

```text
codex plugin add muster@amitbaz
```

To refresh the Git-backed marketplace later:

```text
codex plugin marketplace upgrade amitbaz
```

Workspace admins can also import `https://github.com/amitbaz/ai-marketplace` from **Workspace settings → Plugins → Marketplaces**. Codex discovers the native marketplace manifest at `.agents/plugins/marketplace.json`.

## Use Groundwork

### Claude Code

```text
/groundwork Investigate why the customers table in dashboard does not scroll.
```

### Codex

Invoke the installed skill:

```text
$groundwork Investigate why the customers table in dashboard does not scroll.
```

Groundwork runs the same contract on both platforms: parallel read-only reconnaissance → Superpowers brainstorming/discussion → Superpowers implementation planning. It stops before implementation and hands the accepted plan to a Superpowers execution workflow.

See the [Groundwork README](./plugins/groundwork/README.md) for the complete workflow, dependency rules, and platform differences.

## Use Muster

```text
/muster:hire
```

Reads your repository's documentation, board and history, drafts a company
charter from what it finds, asks only about what it could not find, and hires
the roles your stage needs. Then, at the start of a working session:

```text
/muster:standup
```

Six roles — delivery, architecture, QA, counsel, finance and brand — report to
a chief of staff who hands you one brief of at most five items. No agent in
Muster can spend money; that is enforced by tool grants rather than promised
in a prompt. See the [Muster README](./plugins/muster/README.md).

## Repository Structure

```text
ai-marketplace/
├── .github/
│   └── workflows/
│       └── validate.yml              # manifest + adapter-boundary checks
├── scripts/
│   └── check-adapter-boundary.py     # enforces shared-skill/thin-adapter split
├── .agents/
│   └── plugins/
│       └── marketplace.json          # Codex marketplace
├── .claude-plugin/
│   └── marketplace.json              # Claude Code marketplace
├── plugins/
│   ├── groundwork/
│   │   ├── .codex-plugin/
│   │   │   └── plugin.json           # Codex plugin manifest
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json           # Claude Code plugin manifest
│   │   ├── skills/
│   │   │   └── groundwork/
│   │   │       └── SKILL.md          # canonical Groundwork workflow (both platforms)
│   │   ├── agents/                   # Claude Code recon agents
│   │   ├── commands/                 # Claude Code /groundwork adapter
│   │   └── README.md
│   └── muster/
│       ├── .codex-plugin/
│       │   └── plugin.json           # Codex plugin manifest
│       ├── .claude-plugin/
│       │   └── plugin.json           # Claude Code plugin manifest
│       ├── skills/
│       │   └── coordination-rules/
│       │       └── SKILL.md          # the rules every role runs under
│       ├── agents/                   # the six roles, read-only by tool grant
│       ├── commands/                 # /muster:hire, :standup, :decide, ...
│       ├── FILES.md                  # what Muster writes and who writes it
│       └── README.md
└── README.md
```

The two marketplace manifests intentionally coexist. Claude Code uses `.claude-plugin/marketplace.json`; Codex uses `.agents/plugins/marketplace.json`.

Groundwork follows a **shared workflow contract → thin platform adapters** architecture. `plugins/groundwork/skills/groundwork/SKILL.md` is the single source of truth for the workflow on every platform. Codex consumes it directly as `$groundwork`; Claude's `commands/groundwork.md` invokes it and adds only Claude's dispatch syntax, recon subagent types, and `$ARGUMENTS` handling. `scripts/check-adapter-boundary.py` fails CI when an adapter starts duplicating the shared workflow.
