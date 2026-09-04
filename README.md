# AI Plugin Marketplace

A plugin marketplace for reusable AI coding-agent workflows. Supports **Claude Code** and **OpenAI Codex** with native packaging for each platform.

## Available Plugins

| Plugin | Version | Description |
| --- | --- | --- |
| [groundwork](./plugins/groundwork) | 1.3.0 | Extension for `obra/superpowers` that adds parallel reconnaissance, discussion, and planning before committing to code. **Requires Superpowers.** |

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

## Repository Structure

```text
ai-marketplace/
├── .agents/
│   └── plugins/
│       └── marketplace.json          # Codex marketplace
├── .claude-plugin/
│   └── marketplace.json              # Claude Code marketplace
├── plugins/
│   └── groundwork/
│       ├── .codex-plugin/
│       │   └── plugin.json           # Codex plugin manifest
│       ├── .claude-plugin/
│       │   └── plugin.json           # Claude Code plugin manifest
│       ├── skills/
│       │   └── groundwork/
│       │       └── SKILL.md          # Codex Groundwork workflow
│       ├── agents/                    # Claude Code recon agents
│       ├── commands/                  # Claude Code /groundwork command
│       └── README.md
└── README.md
```

The two marketplace manifests intentionally coexist. Claude Code uses `.claude-plugin/marketplace.json`; Codex uses `.agents/plugins/marketplace.json`. Groundwork keeps platform-specific orchestration at the edges while preserving the same research → discussion → planning workflow.
