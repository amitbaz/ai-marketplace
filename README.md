# AI Plugins Marketplace

A personal registry and distribution hub for custom AI assistant plugins and agent workflows.

## Repository Layout
ai-marketplace/
├── .claude-plugin/
│   └── marketplace.json
├── README.md
└── groundwork.md

## 1. .claude-plugin/marketplace.json
{
  name: amitbaz,
  owner: {
    name: Amit Baz
  },
  plugins: [
    {
      name: groundwork,
      source: ./,
      description: Specialized reconnaissance agents and code context tools.
    }
  ]
}

## 2. groundwork.md
---
name: groundwork
description: Specialized reconnaissance agents and code context tools for deep project analysis.
version: 1.0.0
---

# Groundwork Plugin

## Commands
When the /groundwork command is invoked, execute the reconnaissance workflow to analyze code architecture, context, and external dependencies.

## Reconnaissance Agents
* recon-code: Analyzes internal code structure, patterns, and logic.
* recon-context: Gathers structural metadata and environmental context.
* recon-external: Evaluates external dependencies, APIs, and integrations.

## 3. README.md
# AI Plugins Marketplace

A personal registry and distribution hub for custom AI assistant plugins and agent workflows.

## Installation

/plugin marketplace add amitbaz/ai-marketplace
/plugin install groundwork@amitbaz
