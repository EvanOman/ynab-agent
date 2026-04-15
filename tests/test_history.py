"""Tests for decision history."""

from datetime import UTC, date, datetime

import pytest

from app.history import (
    _normalize_payee_name,
    lookup_payee,
    record_categorization_decisions,
    seed_from_transactions,
)
from app.models import CategorizationDecision, TransactionInfo


@pytest.fixture(autouse=True)
def _clean_history(tmp_path, monkeypatch):
    """Use a temp directory for history files."""
    monkeypatch.setattr("app.paths.HISTORY_DIR", tmp_path)
    monkeypatch.setattr("app.paths.DECISIONS_FILE", tmp_path / "decisions.jsonl")
    monkeypatch.setattr("app.paths.REBALANCES_FILE", tmp_path / "rebalances.jsonl")
    # Also patch the already-imported names in app.history
    monkeypatch.setattr("app.history.DECISIONS_FILE", tmp_path / "decisions.jsonl")
    monkeypatch.setattr("app.history.REBALANCES_FILE", tmp_path / "rebalances.jsonl")


def _make_decision(
    payee_id: str = "p1",
    payee_name: str = "TRADER JOES",
    category_name: str = "Groceries",
    category_id: str = "cat1",
    was_corrected: bool = False,
) -> CategorizationDecision:
    return CategorizationDecision(
        timestamp=datetime.now(UTC),
        transaction_id="t1",
        payee_id=payee_id,
        payee_name=payee_name,
        amount=-45.0,
        proposed_category_id=category_id,
        proposed_category_name=category_name,
        final_category_id=category_id,
        final_category_name=category_name,
        source="agent",
        was_corrected=was_corrected,
    )


class TestNormalizePayeeName:
    def test_strips_store_numbers(self):
        assert _normalize_payee_name("TRADER JOE'S #142") == "TRADER JOE'S"

    def test_strips_reference_codes(self):
        assert _normalize_payee_name("AMZN MKTP US*2A1") == "AMZN MKTP US"

    def test_uppercase(self):
        assert _normalize_payee_name("trader joes") == "TRADER JOES"

    def test_collapses_whitespace(self):
        assert _normalize_payee_name("SHELL  OIL   54892") == "SHELL OIL 54892"


class TestLookupPayee:
    def test_no_history_returns_no_matches(self):
        result = lookup_payee(payee_id="p1")
        assert result["matches"] == []
        assert result["confidence"] == 0

    def test_exact_payee_id_match(self):
        decisions = [_make_decision() for _ in range(5)]
        record_categorization_decisions(decisions)

        result = lookup_payee(payee_id="p1")
        assert result["confidence"] >= 2
        assert result["match_type"] == "payee_id"
        assert result["matches"][0]["category_name"] == "Groceries"

    def test_fuzzy_name_match(self):
        decisions = [
            _make_decision(payee_id="p1", payee_name="TRADER JOE'S #142"),
            _make_decision(payee_id="p1", payee_name="TRADER JOE'S #142"),
            _make_decision(payee_id="p1", payee_name="TRADER JOE'S #142"),
        ]
        record_categorization_decisions(decisions)

        # Look up with different store number
        result = lookup_payee(payee_id=None, payee_name="TRADER JOE'S #987")
        assert result["confidence"] >= 1
        assert result["match_type"] == "fuzzy_name"

    def test_correction_weighting(self):
        # 3 agent-accepted as Groceries, 1 user-corrected to Household
        decisions = [
            _make_decision(category_name="Groceries", category_id="cat1"),
            _make_decision(category_name="Groceries", category_id="cat1"),
            _make_decision(category_name="Groceries", category_id="cat1"),
            _make_decision(category_name="Household", category_id="cat2", was_corrected=True),
        ]
        record_categorization_decisions(decisions)

        result = lookup_payee(payee_id="p1")
        # Groceries: 3 * 1 = 3, Household: 1 * 3 = 3
        # Both should appear
        names = [m["category_name"] for m in result["matches"]]
        assert "Groceries" in names
        assert "Household" in names

    def test_strong_confidence(self):
        # 10+ matches with >80% same category
        decisions = [_make_decision() for _ in range(12)]
        record_categorization_decisions(decisions)

        result = lookup_payee(payee_id="p1")
        assert result["confidence"] == 3

    def test_multiple_categories_for_same_payee(self):
        decisions = [
            _make_decision(category_name="Groceries", category_id="cat1"),
            _make_decision(category_name="Groceries", category_id="cat1"),
            _make_decision(category_name="Household", category_id="cat2"),
        ]
        record_categorization_decisions(decisions)

        result = lookup_payee(payee_id="p1")
        assert len(result["matches"]) == 2
        assert result["matches"][0]["category_name"] == "Groceries"


class TestSeedFromTransactions:
    def test_seeds_categorized_transactions(self):
        transactions = [
            TransactionInfo(
                id="t1",
                date=date(2026, 3, 15),
                amount=-50000,
                payee_id="p1",
                payee_name="TRADER JOES",
                category_id="cat1",
                category_name="Groceries",
            ),
            TransactionInfo(
                id="t2",
                date=date(2026, 3, 16),
                amount=-30000,
                payee_id="p2",
                payee_name="SHELL OIL",
                category_id="cat2",
                category_name="Auto & Transport",
            ),
        ]
        count = seed_from_transactions(transactions)
        assert count == 2

        # Verify they can be looked up
        result = lookup_payee(payee_id="p1")
        assert result["matches"][0]["category_name"] == "Groceries"

    def test_skips_uncategorized(self):
        transactions = [
            TransactionInfo(
                id="t1",
                date=date(2026, 3, 15),
                amount=-50000,
                payee_id="p1",
                payee_name="SOMETHING",
                category_id=None,
                category_name=None,
            ),
        ]
        count = seed_from_transactions(transactions)
        assert count == 0
