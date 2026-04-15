"""Thin wrapper around the official YNAB Python SDK."""

from __future__ import annotations

import os
from datetime import date as date_cls
from uuid import UUID

import ynab
from dotenv import load_dotenv
from pydantic import BaseModel

from ynab_agent.models import (
    AccountInfo,
    CategorizeUpdate,
    CategoryInfo,
    GoalType,
    PayeeInfo,
    PlanInfo,
    TransactionInfo,
)
from ynab_agent.paths import ENV_FILE, ensure_dirs

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


# --- Accounts ---


def get_accounts(plan_id: str | None = None) -> list[AccountInfo]:
    """Fetch all open budget accounts."""
    with _get_client() as client:
        api = ynab.AccountsApi(client)
        resp = api.get_accounts(_plan_id(plan_id))
        accounts = []
        for a in resp.data.accounts:
            if a.deleted or a.closed:
                continue
            accounts.append(
                AccountInfo(
                    id=str(a.id),
                    name=a.name,
                    type=a.type,
                    on_budget=a.on_budget,
                    closed=a.closed,
                    balance=a.balance,
                    cleared_balance=a.cleared_balance,
                    uncleared_balance=a.uncleared_balance,
                    note=a.note,
                )
            )
        return accounts


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
                    cleared=t.cleared.value if t.cleared else "uncleared",
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


class BudgetMonth(BaseModel):
    """Budget month summary with categories and top-level totals."""

    categories: list[CategoryInfo]
    income: int = 0  # milliunits — total income received this month
    to_be_budgeted: int = 0  # milliunits — actual Ready to Assign (unassigned dollars)
    age_of_money: int | None = None  # days


def get_budget_month(
    month: str = "current",
    plan_id: str | None = None,
) -> BudgetMonth:
    """Fetch budget month details with category balances and month-level totals."""
    with _get_client() as client:
        api = ynab.MonthsApi(client)
        month_date = _parse_month(month)
        resp = api.get_plan_month(_plan_id(plan_id), month_date)
        m = resp.data.month
        categories = []
        for cat in m.categories:
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
        return BudgetMonth(
            categories=categories,
            income=m.income or 0,
            to_be_budgeted=m.to_be_budgeted or 0,
            age_of_money=m.age_of_money,
        )


# --- Sync / Import ---


def trigger_import(plan_id: str | None = None) -> list[str]:
    """Trigger YNAB to import transactions from linked accounts.

    Equivalent to clicking "Import" in the YNAB app. Returns the IDs of
    transactions that were newly imported (may be empty).
    """
    with _get_client() as client:
        api = ynab.TransactionsApi(client)
        resp = api.import_transactions(_plan_id(plan_id))
        return [str(tid) for tid in (resp.data.transaction_ids or [])]


# --- Write Operations ---


def create_transaction(
    account_id: str,
    amount_milliunits: int,
    date_str: str | None = None,
    payee_name: str | None = None,
    category_id: str | None = None,
    memo: str | None = None,
    cleared: str = "uncleared",
    approved: bool = True,
    subtransactions: list[dict] | None = None,
    plan_id: str | None = None,
) -> dict:
    """Create a single transaction, optionally as a split.

    For a split, pass `category_id=None` and a list of subtransactions
    (each with `amount_milliunits` and `category_id`). Subtransaction amounts
    must sum to `amount_milliunits`.

    Returns the created transaction's id and a summary dict.
    """
    txn_date = date_cls.fromisoformat(date_str) if date_str else date_cls.today()
    sub_objs = None
    if subtransactions:
        sub_objs = [
            ynab.SaveSubTransaction(
                amount=s["amount_milliunits"],
                category_id=UUID(s["category_id"]) if s.get("category_id") else None,
                payee_name=s.get("payee_name"),
                memo=s.get("memo"),
            )
            for s in subtransactions
        ]
    new_txn = ynab.NewTransaction(
        account_id=UUID(account_id),
        var_date=txn_date,
        amount=amount_milliunits,
        payee_name=payee_name,
        category_id=UUID(category_id) if category_id else None,
        memo=memo,
        cleared=ynab.TransactionClearedStatus(cleared),
        approved=approved,
        subtransactions=sub_objs,
    )
    wrapper = ynab.PostTransactionsWrapper(transaction=new_txn)
    with _get_client() as client:
        api = ynab.TransactionsApi(client)
        resp = api.create_transaction(_plan_id(plan_id), wrapper)
        t = resp.data.transaction
        return {
            "id": str(t.id) if t else None,
            "amount_milliunits": t.amount if t else None,
            "subtransaction_count": len(t.subtransactions) if (t and t.subtransactions) else 0,
        }


