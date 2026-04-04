"""Tests for output formatting."""

from datetime import date

from app.formatting import format_budget_status, format_categorization_proposals
from app.models import CategoryInfo, CategoryProposal, GoalType, TransactionInfo


class TestFormatCategorizationProposals:
    def test_normal_proposal(self):
        proposals = [
            CategoryProposal(
                transaction=TransactionInfo(
                    id="t1",
                    date=date(2026, 4, 1),
                    amount=-45230,
                    payee_name="TRADER JOES",
                    account_name="Checking",
                ),
                proposed_category_id="cat1",
                proposed_category_name="Groceries",
                confidence=3,
                match_count=20,
            )
        ]
        rows = format_categorization_proposals(proposals)
        assert len(rows) == 1
        assert rows[0]["payee"] == "TRADER JOES"
        assert rows[0]["amount"] == -45.23
        assert rows[0]["proposed_category"] == "Groceries"
        assert rows[0]["confidence"] == 3

    def test_split_transaction_skipped(self):
        proposals = [
            CategoryProposal(
                transaction=TransactionInfo(
                    id="t1",
                    date=date(2026, 4, 1),
                    amount=-87300,
                    payee_name="COSTCO",
                    is_split=True,
                ),
                skip_reason="Split transaction (edit in YNAB)",
            )
        ]
        rows = format_categorization_proposals(proposals)
        assert rows[0]["proposed_category"] is None
        assert rows[0]["skip_reason"] == "Split transaction (edit in YNAB)"


class TestFormatBudgetStatus:
    def test_basic_status(self):
        categories = [
            CategoryInfo(
                id="cat1",
                name="Groceries",
                group_name="Everyday Expenses",
                budgeted=500000,
                activity=-312500,
                balance=187500,
                goal_type=GoalType.MONTHLY_FUNDING,
                goal_target=500000,
            ),
        ]
        result = format_budget_status(categories)
        assert result["categories"][0]["name"] == "Groceries"
        assert result["categories"][0]["budgeted"] == 500.0
        assert result["categories"][0]["spent"] == -312.5
        assert result["categories"][0]["remaining"] == 187.5

    def test_filters_internal_categories(self):
        categories = [
            CategoryInfo(
                id="cat1",
                name="Groceries",
                group_name="Everyday Expenses",
                budgeted=500000,
                activity=-312500,
                balance=187500,
            ),
            CategoryInfo(
                id="cat2",
                name="Uncategorized",
                group_name="Internal Master Category",
            ),
        ]
        result = format_budget_status(categories)
        names = [c["name"] for c in result["categories"]]
        assert "Groceries" in names
        assert "Uncategorized" not in names

    def test_flags_overspent(self):
        categories = [
            CategoryInfo(
                id="cat1",
                name="Dining Out",
                group_name="Everyday Expenses",
                budgeted=200000,
                activity=-250000,
                balance=-50000,
            ),
        ]
        result = format_budget_status(categories)
        assert result["categories"][0]["pace"] == "overspent"
        assert any("Dining Out" in f and "overspent" in f for f in result["flags"])

    def test_to_be_budgeted(self):
        """to_be_budgeted comes from the API month-level field, not from the
        Inflow category balance (which is income, not unassigned money)."""
        categories = [
            CategoryInfo(
                id="rta",
                name="Inflow: Ready to Assign",
                group_name="Internal Master Category",
                balance=112000,
            ),
        ]
        result = format_budget_status(categories, to_be_budgeted=45.0, income=112.0)
        assert result["to_be_budgeted"] == 45.0
        assert result["income"] == 112.0
