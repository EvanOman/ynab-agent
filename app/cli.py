"""CLI entry point for ynab-agent."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from pydantic import BaseModel, ValidationError

from app import client, config
from app.models import (
    ApproveInput,
    AssignInput,
    AssignmentRecordInput,
    CategorizationRecordInput,
    CategorizeInput,
    RebalanceInput,
    RebalanceRecordInput,
    dollars_to_milliunits,
)


def _json_out(data: object) -> None:
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


# --- Commands ---


def cmd_setup(args: argparse.Namespace) -> None:
    """Validate PAT, list plans, save config."""
    plans = client.get_plans()
    if not plans:
        print(json.dumps({"error": "No plans found. Check your YNAB_PAT."}))
        sys.exit(1)

    _json_out(
        {
            "plans": [p.model_dump() for p in plans],
            "message": "Select a plan and run: ynab-agent setup --plan-id <id>",
        }
    )

    if args.plan_id:
        selected = next((p for p in plans if p.id == args.plan_id), None)
        if not selected:
            # Try "last-used" shortcut
            if args.plan_id == "last-used":
                cfg = config.load_config()
                cfg.plan_id = "last-used"
                cfg.plan_name = "last-used"
                config.save_config(cfg)
                _json_out({"status": "ok", "plan_id": "last-used"})
                return
            print(json.dumps({"error": f"Plan {args.plan_id} not found"}))
            sys.exit(1)
        cfg = config.load_config()
        cfg.plan_id = selected.id
        cfg.plan_name = selected.name
        config.save_config(cfg)
        _json_out({"status": "ok", "plan_id": selected.id, "plan_name": selected.name})


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch data from YNAB API."""
    cfg = config.load_config()
    plan_id = cfg.plan_id

    if args.resource == "pending":
        since = args.since or (date.today() - timedelta(days=14)).isoformat()
        transactions, _ = client.get_transactions(plan_id=plan_id, since_date=since)
        pending = [t for t in transactions if t.cleared == "uncleared"]
        _json_out(
            {
                "transactions": [t.to_output_dict() for t in pending],
                "count": len(pending),
            }
        )

    elif args.resource in ("uncategorized", "unapproved"):
        # Always fetch the full list (no delta) for both — these are "show me
        # everything currently matching this filter" queries, not "what's new".
        # Using server_knowledge here would hide items that existed before the
        # last sync point.
        transactions, new_sk = client.get_transactions(
            plan_id=plan_id,
            type=args.resource,
        )
        if args.resource == "uncategorized":
            # Filter out transfers between budget accounts — they legitimately
            # have no category in YNAB but aren't "uncategorized" in the
            # meaningful sense.
            transactions = [
                t for t in transactions if not (t.payee_name or "").startswith("Transfer :")
            ]
        _json_out(
            {
                "transactions": [t.to_output_dict() for t in transactions],
                "count": len(transactions),
                "server_knowledge": new_sk,
            }
        )

    elif args.resource == "transactions":
        sk = cfg.server_knowledge_transactions
        kwargs: dict = {"plan_id": plan_id, "last_knowledge": sk}
        if args.since:
            kwargs["since_date"] = args.since
        transactions, new_sk = client.get_transactions(**kwargs)
        cfg.server_knowledge_transactions = new_sk
        config.save_config(cfg)
        _json_out(
            {
                "transactions": [t.to_output_dict() for t in transactions],
                "count": len(transactions),
                "server_knowledge": new_sk,
            }
        )

    elif args.resource == "categories":
        sk = cfg.server_knowledge_categories
        categories, new_sk = client.get_categories(plan_id=plan_id, last_knowledge=sk)
        cfg.server_knowledge_categories = new_sk
        config.save_config(cfg)
        _json_out(
            {
                "categories": [c.to_output_dict() for c in categories],
                "count": len(categories),
                "server_knowledge": new_sk,
            }
        )

    elif args.resource == "payees":
        sk = cfg.server_knowledge_payees
        payees, new_sk = client.get_payees(plan_id=plan_id, last_knowledge=sk)
        cfg.server_knowledge_payees = new_sk
        config.save_config(cfg)
        _json_out(
            {
                "payees": [p.model_dump() for p in payees],
                "count": len(payees),
                "server_knowledge": new_sk,
            }
        )

    elif args.resource == "accounts":
        accounts = client.get_accounts(plan_id=plan_id)
        _json_out(
            {
                "accounts": [a.to_output_dict() for a in accounts],
                "count": len(accounts),
            }
        )

    elif args.resource == "budget-month":
        month = args.month or "current"
        budget = client.get_budget_month(month=month, plan_id=plan_id)
        categories = [c.to_output_dict() for c in budget.categories]
        if args.active_only:
            categories = [
                c
                for c in categories
                if c["budgeted"] != 0 or c["activity"] != 0 or c["balance"] != 0
            ]
        _json_out(
            {
                "categories": categories,
                "count": len(categories),
                "month": month,
                "income": budget.income / 1000.0,
                "to_be_budgeted": budget.to_be_budgeted / 1000.0,
                "age_of_money": budget.age_of_money,
            }
        )

    else:
        print(json.dumps({"error": f"Unknown resource: {args.resource}"}))
        sys.exit(1)