def get_transaction(
    transaction_id: str,
    plan_id: str | None = None,
) -> dict:
    """Fetch a single transaction with its subtransactions. Returns a raw dict."""
    with _get_client() as client:
        api = ynab.TransactionsApi(client)
        resp = api.get_transaction_by_id(_plan_id(plan_id), transaction_id)
        t = resp.data.transaction
        return {
            "id": str(t.id),
            "amount": t.amount,
            "category_id": str(t.category_id) if t.category_id else None,
            "subtransactions": [
                {
                    "category_id": str(s.category_id) if s.category_id else None,
                    "amount": s.amount,
                }
                for s in (t.subtransactions or [])
                if not s.deleted
            ],
        }


def delete_transaction(
    transaction_id: str,
    plan_id: str | None = None,
) -> dict:
    """Delete a transaction by ID. Returns the deleted transaction summary."""
    with _get_client() as client:
        api = ynab.TransactionsApi(client)
        resp = api.delete_transaction(_plan_id(plan_id), transaction_id)
        t = resp.data.transaction
        return {"id": str(t.id), "amount": t.amount, "deleted": t.deleted}


def nudge_category(
    category_id: str,
    month: str = "current",
    plan_id: str | None = None,
) -> None:
    """Force YNAB to recompute a category's month aggregate by toggling budget by 1 milliunit.

    Workaround for a YNAB API quirk where deleted or modified split transactions
    leave ghost activity in the month-aggregate view until the category's budget
    is edited.
    """
    assign_to_category(category_id=category_id, add_amount=1, month=month, plan_id=plan_id)
    assign_to_category(category_id=category_id, add_amount=-1, month=month, plan_id=plan_id)


def _update_transactions(
    txns: list[ynab.SaveTransactionWithIdOrImportId],
    plan_id: str | None = None,
) -> int:
    """Send a batch transaction update. Returns count of updated transactions."""
    with _get_client() as client:
        api = ynab.TransactionsApi(client)
        wrapper = ynab.PatchTransactionsWrapper(transactions=txns)
        # The SDK's update_transactions returns None despite a 200 response,
        # so we use the _with_http_info variant to at least confirm success.
        resp = api.update_transactions_with_http_info(_plan_id(plan_id), wrapper)
        if resp.status_code != 200:
            msg = f"YNAB API returned status {resp.status_code}"
            raise RuntimeError(msg)
        return len(txns)


def update_transaction_categories(
    updates: list[CategorizeUpdate],
    plan_id: str | None = None,
) -> int:
    """Batch update transaction categories and approve them."""
    txns = [
        ynab.SaveTransactionWithIdOrImportId(
            id=u.transaction_id,
            category_id=UUID(u.category_id),
            approved=True,
        )
        for u in updates
    ]
    return _update_transactions(txns, plan_id)


def approve_transactions(
    transaction_ids: list[str],
    plan_id: str | None = None,
) -> int:
    """Approve transactions by ID. Returns count of approved transactions."""
    txns = [ynab.SaveTransactionWithIdOrImportId(id=tid, approved=True) for tid in transaction_ids]
    return _update_transactions(txns, plan_id)


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


def assign_to_category(
    category_id: str,
    add_amount: int,
    month: str = "current",
    plan_id: str | None = None,
) -> int:
    """Add amount (milliunits) to a category's budget from Ready to Assign. Returns new budgeted."""
    budget = get_budget_month(month=month, plan_id=plan_id)
    current = next((c for c in budget.categories if c.id == category_id), None)
    if not current:
        raise ValueError(f"Category {category_id} not found")
    new_budgeted = current.budgeted + add_amount
    update_month_category_budgeted(category_id, new_budgeted, month, plan_id)
    return new_budgeted
