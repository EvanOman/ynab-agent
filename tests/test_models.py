"""Tests for data models."""

from datetime import date

from ynab_agent.models import CategoryInfo, Config, GoalType, TransactionInfo, dollars_to_milliunits


def test_transaction_amount_dollars():
    t = TransactionInfo(id="1", date=date(2026, 4, 1), amount=-45230)
    assert t.amount_dollars == -45.23


def test_transaction_amount_positive():
    t = TransactionInfo(id="1", date=date(2026, 4, 1), amount=10000)
    assert t.amount_dollars == 10.0


def test_category_dollar_properties():
    c = CategoryInfo(
        id="1",
        name="Groceries",
        budgeted=500000,
        activity=-312500,
        balance=187500,
        goal_target=500000,
    )
    assert c.budgeted_dollars == 500.0
    assert c.activity_dollars == -312.5
    assert c.balance_dollars == 187.5
    assert c.goal_target_dollars == 500.0


def test_category_no_goal_target():
    c = CategoryInfo(id="1", name="Misc")
    assert c.goal_target_dollars is None


def test_config_defaults():
    cfg = Config()
    assert cfg.plan_id is None
    assert cfg.server_knowledge_transactions is None


def test_goal_type_enum():
    assert GoalType.MONTHLY_FUNDING == "MF"
    assert GoalType.TARGET_BALANCE_BY_DATE == "TBD"


def test_dollars_to_milliunits_basic():
    assert dollars_to_milliunits(10.00) == 10000
    assert dollars_to_milliunits(45.23) == 45230
    assert dollars_to_milliunits(-45.23) == -45230
    assert dollars_to_milliunits(0) == 0


def test_dollars_to_milliunits_rounds_to_cent():
    assert dollars_to_milliunits(99.999) == 100000  # rounds to $100.00
    assert dollars_to_milliunits(0.001) == 0  # rounds to $0.00
    assert dollars_to_milliunits(49.995) == 50000  # rounds to $50.00
    assert dollars_to_milliunits(1.01) == 1010
