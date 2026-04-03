"""Thin wrapper around the official YNAB Python SDK."""

from __future__ import annotations

import os
from datetime import date as date_cls

import ynab
from dotenv import load_dotenv

from app.models import CategoryInfo, GoalType, PayeeInfo, PlanInfo, TransactionInfo
from app.paths import ENV_FILE, ensure_dirs

# Load .env from data directory
ensure_dirs()
load_dotenv(ENV_FILE)


def _get_client() -> ynab.ApiClient:
    token = os.environ.get("YNAB_PAT")
    if not token:
        msg = "YNAB_PAT environment variable not set. Add it to .env or export it."
        raise RuntimeError(msg)
    config = ynab.Configuration(access_token=token)
    return ynab.ApiClient(config)


def _plan_id(plan_id: str | None = None) -> str:
    return plan_id or "last-used"


def _parse_month(month: str) -> date_cls:
    """Parse a month string to a date. Supports 'current' or ISO date strings."""
    if month == "current":
        # YNAB SDK accepts the string "current" cast to date via validate_call,
        # but ty doesn't know that. We pass the first of the current month.
        today = date_cls.today()
        return today.replace(day=1)
    return date_cls.fromisoformat(month if len(month) > 7 else month + "-01")


# --- Plans (Budgets) ---


def get_plans() -> list[PlanInfo]:
    """List all YNAB plans/budgets."""
    with _get_client() as client:
        api = ynab.PlansApi(client)
        resp = api.get_plans()
        return [PlanInfo(id=str(p.id), name=p.name) for p in resp.data.plans]


# --- Transactions ---


def get_transactions(
    plan_id: str | None = None,
    type: str | None = None,
    since_date: str | None = None,
    last_knowledge: int | None = None,
) -> tuple[list[TransactionInfo], int]:
    """Fetch transactions. Returns (transactions, server_knowledge)."""
    with _get_client() as client:
        api = ynab.TransactionsApi(client)
        kwargs: dict = {}
        if type:
            kwargs["type"] = type
        if since_date:
            kwargs["since_date"] = date_cls.fromisoformat(since_date)
        if last_knowledge is not None:
            kwargs["last_knowledge_of_server"] = last_knowledge

        resp = api.get_transactions(_plan_id(plan_id), **kwargs)
        transactions = []
        for t in resp.data.transactions:
            is_split = bool(t.subtransactions and len(t.subtransactions) > 0)
            transactions.append(
                TransactionInfo(
                    id=str(t.id),
                    date=t.var_date,
                    amount=t.amount,
                    payee_id=str(t.payee_id) if t.payee_id else None,
                    payee_name=t.payee_name,
                    category_id=str(t.category_id) if t.category_id else None,
                    category_name=t.category_name,
                    account_name=t.account_name,
                    memo=t.memo,
                    approved=t.approved,
                    is_split=is_split,
                )
            )
        return transactions, resp.data.server_knowledge


# --- Categories ---


def get_categories(
    plan_id: str | None = None,
    last_knowledge: int | None = None,
) -> tuple[list[CategoryInfo], int]:
    """Fetch all categories. Returns (categories, server_knowledge)."""
    with _get_client() as client:
        api = ynab.CategoriesApi(client)
        kwargs: dict = {}
        if last_knowledge is not None:
            kwargs["last_knowledge_of_server"] = last_knowledge

        resp = api.get_categories(_plan_id(plan_id), **kwargs)
        categories = []
        for group in resp.data.category_groups:
            for cat in group.categories:
                if cat.deleted:
                    continue
                goal_type = None
                if cat.goal_type:
                    try:
                        goal_type = GoalType(cat.goal_type)
                    except ValueError:
                        pass
                categories.append(
                    CategoryInfo(
                        id=str(cat.id),
                        name=cat.name,
                        group_name=group.name,
                        group_id=str(group.id),
                        hidden=cat.hidden,
                        budgeted=cat.budgeted,
                        activity=cat.activity,
                        balance=cat.balance,
                        goal_type=goal_type,
                        goal_target=cat.goal_target,
                        goal_target_month=str(cat.goal_target_month)
                        if cat.goal_target_month
                        else None,
                        goal_percentage_complete=cat.goal_percentage_complete,
                        goal_under_funded=cat.goal_under_funded,
                    )
                )
        return categories, resp.data.server_knowledge