def _parse_stdin[T: BaseModel](model_cls: type[T]) -> T:
    """Parse stdin JSON into a Pydantic model, exit with clear error on failure."""
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON on stdin: {e}"}))
        sys.exit(1)
    try:
        return model_cls.model_validate(data)
    except ValidationError as e:
        print(json.dumps({"error": f"Invalid input: {e}"}))
        sys.exit(1)


def cmd_apply(args: argparse.Namespace) -> None:
    """Apply changes to YNAB."""
    cfg = config.load_config()
    plan_id = cfg.plan_id

    if args.action == "categorize":
        inp = _parse_stdin(CategorizeInput)
        if not inp.updates:
            _json_out({"status": "ok", "updated": 0, "message": "No updates to apply."})
            return
        count = client.update_transaction_categories(inp.updates, plan_id=plan_id)
        _json_out({"status": "ok", "updated": count})

    elif args.action == "approve":
        inp = _parse_stdin(ApproveInput)
        if not inp.transaction_ids:
            _json_out({"status": "ok", "approved": 0, "message": "No transactions to approve."})
            return
        count = client.approve_transactions(inp.transaction_ids, plan_id=plan_id)
        _json_out({"status": "ok", "approved": count})

    elif args.action == "rebalance":
        inp = _parse_stdin(RebalanceInput)
        if not inp.moves:
            _json_out({"status": "ok", "moved": 0, "message": "No moves to apply."})
            return
        # Fetch current budget to compute new absolute values
        budget = client.get_budget_month(plan_id=plan_id)
        cat_budgeted = {c.id: c.budgeted for c in budget.categories}
        for move in inp.moves:
            amount_mu = dollars_to_milliunits(move.amount)
            from_current = cat_budgeted.get(move.from_category_id, 0)
            to_current = cat_budgeted.get(move.to_category_id, 0)
            client.update_month_category_budgeted(
                category_id=move.from_category_id,
                budgeted=from_current - amount_mu,
                plan_id=plan_id,
            )
            client.update_month_category_budgeted(
                category_id=move.to_category_id,
                budgeted=to_current + amount_mu,
                plan_id=plan_id,
            )
            # Update local state for chained moves
            cat_budgeted[move.from_category_id] = from_current - amount_mu
            cat_budgeted[move.to_category_id] = to_current + amount_mu
        _json_out({"status": "ok", "moved": len(inp.moves)})

    elif args.action == "assign":
        inp = _parse_stdin(AssignInput)
        if not inp.assignments:
            _json_out({"status": "ok", "assigned": 0, "message": "No assignments to apply."})
            return
        for a in inp.assignments:
            client.assign_to_category(
                category_id=a.category_id,
                add_amount=dollars_to_milliunits(a.amount),
                month=inp.month,
                plan_id=plan_id,
            )
        _json_out({"status": "ok", "assigned": len(inp.assignments)})

    else:
        print(json.dumps({"error": f"Unknown action: {args.action}"}))
        sys.exit(1)


