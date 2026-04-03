---
name: ynab
description: Full YNAB budget check-in. Walks through categorizing transactions, rebalancing budget, and reviewing status. The main entry point for budget management. Use when the user wants to do a budget check-in or manage their YNAB budget.
allowed-tools: Bash(uvx --from * ynab-agent *), Bash(echo *), Bash(cat *), Read, AskUserQuestion
user-invocable: true
---

# YNAB Budget Check-in

The full budget management workflow. Runs three steps in sequence:
1. **Categorize** uncategorized transactions
2. **Rebalance** budget allocations
3. **Status** review

Each step is conversational — you see what's happening and approve changes before they're applied. If a step has nothing to do, it's skipped.

**Repo path:** All commands use `YNAB_AGENT_DIR` which defaults to `~/dev/ynab-agent`. If the repo is cloned elsewhere, set this variable in your shell profile.

## Pre-flight

Check that setup is complete and load budget context:

```bash
YNAB_AGENT_DIR="${YNAB_AGENT_DIR:-$HOME/dev/ynab-agent}"
cat ~/.config/ynab-agent/config.json 2>/dev/null
```

If config doesn't exist or has no `plan_id`, tell the user to run `/ynab-setup` first.

**Load the agent's philosophy and budget context:**

```bash
YNAB_AGENT_DIR="${YNAB_AGENT_DIR:-$HOME/dev/ynab-agent}"
cat "$YNAB_AGENT_DIR/philosophy.md" 2>/dev/null
cat ~/.config/ynab-agent/context.md 2>/dev/null
```

- **philosophy.md** is the agent's soul — zero-based budgeting principles, tone, and how to frame every interaction. Read it and internalize it. It shapes how you present proposals, surface tradeoffs, and talk about money. Don't recite it — let it inform your voice.
- **context.md** has workflow preferences: pay schedule, category notes, rebalancing strategy. Apply relevant context throughout.
- If the user gives new hints or corrections during the session, offer to update context.md so they persist.

**context.md is for workflow preferences, not YNAB overrides.** Never use it to suppress, ignore, or override goals/targets from YNAB. When the user disagrees with YNAB data (e.g., a stale goal), suggest they fix it in YNAB first rather than papering over it in context.md.

## CLI Pattern

All CLI commands follow this pattern:

```bash
YNAB_AGENT_DIR="${YNAB_AGENT_DIR:-$HOME/dev/ynab-agent}"
uvx --from "$YNAB_AGENT_DIR" ynab-agent <command> [args]
```

## Step 1: Categorize

Follow the `/ynab-categorize` workflow:

1. Fetch uncategorized transactions
2. If none: say "No uncategorized transactions" and move to Step 2
3. If some: look up history, build proposal table, get approval, apply, record decisions

## Step 2: Rebalance

Follow the `/ynab-rebalance` workflow:

1. Fetch current month budget with targets
2. Analyze for over/under-funded categories
3. If no moves needed (everything within threshold): say "Budget looks balanced" and move to Step 3
4. If moves needed: propose, get approval, apply, record decisions

## Step 3: Status Review

Follow the `/ynab-status` workflow:

1. Fetch current month budget (may reuse data from Step 2 if just fetched)
2. Present the budget overview with pace indicators and flags
3. Highlight anything notable

## Wrap-up

Summarize what happened:
- N transactions categorized (M skipped)
- N budget moves applied
- Overall budget status

If there are things that need manual attention (split transactions, credit card issues), mention them.
