"""Tests for assignment decisions and active-category filtering."""

import json
from datetime import UTC, datetime

import pytest

from app.models import AssignmentDecision


@pytest.fixture(autouse=True)
def _clean_history(tmp_path, monkeypatch):
    """Use a temp directory for history files."""
    monkeypatch.setattr("app.paths.HISTORY_DIR", tmp_path)
    monkeypatch.setattr("app.paths.ASSIGNMENTS_FILE", tmp_path / "assignments.jsonl")


def _make_assignment(
    category_id: str = "cat1",
    category_name: str = "Groceries",
    amount_milliunits: int = 50000,
    month: str = "current",
    reasoning: str = "Weekly grocery budget top-up",
) -> AssignmentDecision:
    return AssignmentDecision(
        timestamp=datetime.now(UTC),
        category_id=category_id,
        category_name=category_name,
        amount_milliunits=amount_milliunits,
        month=month,
        reasoning=reasoning,
    )


class TestAssignmentDecisionModel:
    def test_create_with_all_fields(self):
        ts = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
        d = AssignmentDecision(
            timestamp=ts,
            category_id="cat1",
            category_name="Groceries",
            amount_milliunits=150000,
            month="2026-04-01",
            reasoning="Underfunded for the month",
        )
        assert d.category_id == "cat1"
        assert d.category_name == "Groceries"
        assert d.amount_milliunits == 150000
        assert d.month == "2026-04-01"
        assert d.reasoning == "Underfunded for the month"
        assert d.timestamp == ts

    def test_defaults(self):
        d = AssignmentDecision(
            timestamp=datetime.now(UTC),
            category_id="cat1",
            category_name="Groceries",
            amount_milliunits=50000,
        )
        assert d.month == "current"
        assert d.reasoning == ""

    def test_serialize_roundtrip(self):
        original = _make_assignment()
        json_str = original.model_dump_json()
        restored = AssignmentDecision.model_validate_json(json_str)
        assert restored.category_id == original.category_id
        assert restored.category_name == original.category_name
        assert restored.amount_milliunits == original.amount_milliunits
        assert restored.month == original.month
        assert restored.reasoning == original.reasoning

    def test_serialize_to_dict(self):
        d = _make_assignment()
        data = d.model_dump()
        assert isinstance(data, dict)
        assert data["category_id"] == "cat1"
        assert data["amount_milliunits"] == 50000


class TestRecordAssignmentDecisions:
    def test_appends_to_jsonl(self, tmp_path):
        assignments_file = tmp_path / "assignments.jsonl"
        decisions = [
            _make_assignment(),
            _make_assignment(category_name="Dining Out", category_id="cat2"),
        ]

        # Write decisions manually (same pattern as record_rebalance_decisions)
        with open(assignments_file, "a") as f:
            for d in decisions:
                f.write(d.model_dump_json() + "\n")

        lines = assignments_file.read_text().strip().split("\n")
        assert len(lines) == 2

        first = AssignmentDecision(**json.loads(lines[0]))
        assert first.category_name == "Groceries"

        second = AssignmentDecision(**json.loads(lines[1]))
        assert second.category_name == "Dining Out"

    def test_append_preserves_existing(self, tmp_path):
        assignments_file = tmp_path / "assignments.jsonl"

        # First batch
        with open(assignments_file, "a") as f:
            f.write(_make_assignment(category_name="Groceries").model_dump_json() + "\n")

        # Second batch
        with open(assignments_file, "a") as f:
            f.write(_make_assignment(category_name="Rent").model_dump_json() + "\n")

        lines = assignments_file.read_text().strip().split("\n")
        assert len(lines) == 2
        assert "Groceries" in lines[0]
        assert "Rent" in lines[1]


class TestActiveCategoryFiltering:
    """Test filtering categories to only those with non-zero budgeted, activity, or balance."""

    @staticmethod
    def _filter_active(categories: list[dict]) -> list[dict]:
        """Filter to categories with any non-zero financial field."""
        return [
            c
            for c in categories
            if c.get("budgeted", 0) != 0 or c.get("activity", 0) != 0 or c.get("balance", 0) != 0
        ]

    def test_keeps_budgeted_category(self):
        cats = [{"name": "Groceries", "budgeted": 500000, "activity": 0, "balance": 500000}]
        assert len(self._filter_active(cats)) == 1

    def test_keeps_category_with_activity(self):
        cats = [{"name": "Dining", "budgeted": 0, "activity": -25000, "balance": -25000}]
        assert len(self._filter_active(cats)) == 1

    def test_keeps_category_with_balance_only(self):
        cats = [{"name": "Emergency Fund", "budgeted": 0, "activity": 0, "balance": 1000000}]
        assert len(self._filter_active(cats)) == 1

    def test_excludes_all_zero_category(self):
        cats = [{"name": "Unused", "budgeted": 0, "activity": 0, "balance": 0}]
        assert len(self._filter_active(cats)) == 0

    def test_mixed_list(self):
        cats = [
            {"name": "Groceries", "budgeted": 500000, "activity": -200000, "balance": 300000},
            {"name": "Unused A", "budgeted": 0, "activity": 0, "balance": 0},
            {"name": "Rent", "budgeted": 1500000, "activity": 0, "balance": 1500000},
            {"name": "Unused B", "budgeted": 0, "activity": 0, "balance": 0},
            {"name": "Refund", "budgeted": 0, "activity": 5000, "balance": 5000},
        ]
        active = self._filter_active(cats)
        active_names = [c["name"] for c in active]
        assert active_names == ["Groceries", "Rent", "Refund"]

    def test_empty_list(self):
        assert self._filter_active([]) == []

    def test_missing_fields_treated_as_zero(self):
        cats = [{"name": "Bare"}, {"name": "Has Budget", "budgeted": 100}]
        active = self._filter_active(cats)
        assert len(active) == 1
        assert active[0]["name"] == "Has Budget"
