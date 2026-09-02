# AI Plugin Marketplace

A personal Claude Code plugin marketplace for reusable development workflows, agents, and commands.

## Available Plugins

| Plugin | Version | Description |
| --- | --- | --- |
| [groundwork](./plugins/groundwork) | 1.2.1 | Extension for `obra/superpowers` that adds parallel reconnaissance, discussion, and planning before committing to code. **Requires Superpowers.** |

## Installation

Groundwork is built as an extension/wrapper around [`obra/superpowers`](https://github.com/obra/superpowers). Install Superpowers first:

```text
/plugin install superpowers@claude-plugins-official
```

Then add this marketplace to Claude Code:

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

## Groundwork

Groundwork depends on Superpowers and does not bundle or replace it. If the required Superpowers skills are unavailable, `/groundwork` should stop rather than fall back to a reduced workflow.

Once installed, start a reconnaissance workflow with:

```text
/groundwork <problem>
```

Example:

```text
/groundwork Investigate why the customers table in dashboard does not scroll.
```

For the full workflow, dependency details, built-in engineering discipline, and recon-agent details, see the [Groundwork README](./plugins/groundwork/README.md).

## Repository Structure

```text
ai-marketplace/
├── .claude-plugin/
│   └── marketplace.json
├── plugins/
│   └── groundwork/
│       ├── .claude-plugin/
│       │   └── plugin.json
│       ├── agents/
│       ├── commands/
│       └── README.md
└── README.md
```

The marketplace catalog is defined in `.claude-plugin/marketplace.json`. Each plugin lives under `plugins/` and contains its own manifest and documentation.
