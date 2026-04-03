---
name: ynab-setup
description: One-time setup for YNAB budget agent. Configure API token, select budget, seed decision history. Use when first setting up the YNAB agent.
allowed-tools: Bash(uvx --from * ynab-agent *), Read, Write, AskUserQuestion
user-invocable: true
---

**Repo path:** Set `YNAB_AGENT_DIR` env var if repo is not at `~/dev/ynab-agent`. All commands use `YNAB_AGENT_DIR="${YNAB_AGENT_DIR:-$HOME/dev/ynab-agent}"` as default.

# YNAB Setup

One-time setup for the YNAB budget agent.

## Steps

### 1. Check for API token

Check if `~/.config/ynab-agent/.env` exists and has a `YNAB_PAT` value:

```bash
cat ~/.config/ynab-agent/.env 2>/dev/null | grep YNAB_PAT
```

If not set, tell the user:
- Go to YNAB web app → Account Settings → Developer Settings
- Generate a Personal Access Token
- Save it to `~/.config/ynab-agent/.env` as `YNAB_PAT=<token>`

### 2. List plans and select

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent setup
```

This lists all available plans/budgets. Ask the user which one to use. Then:

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent setup --plan-id <selected-id>
```

For most users, `last-used` works fine as the plan ID.

### 3. Seed decision history

Pull the last 3 months of categorized transactions to bootstrap the history:

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent history seed --since "3 months"
```

This gives the agent a baseline for future categorization proposals.

### 4. Verify

Fetch categories to confirm everything works:

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch categories
```

Tell the user setup is complete and they can now use `/ynab` for budget check-ins.
