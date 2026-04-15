"""Pydantic models for YNAB agent data."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def dollars_to_milliunits(dollars: float) -> int:
    """Convert a dollar amount to YNAB milliunits, rounded to the nearest cent.

    Uses Decimal to avoid IEEE 754 floating-point artifacts (e.g., 49.995
    being represented as 49.99499... and rounding down instead of up).
    """
    from decimal import ROUND_HALF_UP, Decimal

    d = Decimal(str(dollars)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 1000)


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
    cleared: str = "uncleared"  # "cleared", "uncleared", or "reconciled"
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

    timestamp: datetime = Field(default_factory=datetime.now)
    transaction_id: str
    payee_id: str | None = None
    payee_name: str | None = None
    amount: float = 0  # dollars
    proposed_category_id: str | None = None
    proposed_category_name: str | None = None
    final_category_id: str
    final_category_name: str
    source: str = "agent"  # "agent" or "user"
    was_corrected: bool = False


class RebalanceDecision(BaseModel):
    """A recorded rebalancing decision."""

    timestamp: datetime = Field(default_factory=datetime.now)
    from_category_id: str
    from_category_name: str
    to_category_id: str
    to_category_name: str
    amount: float  # dollars
    reasoning: str = ""


class AssignmentDecision(BaseModel):
    """A recorded RTA assignment decision."""

    timestamp: datetime = Field(default_factory=datetime.now)
    category_id: str
    category_name: str
    amount: float  # dollars
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


# --- Stdin input models for `apply` and `history` commands ---


class CategorizeUpdate(BaseModel):
    """A single transaction category update."""

    transaction_id: str
    category_id: str


class CategorizeInput(BaseModel):
    """Stdin schema for `apply categorize`."""

    updates: list[CategorizeUpdate] = []


class ApproveInput(BaseModel):
    """Stdin schema for `apply approve`."""

    transaction_ids: list[str] = []


class RebalanceMove(BaseModel):
    """A single budget rebalance move. Amount is in dollars."""

    from_category_id: str
    to_category_id: str
    amount: float  # dollars to move


class RebalanceInput(BaseModel):
    """Stdin schema for `apply rebalance`."""

    moves: list[RebalanceMove] = []


class Assignment(BaseModel):
    """A single RTA assignment. Amount is in dollars."""

    category_id: str
    amount: float  # dollars


class AssignInput(BaseModel):
    """Stdin schema for `apply assign`."""

    assignments: list[Assignment] = []
    month: str = "current"


class CategorizationRecordInput(BaseModel):
    """Stdin schema for `history record`."""

    decisions: list[CategorizationDecision] = []


class RebalanceRecordInput(BaseModel):
    """Stdin schema for `history record-rebalance`."""

    decisions: list[RebalanceDecision] = []


class AssignmentRecordInput(BaseModel):
    """Stdin schema for `history record-assignment`."""

    decisions: list[AssignmentDecision] = []


class Config(BaseModel):
    """Persistent configuration."""

    plan_id: str | None = None
    plan_name: str | None = None
    server_knowledge_transactions: int | None = None
    server_knowledge_categories: int | None = None
    server_knowledge_payees: int | None = None
