"""Pydantic models for YNAB agent data."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class GoalType(StrEnum):
    TARGET_BALANCE = "TB"
    TARGET_BALANCE_BY_DATE = "TBD"
    MONTHLY_FUNDING = "MF"
    PLAN_SPENDING = "NEED"
    DEBT = "DEBT"


class TransactionInfo(BaseModel):
    """A transaction from YNAB, simplified for agent use."""

    id: str
    date: date
    amount: int  # milliunits
    payee_id: str | None = None
    payee_name: str | None = None
    category_id: str | None = None
    category_name: str | None = None
    account_name: str | None = None
    memo: str | None = None
    approved: bool = False
    is_split: bool = False

    @property
    def amount_dollars(self) -> float:
        return self.amount / 1000.0

    def to_output_dict(self) -> dict:
        """Serialize with dollar amounts instead of milliunits."""
        d = self.model_dump()
        d["amount"] = self.amount_dollars
        return d


class CategoryInfo(BaseModel):
    """A budget category from YNAB, simplified for agent use."""

    id: str
    name: str
    group_name: str | None = None
    group_id: str | None = None
    hidden: bool = False
    budgeted: int = 0  # milliunits
    activity: int = 0  # milliunits (negative = spending)
    balance: int = 0  # milliunits
    goal_type: GoalType | None = None
    goal_target: int | None = None  # milliunits
    goal_target_month: str | None = None
    goal_percentage_complete: int | None = None
    goal_under_funded: int | None = None

    @property
    def budgeted_dollars(self) -> float:
        return self.budgeted / 1000.0

    @property
    def activity_dollars(self) -> float:
        return self.activity / 1000.0

    @property
    def balance_dollars(self) -> float:
        return self.balance / 1000.0

    @property
    def goal_target_dollars(self) -> float | None:
        return self.goal_target / 1000.0 if self.goal_target is not None else None

    def to_output_dict(self) -> dict:
        """Serialize with dollar amounts instead of milliunits."""
        d = self.model_dump()
        d["budgeted"] = self.budgeted_dollars
        d["activity"] = self.activity_dollars
        d["balance"] = self.balance_dollars
        d["goal_target"] = self.goal_target_dollars
        d["goal_under_funded"] = (
            self.goal_under_funded / 1000.0 if self.goal_under_funded is not None else None
        )
        return d


class AccountInfo(BaseModel):
    """A budget account from YNAB."""

    id: str
    name: str
    type: str
    on_budget: bool = True
    closed: bool = False
    balance: int = 0  # milliunits
    cleared_balance: int = 0  # milliunits
    uncleared_balance: int = 0  # milliunits
    note: str | None = None

    @property
    def balance_dollars(self) -> float:
        return self.balance / 1000.0

    @property
    def cleared_balance_dollars(self) -> float:
        return self.cleared_balance / 1000.0

    @property
    def uncleared_balance_dollars(self) -> float:
        return self.uncleared_balance / 1000.0

    def to_output_dict(self) -> dict:
        """Serialize with dollar amounts instead of milliunits."""
        d = self.model_dump()
        d["balance"] = self.balance_dollars
        d["cleared_balance"] = self.cleared_balance_dollars
        d["uncleared_balance"] = self.uncleared_balance_dollars
        return d


class PayeeInfo(BaseModel):
    """A payee from YNAB."""

    id: str
    name: str
    transfer_account_id: str | None = None


class PlanInfo(BaseModel):
    """A YNAB plan/budget."""

    id: str
    name: str


class CategorizationDecision(BaseModel):
    """A recorded categorization decision."""

    timestamp: datetime
    transaction_id: str
    payee_id: str | None = None
    payee_name: str | None = None
    amount_milliunits: int = 0
    proposed_category_id: str | None = None
    proposed_category_name: str | None = None
    final_category_id: str
    final_category_name: str
    source: str = "agent"  # "agent" or "user"
    was_corrected: bool = False


class RebalanceDecision(BaseModel):
    """A recorded rebalancing decision."""

    timestamp: datetime
    from_category_id: str
    from_category_name: str
    to_category_id: str
    to_category_name: str
    amount_milliunits: int
    reasoning: str = ""


class AssignmentDecision(BaseModel):
    """A recorded RTA assignment decision."""

    timestamp: datetime
    category_id: str
    category_name: str
    amount_milliunits: int
    month: str = "current"
    reasoning: str = ""


class CategoryProposal(BaseModel):
    """A proposed category assignment for a transaction."""

    transaction: TransactionInfo
    proposed_category_id: str | None = None
    proposed_category_name: str | None = None
    confidence: int = 0  # 0-3: 0=new payee, 1=fuzzy match, 2=few matches, 3=strong match
    match_count: int = 0
    alternatives: list[str] = []  # other category names seen for this payee
    skip_reason: str | None = None  # e.g., "split transaction"


class RebalanceProposal(BaseModel):
    """A proposed budget move between categories."""

    from_category_id: str
    from_category_name: str
    from_remaining: int  # milliunits
    to_category_id: str
    to_category_name: str
    to_shortfall: int  # milliunits (positive = underfunded)
    amount: int  # milliunits
    reasoning: str


class Config(BaseModel):
    """Persistent configuration."""

    plan_id: str | None = None
    plan_name: str | None = None
    server_knowledge_transactions: int | None = None
    server_knowledge_categories: int | None = None
    server_knowledge_payees: int | None = None
