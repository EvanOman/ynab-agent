---
name: ynab-categorize
description: Categorize uncategorized YNAB transactions. Proposes categories based on decision history and asks for approval before applying. Use when the user wants to categorize transactions.
allowed-tools: Bash(uvx --from * ynab-agent *), Bash(echo *), Bash(cat *), Read, AskUserQuestion
user-invocable: true
---

**Repo path:** Set `YNAB_AGENT_DIR` env var if repo is not at `~/dev/ynab-agent`. All commands use `YNAB_AGENT_DIR="${YNAB_AGENT_DIR:-$HOME/dev/ynab-agent}"` as default.

# YNAB Categorize

Categorize uncategorized transactions with batch approval.

## Workflow

### 0. Load philosophy and context

```bash
cat "$YNAB_AGENT_DIR/philosophy.md" 2>/dev/null
cat ~/.config/ynab-agent/context.md 2>/dev/null
```

- **philosophy.md** shapes your tone. Categorization isn't just filing — it's helping the user see where their money actually went, the first step to deciding where it goes next.
- **context.md** has category notes and preferences. If the user gives new hints, offer to update context.md.

### 1. Fetch uncategorized transactions

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch uncategorized
```

If count is 0, tell the user "No uncategorized transactions — you're all caught up!" and stop.

### 2. Fetch categories (for reference)

```bash
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch categories
```

### 3. Look up decision history for each transaction

Pipe the uncategorized transactions into batch lookup:

```bash
echo '<json with transactions array>' | uvx --from "$YNAB_AGENT_DIR" ynab-agent history lookup-batch
```

The input JSON should be: `{"transactions": [<array of transaction objects from step 1>]}`

### 4. Build proposal table

For each transaction, combine the history lookup with your own judgment to propose a category. Format as a numbered table:

```
Uncategorized transactions (N found):

  #  | Date       | Payee              | Amount   | Proposed Category | Confidence
  1  | 2026-04-01 | TRADER JOE'S #142  | -$45.23  | 🍌 Groceries      | ●●● (20x match)
  2  | 2026-04-01 | SHELL OIL 54892    | -$52.10  | 🚗 Transportation  | ●●○ (3x match)
  ...
```

**Confidence indicators:**
- `●●●` — Strong match (10+ historical matches, >80% same category)
- `●●○` — Moderate match (3+ matches)
- `●○○` — Weak match (1-2 matches or fuzzy name only)
- `○○○` — New payee (no history, LLM best guess)
- `⚠ Split` — Split transaction, cannot be categorized via API

**For split transactions:** Show them in the table as non-actionable:
```
  5  | 2026-03-31 | COSTCO #482        | -$87.30  | —                 | ⚠ Split (edit in YNAB)
```

**For payees with multiple historical categories:** Note the alternatives:
```
  3  | 2026-03-31 | AMAZON             | -$23.99  | Household Goods   | ●○○ (mixed: 8x Household, 5x Groceries)
```

**IMPORTANT:** Use the actual YNAB category names from step 2 (they may have emoji prefixes like "🍌 Groceries"). Match exactly.

### 5. Ask for approval

Use AskUserQuestion or just ask directly:

> Review the proposals above. You can:
> - **approve** — apply all proposals as shown
> - **change N to Category** — override a specific row (e.g., "3 → 🍌 Groceries")
> - **skip N** — leave that transaction uncategorized
> - **cancel** — apply nothing

### 6. Apply approved categorizations

Build the updates JSON and pipe to apply:

```bash
echo '{"updates": [{"id": "txn-id-1", "category_id": "cat-id-1"}, ...]}' | uvx --from "$YNAB_AGENT_DIR" ynab-agent apply categorize
```

**Skip:** split transactions and any the user explicitly skipped.

### 7. Record decisions to history

Record what was decided (including corrections) so future proposals improve:

```bash
echo '{"decisions": [...]}' | uvx --from "$YNAB_AGENT_DIR" ynab-agent history record
```

Each decision object:
```json
{
  "timestamp": "2026-04-02T14:30:00Z",
  "transaction_id": "abc123",
  "payee_id": "payee-uuid",
  "payee_name": "TRADER JOES",
  "amount_milliunits": -45230,
  "proposed_category_id": "cat-id",
  "proposed_category_name": "Groceries",
  "final_category_id": "cat-id",
  "final_category_name": "Groceries",
  "source": "agent",
  "was_corrected": false
}
```

Set `was_corrected: true` and update `final_*` fields when the user overrode your proposal. Corrections are weighted 3x in future lookups.

### 8. Summary

Tell the user how many were categorized, how many skipped, and any that need manual attention in YNAB (splits).
