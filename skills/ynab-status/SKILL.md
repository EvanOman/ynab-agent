---
name: ynab-status
description: Quick overview of YNAB budget status. Shows spending vs targets, pace, and flags. Use when the user wants to check their budget status.
allowed-tools: Bash(uvx --from * ynab-agent *), Bash(cat *)
user-invocable: true
---

**Repo path:** Set `YNAB_AGENT_DIR` env var if repo is not at `~/dev/ynab-agent`. All commands use `YNAB_AGENT_DIR="${YNAB_AGENT_DIR:-$HOME/dev/ynab-agent}"` as default.

# YNAB Status

Quick read-only budget overview.

## Workflow

### 0. Load philosophy and context

```bash
cat "$YNAB_AGENT_DIR/philosophy.md" 2>/dev/null
cat ~/.config/ynab-agent/context.md 2>/dev/null
```

- **philosophy.md** shapes your tone. Connect the numbers to the bigger picture — not just "90% spent" but what that means for the rest of the month.
- **context.md** has pay schedule and preferences.

### 1. Fetch current month budget

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch budget-month
```

### 2. Present status

Format the budget data as a status overview. Filter out hidden categories, internal categories, and the "Uncategorized" / "Inflow: Ready to Assign" rows from the main table.

**Calculate pace for each category:**
- Days elapsed vs days in month (percentage)
- Budget used vs budget total (percentage)
- If % budget used > % month elapsed + 20pp → "tight"
- If balance < 0 → "overspent"
- If activity = 0 and budgeted > 0 and >30% of month elapsed → "inactive"
- Otherwise → "on track"

**Format:**

```
Budget Status — April 2026 (18 days remaining)

Category              | Budgeted | Spent     | Remaining | Target  | Pace
🍌 Groceries          | $500.00  | -$312.50  | $187.50   | $500.00 | ✅ On track
🍽 Dining Out          | $200.00  | -$187.30  | $12.70    | $200.00 | ⚠ Tight
🚗 Transportation      | $150.00  | -$89.00   | $61.00    | $150.00 | ✅ On track
...

Flags:
- ⚠ Dining Out: 94% spent with 60% of month remaining
- ✅ 8 of 12 categories on track

Ready to Assign: $87.00
```

**Group by category group** if there are many categories. Show group subtotals.

### 3. Offer next steps

If there are issues (overspent, tight), mention that `/ynab-rebalance` can help redistribute funds. If everything looks good, just say so.
