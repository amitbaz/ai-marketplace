---
description: Rebuild the current picture on demand from the tracker and pull requests — decisions needed, startable frontier, blocked, open PRs.
argument-hint: ""
---

# Muster — Claude Code adapter

This command is a thin adapter. The workflow — rebuilding state fresh from
the tracker every run, never from memory or a previous conversation — lives
in the canonical skill and is not repeated here.

**Invoke the canonical skill with the Skill tool:**

```
Skill(skill: "muster:standup")
```

If that skill does not load, read
`${CLAUDE_PLUGIN_ROOT}/skills/standup/SKILL.md` and follow it verbatim
instead.

$ARGUMENTS
