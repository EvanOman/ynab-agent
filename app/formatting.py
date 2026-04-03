"""Output formatting for the agent — all output is JSON for skill consumption."""

from __future__ import annotations

from datetime import date

from app.models import CategoryInfo, CategoryProposal, RebalanceProposal


def format_categorization_proposals(proposals: list[CategoryProposal]) -> list[dict]:
    """Format categorization proposals as JSON for the skill to render."""
    rows = []
    for i, p in enumerate(proposals, 1):
        row: dict = {
            "row": i,
            "date": p.transaction.date.isoformat(),
            "payee": p.transaction.payee_name or "Unknown",
            "amount": p.transaction.amount_dollars,
            "account": p.transaction.account_name or "",
            "transaction_id": p.transaction.id,
        }

        if p.skip_reason:
            row["proposed_category"] = None
            row["skip_reason"] = p.skip_reason
            row["confidence"] = 0
        else:
            row["proposed_category"] = p.proposed_category_name
            row["proposed_category_id"] = p.proposed_category_id
            row["confidence"] = p.confidence
            row["match_count"] = p.match_count
            row["alternatives"] = p.alternatives

        rows.append(row)
    return rows


def format_rebalance_proposals(proposals: list[RebalanceProposal]) -> list[dict]:
    """Format rebalance proposals as JSON for the skill to render."""
    rows = []
    for i, p in enumerate(proposals, 1):
        rows.append(
            {
                "row": i,
                "from_category": p.from_category_name,
                "from_category_id": p.from_category_id,
                "from_remaining": p.from_remaining / 1000.0,
                "to_category": p.to_category_name,
                "to_category_id": p.to_category_id,
                "to_shortfall": p.to_shortfall / 1000.0,
                "amount": p.amount / 1000.0,
                "reasoning": p.reasoning,
            }
        )
    return rows


def format_budget_status(
    categories: list[CategoryInfo],
    month_str: str | None = None,
) -> dict:
    """Format budget status overview as JSON for the skill to render."""
    today = date.today()
    if month_str and month_str != "current":
        # Parse month to get days info
        month_date = date.fromisoformat(month_str + "-01")
    else:
        month_date = today.replace(day=1)

    # Calculate days in month and days remaining
    if month_date.month == 12:
        next_month = month_date.replace(year=month_date.year + 1, month=1)
    else:
        next_month = month_date.replace(month=month_date.month + 1)
    days_in_month = (next_month - month_date).days
    days_remaining = max(0, (next_month - today).days)
    days_elapsed = days_in_month - days_remaining
    pct_month_elapsed = days_elapsed / days_in_month if days_in_month > 0 else 1.0

    # Build category rows
    rows = []
    flags = []
    total_budgeted = 0
    total_activity = 0
    total_balance = 0

    # Filter to visible, non-internal categories
    visible = [
        c
        for c in categories
        if not c.hidden
        and c.group_name not in ("Internal Master Category", "Hidden Categories")
        and c.name not in ("Uncategorized", "Inflow: Ready to Assign")
    ]

    for cat in visible:
        total_budgeted += cat.budgeted
        total_activity += cat.activity
        total_balance += cat.balance

        target = cat.goal_target_dollars
        pct_spent = abs(cat.activity) / cat.budgeted * 100 if cat.budgeted > 0 else 0

        # Determine pace status
        pace = "ok"
        if cat.budgeted > 0:
            pct_budget_used = abs(cat.activity) / cat.budgeted
            if pct_budget_used > 1.0:
                pace = "overspent"
            elif pct_budget_used > 0.85 and pct_month_elapsed < 0.67:
                pace = "tight"
            elif cat.activity == 0 and cat.budgeted > 0 and pct_month_elapsed > 0.3:
                pace = "inactive"

        row = {
            "name": cat.name,
            "group": cat.group_name,
            "target": target,
            "budgeted": cat.budgeted_dollars,
            "spent": cat.activity_dollars,
            "remaining": cat.balance_dollars,
            "goal_type": cat.goal_type.value if cat.goal_type else None,
            "goal_pct_complete": cat.goal_percentage_complete,
            "pace": pace,
        }
        rows.append(row)

        # Generate flags
        if pace == "overspent":
            flags.append(f"🔴 {cat.name} is overspent by ${abs(cat.balance_dollars):.2f}")
        elif pace == "tight":
            flags.append(
                f"⚠️ {cat.name} is {pct_spent:.0f}% spent with {days_remaining} days remaining"
            )
        elif pace == "inactive":
            flags.append(f"💤 {cat.name} has $0 activity (budgeted ${cat.budgeted_dollars:.2f})")

    # Find Ready to Assign
    rta = next(
        (c for c in categories if c.name == "Inflow: Ready to Assign"),
        None,
    )

    return {
        "month": month_date.isoformat()[:7],
        "days_in_month": days_in_month,
        "days_remaining": days_remaining,
        "pct_month_elapsed": round(pct_month_elapsed * 100, 1),
        "categories": rows,
        "flags": flags,
        "totals": {
            "budgeted": total_budgeted / 1000.0,
            "activity": total_activity / 1000.0,
            "balance": total_balance / 1000.0,
        },
        "ready_to_assign": rta.balance_dollars if rta else 0,
    }
