---
name: ynab-rebalance
description: Rebalance YNAB budget by proposing specific dollar moves between categories. Considers targets and goals. Use when the user wants to rebalance or redistribute their budget.
allowed-tools: Bash(uvx --from * ynab-agent *), Bash(echo *), Bash(cat *), Read, AskUserQuestion
user-invocable: true
---

**Repo path:** Set `YNAB_AGENT_DIR` env var if repo is not at `~/dev/ynab-agent`. All commands use `YNAB_AGENT_DIR="${YNAB_AGENT_DIR:-$HOME/dev/ynab-agent}"` as default.

# YNAB Rebalance

Propose and apply budget moves between categories.

## Workflow

### 0. Load philosophy and context

```bash
cat "$YNAB_AGENT_DIR/philosophy.md" 2>/dev/null
cat ~/.config/ynab-agent/context.md 2>/dev/null
```

- **philosophy.md** shapes your tone and framing. Every rebalancing move is a tradeoff — make the values behind the numbers visible. Don't just move money; surface what it means.
- **context.md** has pay schedule, category notes, and rebalancing preferences. If the user gives new hints, offer to update context.md.

### 1. Fetch current month budget

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch budget-month
```

### 2. Analyze and propose moves

**Parse due dates from category names.** Categories like "Verizon - 15th" mean due on the 15th. Group proposals by urgency: due before next payday vs. can wait.

Review the budget data and identify:

**Categories that need money (destinations):**
- Overspent categories (negative balance)
- Categories underfunded relative to their goal target (`goal_under_funded` field)
- Categories where `goal_percentage_complete` < 100

**Categories that can give money (sources), in priority order:**
1. Categories overfunded relative to target (balance > goal_target and spending is done)
2. "Inflow: Ready to Assign" balance
3. Categories with significant surplus (balance well above what's needed for remaining days)

**Materiality threshold:** Only propose moves of $5+ or categories off-target by more than 10%. Don't propose trivial moves.

**Goal type handling:**
- `MF` (Monthly Funding) — compare budgeted vs target directly
- `NEED` (Plan Spending) — compare budgeted vs target for the month
- `TB` (Target Balance) — compare current balance vs target, flag if significantly off
- `TBD` (Target Balance by Date) — check `goal_percentage_complete`, only flag if behind pace
- `DEBT` — do not touch, these are managed by YNAB's debt handling
- No goal — include in status but don't auto-rebalance

**Exclude from rebalancing:**
- Hidden categories
- Internal Master Category / Hidden Categories groups
- Credit card payment categories (group name often contains "Credit Card")
- Debt categories

### 3. Present proposal

Format as a table:

```
Budget rebalancing (N moves proposed):

  #  | From              | To               | Amount  | Reason
  1  | 👚 Clothing ($120 | 🍽 Dining Out    | $40.00  | Dining overspent by $15,
     |   remaining)      |   ($15 over)     |         | Clothing has $80 buffer
  2  | Ready to Assign   | 🍌 Groceries     | $25.00  | Groceries $25 under
     |   ($112.00)       |   ($25 under)    |         | monthly target

After moves: Ready to Assign will be $87.00
```

### 4. Ask for approval

> Review the proposals above. You can:
> - **approve** — apply all moves as shown
> - **change N amount** — adjust a specific move (e.g., "1 → $25 instead")
> - **skip N** — don't make that move
> - **cancel** — apply nothing

### 5. Apply approved moves

Just specify the category IDs and the dollar amount to move — the CLI handles the arithmetic:

```bash
echo '{"moves": [{"from_category_id": "id", "to_category_id": "id", "amount": 40.00}]}' | uvx --from "$YNAB_AGENT_DIR" ynab-agent apply rebalance
```

All amounts are in **dollars** (e.g., 40.00 = $40).

### 6. Record decisions

```bash
echo '{"decisions": [{"from_category_id": "...", "from_category_name": "...", "to_category_id": "...", "to_category_name": "...", "amount": 40.00, "reasoning": "..."}]}' | uvx --from "$YNAB_AGENT_DIR" ynab-agent history record-rebalance
```

### 7. Summary

Report what was moved and the resulting Ready to Assign balance.

### Important: context.md is for workflow preferences, not YNAB overrides

**Do NOT use context.md to override YNAB data** (e.g., "ignore this category's goal" or "treat this target as $X instead"). context.md is for workflow preferences like pay schedule, rebalancing strategy, and category notes that add context the API can't provide.

When the user disagrees with a YNAB goal or target, suggest they change it upstream in YNAB first. Ask: "Want to update that goal in YNAB, or just skip it for this session?" Only use context.md if the user explicitly wants a persistent workflow note (e.g., "Pets is usually $100" is fine — that's a preference). "Ignore Taxes" is not — that's fighting the data.

**To update a category's goal target in YNAB:**

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent category <category_id> --goal-target <dollars>
```

- `--goal-target 0` — zero out the goal
- `--goal-target 250` — set goal to $250
- `--name "New Name"` — rename the category
- `--note "Some note"` — update the category note