def cmd_history(args: argparse.Namespace) -> None:
    """Decision history operations."""
    from app.history import (
        lookup_payee,
        lookup_payee_batch,
        record_assignment_decisions,
        record_categorization_decisions,
        record_rebalance_decisions,
        seed_from_transactions,
    )

    if args.action == "lookup":
        amount_mu = dollars_to_milliunits(args.amount) if args.amount is not None else None
        result = lookup_payee(
            payee_id=args.payee_id,
            payee_name=args.payee_name,
            amount=amount_mu,
        )
        _json_out(result)

    elif args.action == "lookup-batch":
        data = json.load(sys.stdin)
        transactions = data.get("transactions", [])
        results = lookup_payee_batch(transactions)
        _json_out(results)

    elif args.action == "record":
        inp = _parse_stdin(CategorizationRecordInput)
        record_categorization_decisions(inp.decisions)
        _json_out({"status": "ok", "recorded": len(inp.decisions)})

    elif args.action == "record-rebalance":
        inp = _parse_stdin(RebalanceRecordInput)
        record_rebalance_decisions(inp.decisions)
        _json_out({"status": "ok", "recorded": len(inp.decisions)})

    elif args.action == "record-assignment":
        inp = _parse_stdin(AssignmentRecordInput)
        record_assignment_decisions(inp.decisions)
        _json_out({"status": "ok", "recorded": len(inp.decisions)})

    elif args.action == "seed":
        cfg = config.load_config()
        since = args.since or "3 months"
        # Fetch recent categorized transactions
        if since.endswith("months"):
            months = int(since.split()[0])
            since_date = (date.today() - timedelta(days=months * 30)).isoformat()
        else:
            since_date = since

        transactions, _ = client.get_transactions(
            plan_id=cfg.plan_id,
            since_date=since_date,
        )
        # Filter to categorized, non-transfer transactions
        categorized = [
            t
            for t in transactions
            if t.category_id
            and t.payee_id
            and (not t.payee_name.startswith("Transfer :") if t.payee_name else True)
        ]
        count = seed_from_transactions(categorized)
        _json_out({"status": "ok", "seeded": count})

    else:
        print(json.dumps({"error": f"Unknown history action: {args.action}"}))
        sys.exit(1)


def cmd_category(args: argparse.Namespace) -> None:
    """Update category properties."""
    goal_target_mu = (
        dollars_to_milliunits(args.goal_target) if args.goal_target is not None else None
    )
    result = client.update_category(
        category_id=args.category_id,
        goal_target=goal_target_mu,
        name=args.name,
        note=args.note,
    )
    # Convert milliunits to dollars in output
    if result.get("goal_target") is not None:
        result["goal_target"] = result["goal_target"] / 1000.0
    _json_out({"status": "ok", "category": result})


def main() -> None:
    parser = argparse.ArgumentParser(prog="ynab-agent", description="YNAB budget agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup
    setup_parser = subparsers.add_parser("setup", help="Configure YNAB connection")
    setup_parser.add_argument("--plan-id", help="Plan/budget ID to use")

    # fetch
    fetch_parser = subparsers.add_parser("fetch", help="Fetch data from YNAB")
    fetch_parser.add_argument(
        "resource",
        choices=[
            "uncategorized",
            "unapproved",
            "pending",
            "transactions",
            "categories",
            "payees",
            "accounts",
            "budget-month",
        ],
        help="Resource to fetch",
    )
    fetch_parser.add_argument("--since", help="Since date (ISO format, for transactions)")
    fetch_parser.add_argument("--month", help="Month (ISO format or 'current', for budget-month)")
    fetch_parser.add_argument(
        "--active-only",
        action="store_true",
        help="Filter to categories with non-zero budgeted, activity, or balance",
    )

    # apply
    apply_parser = subparsers.add_parser("apply", help="Apply changes to YNAB (reads JSON stdin)")
    apply_parser.add_argument(
        "action", choices=["categorize", "approve", "rebalance", "assign"], help="Action to apply"
    )

    # history
    history_parser = subparsers.add_parser("history", help="Decision history operations")
    history_parser.add_argument(
        "action",
        choices=[
            "lookup",
            "lookup-batch",
            "record",
            "record-rebalance",
            "record-assignment",
            "seed",
        ],
        help="History action",
    )
    history_parser.add_argument("--payee-id", help="Payee ID for lookup")
    history_parser.add_argument("--payee-name", help="Payee name for lookup")
    history_parser.add_argument(
        "--amount", type=float, help="Transaction amount in dollars for lookup"
    )
    history_parser.add_argument(
        "--since", help="How far back to seed (e.g., '3 months' or ISO date)"
    )

    # category
    cat_parser = subparsers.add_parser("category", help="Update category properties")
    cat_parser.add_argument("category_id", help="Category ID to update")
    cat_parser.add_argument(
        "--goal-target", type=float, help="New goal target in dollars (0 to zero out)"
    )
    cat_parser.add_argument("--name", help="New category name")
    cat_parser.add_argument("--note", help="New category note")

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "fetch":
        cmd_fetch(args)
    elif args.command == "apply":
        cmd_apply(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "category":
        cmd_category(args)


if __name__ == "__main__":
    main()
