---
title: "CLI missing assign-from-Ready-to-Assign and budget-month output too verbose"
category: logic-errors
tags: [cli, ynab, workflow, rebalance, budget-month]
component: app/cli.py, app/client.py, app/models.py, app/history.py
severity: medium
date_discovered: 2026-04-03
---

## Problem

Three related issues surfaced during a daily YNAB check-in that collectively break the most common budgeting workflow: assigning money from Ready to Assign to categories.

### 1. No CLI command for assigning from Ready to Assign

The `apply rebalance` command requires both `from_category_id` and `to_category_id` with corresponding `from_new_budgeted` and `to_new_budgeted` values. This models category-to-category moves but does not cover the most frequent budget operation: assigning unbudgeted money (Ready to Assign) into a category. The agent was forced to fall back to raw Python (`uvx python3 -c` calling `update_month_category_budgeted` directly), bypassing the CLI entirely. The skill also attempted `apply budget-move` first, which does not exist, wasting a round trip.

### 2. `fetch budget-month` output is too large

The command returns ~32KB of JSON covering all 74 categories, most of which have zero activity and zero budgeted amounts. This exceeded single-read capacity and required four sequential reads to process. The noise from zero-value categories obscures the ones that matter.

### 3. History recording doesn't fit RTA assignments

The `RebalanceDecision` model requires `from_category_id` which doesn't apply for RTA assignments. During this session, "rta" was used as a fake ID to record the decisions, which is fragile.

## Solution

### Fix 1: New `apply assign` command

Add an `assign` action to `cmd_apply` in `app/cli.py`:

```python
elif args.action == "assign":
    assignments = data.get("assignments", [])
    if not assignments:
        _json_out({"status": "ok", "assigned": 0, "message": "No assignments to apply."})
        return
    month = data.get("month", "current")
    for a in assignments:
        if "amount" in a:
            # Delta mode: add to current budgeted
            client.assign_to_category(
                category_id=a["category_id"],
                add_amount=a["amount"],
                month=month, plan_id=plan_id,
            )
        else:
            # Absolute mode: set budgeted directly
            client.update_month_category_budgeted(
                category_id=a["category_id"],
                budgeted=a["budgeted"],
                month=month, plan_id=plan_id,
            )
    _json_out({"status": "ok", "assigned": len(assignments)})
```

Add a convenience wrapper in `app/client.py`:

```python
def assign_to_category(
    category_id: str,
    add_amount: int,  # milliunits to ADD (not absolute)
    month: str = "current",
    plan_id: str | None = None,
) -> int:
    """Add amount to a category's budget from Ready to Assign. Returns new budgeted value."""
    budget = get_budget_month(month=month, plan_id=plan_id)
    current = next((c for c in budget.categories if c.id == category_id), None)
    if not current:
        raise ValueError(f"Category {category_id} not found")
    new_budgeted = current.budgeted + add_amount
    update_month_category_budgeted(category_id, new_budgeted, month, plan_id)
    return new_budgeted
```

Stdin format:

```json
{
  "assignments": [
    {"category_id": "abc-123", "amount": 50000},
    {"category_id": "def-456", "amount": 125000}
  ],
  "month": "current"
}
```

Update argparse choices to include `"assign"`.

### Fix 2: `--active-only` flag for budget-month

Add `--active-only` flag to `fetch budget-month` that filters to categories with non-zero budgeted, activity, or balance. This cuts 74 categories down to ~12-15 that actually matter.

```python
fetch_parser.add_argument(
    "--active-only", action="store_true",
    help="Filter budget-month to categories with non-zero budgeted, activity, or balance"
)
```

In the budget-month branch:

```python
categories = budget.categories
if args.active_only:
    categories = [
        c for c in categories
        if c.budgeted != 0 or c.activity != 0 or c.balance != 0
    ]
```

### Fix 3: New `AssignmentDecision` model and history

Add to `app/models.py`:

```python
class AssignmentDecision(BaseModel):
    """A recorded RTA assignment decision."""
    timestamp: datetime
    category_id: str
    category_name: str
    amount_milliunits: int
    month: str = "current"
    reasoning: str = ""
```

Add `assignments.jsonl` to `app/history.py` following the same pattern as rebalances, and a `record-assignment` action to the history CLI.

## Prevention

- When adding new CLI actions, think about the most common real-world operations first (assign from RTA) not just the API-level primitives (move between categories)
- Large JSON outputs should default to filtering noise or provide filtering flags
- History models should match actual decision types, not force-fit one model for different operations

## Update skills

After implementing these fixes, update the `/ynab-rebalance` and `/ynab` skills to use `apply assign` instead of raw Python fallbacks.
