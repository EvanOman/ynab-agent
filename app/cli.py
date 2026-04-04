"""CLI entry point for ynab-agent."""

from __future__ import annotations

import argparse
import json
import sys

from app import client, config
from app.models import AssignmentDecision, CategorizationDecision, RebalanceDecision


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

    if args.resource in ("uncategorized", "unapproved"):
        # unapproved: always fetch the full list (no delta) so we see everything
        # uncategorized: use delta tracking to avoid re-processing
        sk = cfg.server_knowledge_transactions if args.resource == "uncategorized" else None
        transactions, new_sk = client.get_transactions(
            plan_id=plan_id,
            type=args.resource,
            last_knowledge=sk,
        )
        if args.resource == "uncategorized":
            cfg.server_knowledge_transactions = new_sk
            config.save_config(cfg)
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


def cmd_apply(args: argparse.Namespace) -> None:
    """Apply changes to YNAB."""
    cfg = config.load_config()
    plan_id = cfg.plan_id
    data = json.load(sys.stdin)

    if args.action == "categorize":
        updates = data.get("updates", [])
        if not updates:
            _json_out({"status": "ok", "updated": 0, "message": "No updates to apply."})
            return
        count = client.update_transaction_categories(updates, plan_id=plan_id)
        _json_out({"status": "ok", "updated": count})

    elif args.action == "approve":
        ids = data.get("transaction_ids", [])
        if not ids:
            _json_out({"status": "ok", "approved": 0, "message": "No transactions to approve."})
            return
        count = client.approve_transactions(ids, plan_id=plan_id)
        _json_out({"status": "ok", "approved": count})

    elif args.action == "rebalance":
        moves = data.get("moves", [])
        if not moves:
            _json_out({"status": "ok", "moved": 0, "message": "No moves to apply."})
            return
        for move in moves:
            # Get current budgeted amounts and adjust
            # The skill should compute the new budgeted values
            client.update_month_category_budgeted(
                category_id=move["from_category_id"],
                budgeted=move["from_new_budgeted"],
                plan_id=plan_id,
            )
            client.update_month_category_budgeted(
                category_id=move["to_category_id"],
                budgeted=move["to_new_budgeted"],
                plan_id=plan_id,
            )
        _json_out({"status": "ok", "moved": len(moves)})

    elif args.action == "assign":
        assignments = data.get("assignments", [])
        month = data.get("month", "current")
        if not assignments:
            _json_out({"status": "ok", "assigned": 0, "message": "No assignments to apply."})
            return
        for a in assignments:
            client.assign_to_category(
                category_id=a["category_id"],
                add_amount=a["amount"],
                month=month,
                plan_id=plan_id,
            )
        _json_out({"status": "ok", "assigned": len(assignments)})

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
        result = lookup_payee(
            payee_id=args.payee_id,
            payee_name=args.payee_name,
            amount=int(args.amount) if args.amount else None,
        )
        _json_out(result)

    elif args.action == "lookup-batch":
        data = json.load(sys.stdin)
        transactions = data.get("transactions", [])
        results = lookup_payee_batch(transactions)
        _json_out(results)

    elif args.action == "record":
        data = json.load(sys.stdin)
        decisions_data = data.get("decisions", [])
        decisions = [CategorizationDecision(**d) for d in decisions_data]
        record_categorization_decisions(decisions)
        _json_out({"status": "ok", "recorded": len(decisions)})

    elif args.action == "record-rebalance":
        data = json.load(sys.stdin)
        decisions_data = data.get("decisions", [])
        decisions = [RebalanceDecision(**d) for d in decisions_data]
        record_rebalance_decisions(decisions)
        _json_out({"status": "ok", "recorded": len(decisions)})

    elif args.action == "record-assignment":
        data = json.load(sys.stdin)
        decisions_data = data.get("decisions", [])
        decisions = [AssignmentDecision(**d) for d in decisions_data]
        record_assignment_decisions(decisions)
        _json_out({"status": "ok", "recorded": len(decisions)})

    elif args.action == "seed":
        cfg = config.load_config()
        since = args.since or "3 months"
        # Fetch recent categorized transactions
        from datetime import date, timedelta

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
    result = client.update_category(
        category_id=args.category_id,
        goal_target=args.goal_target,
        name=args.name,
        note=args.note,
    )
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
    history_parser.add_argument("--amount", help="Transaction amount in milliunits for lookup")
    history_parser.add_argument(
        "--since", help="How far back to seed (e.g., '3 months' or ISO date)"
    )

    # category
    cat_parser = subparsers.add_parser("category", help="Update category properties")
    cat_parser.add_argument("category_id", help="Category ID to update")
    cat_parser.add_argument(
        "--goal-target", type=int, help="New goal target in milliunits (0 to zero out)"
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