# --- Payees ---


def get_payees(
    plan_id: str | None = None,
    last_knowledge: int | None = None,
) -> tuple[list[PayeeInfo], int]:
    """Fetch all payees. Returns (payees, server_knowledge)."""
    with _get_client() as client:
        api = ynab.PayeesApi(client)
        kwargs: dict = {}
        if last_knowledge is not None:
            kwargs["last_knowledge_of_server"] = last_knowledge

        resp = api.get_payees(_plan_id(plan_id), **kwargs)
        payees = []
        for p in resp.data.payees:
            if p.deleted:
                continue
            payees.append(
                PayeeInfo(
                    id=str(p.id),
                    name=p.name,
                    transfer_account_id=str(p.transfer_account_id)
                    if p.transfer_account_id
                    else None,
                )
            )
        return payees, resp.data.server_knowledge


# --- Budget Month ---


def get_budget_month(
    month: str = "current",
    plan_id: str | None = None,
) -> list[CategoryInfo]:
    """Fetch budget month details with category balances."""
    with _get_client() as client:
        api = ynab.MonthsApi(client)
        month_date = _parse_month(month)
        resp = api.get_plan_month(_plan_id(plan_id), month_date)
        categories = []
        for cat in resp.data.month.categories:
            if cat.deleted:
                continue
            goal_type = None
            if cat.goal_type:
                try:
                    goal_type = GoalType(cat.goal_type)
                except ValueError:
                    pass
            categories.append(
                CategoryInfo(
                    id=str(cat.id),
                    name=cat.name,
                    group_id=str(cat.category_group_id),
                    hidden=cat.hidden,
                    budgeted=cat.budgeted,
                    activity=cat.activity,
                    balance=cat.balance,
                    goal_type=goal_type,
                    goal_target=cat.goal_target,
                    goal_target_month=str(cat.goal_target_month) if cat.goal_target_month else None,
                    goal_percentage_complete=cat.goal_percentage_complete,
                    goal_under_funded=cat.goal_under_funded,
                )
            )
        return categories


# --- Write Operations ---


def update_transaction_categories(
    updates: list[dict],
    plan_id: str | None = None,
) -> int:
    """Batch update transaction categories. Returns count of updated transactions.

    updates: list of {"id": str, "category_id": str}
    """
    with _get_client() as client:
        api = ynab.TransactionsApi(client)
        txns = []
        for u in updates:
            txns.append(
                ynab.SaveTransactionWithIdOrImportId(
                    id=u["id"],
                    category_id=u["category_id"],
                )
            )
        wrapper = ynab.PatchTransactionsWrapper(transactions=txns)
        resp = api.update_transactions(_plan_id(plan_id), wrapper)
        return len(resp.data.transactions or [])


def update_category(
    category_id: str,
    goal_target: int | None = None,
    name: str | None = None,
    note: str | None = None,
    plan_id: str | None = None,
) -> dict:
    """Update a category's properties (goal target, name, note).

    goal_target: in milliunits. Set to 0 to zero out the goal target.
    Returns the updated category data.
    """
    with _get_client() as client:
        api = ynab.CategoriesApi(client)
        kwargs: dict = {}
        if goal_target is not None:
            kwargs["goal_target"] = goal_target
        if name is not None:
            kwargs["name"] = name
        if note is not None:
            kwargs["note"] = note
        category = ynab.ExistingCategory(**kwargs)
        wrapper = ynab.PatchCategoryWrapper(category=category)
        resp = api.update_category(_plan_id(plan_id), category_id, wrapper)
        cat = resp.data.category
        return {
            "id": str(cat.id),
            "name": cat.name,
            "goal_type": cat.goal_type,
            "goal_target": cat.goal_target,
        }


def update_month_category_budgeted(
    category_id: str,
    budgeted: int,
    month: str = "current",
    plan_id: str | None = None,
) -> None:
    """Update a category's budgeted amount for a given month."""
    with _get_client() as client:
        api = ynab.CategoriesApi(client)
        month_date = _parse_month(month)
        wrapper = ynab.PatchMonthCategoryWrapper(category=ynab.SaveMonthCategory(budgeted=budgeted))
        api.update_month_category(_plan_id(plan_id), month_date, category_id, wrapper)
