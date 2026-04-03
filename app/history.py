"""Decision history management — JSONL-based storage with fuzzy payee matching."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime

from thefuzz import fuzz

from app.models import CategorizationDecision, RebalanceDecision, TransactionInfo
from app.paths import DECISIONS_FILE, REBALANCES_FILE

# Fuzzy match threshold (0-100)
FUZZY_THRESHOLD = 75

# User corrections are weighted this many times more than agent-accepted proposals
CORRECTION_WEIGHT = 3


def _ensure_history_dir() -> None:
    from app.paths import ensure_dirs

    ensure_dirs()


def _normalize_payee_name(name: str) -> str:
    """Normalize payee name for fuzzy matching.

    Strips store numbers, locations, extra whitespace.
    """
    # Remove store/location numbers like #123, *2A1
    normalized = re.sub(r"[#*]\w+", "", name)
    # Remove trailing location info (city, state patterns)
    normalized = re.sub(r"\b[A-Z]{2}\s*\d{5}\b", "", normalized)  # ZIP codes
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.upper()


def _load_decisions() -> list[CategorizationDecision]:
    """Load all categorization decisions from JSONL."""
    if not DECISIONS_FILE.exists():
        return []
    decisions = []
    for line in DECISIONS_FILE.read_text().strip().split("\n"):
        if line.strip():
            decisions.append(CategorizationDecision(**json.loads(line)))
    return decisions


def _load_rebalances() -> list[RebalanceDecision]:
    """Load all rebalance decisions from JSONL."""
    if not REBALANCES_FILE.exists():
        return []
    decisions = []
    for line in REBALANCES_FILE.read_text().strip().split("\n"):
        if line.strip():
            decisions.append(RebalanceDecision(**json.loads(line)))
    return decisions


def lookup_payee(
    payee_id: str | None = None,
    payee_name: str | None = None,
    amount: int | None = None,
) -> dict:
    """Look up categorization history for a payee.

    Returns category frequency distribution with confidence score.
    """
    decisions = _load_decisions()
    if not decisions:
        return {"matches": [], "confidence": 0, "match_type": "none"}

    # Step 1: Exact payee_id match
    if payee_id:
        id_matches = [d for d in decisions if d.payee_id == payee_id]
        if id_matches:
            return _build_lookup_result(id_matches, "payee_id", amount)

    # Step 2: Fuzzy payee_name match
    if payee_name:
        normalized = _normalize_payee_name(payee_name)
        name_matches = []
        for d in decisions:
            if d.payee_name:
                d_normalized = _normalize_payee_name(d.payee_name)
                score = fuzz.ratio(normalized, d_normalized)
                if score >= FUZZY_THRESHOLD:
                    name_matches.append(d)

        if name_matches:
            return _build_lookup_result(name_matches, "fuzzy_name", amount)

    return {"matches": [], "confidence": 0, "match_type": "none"}


def _build_lookup_result(
    matches: list[CategorizationDecision],
    match_type: str,
    amount: int | None = None,
) -> dict:
    """Build a lookup result from matching decisions."""
    # Count categories with correction weighting
    weighted_counts: Counter[str] = Counter()
    category_ids: dict[str, str] = {}

    for d in matches:
        weight = CORRECTION_WEIGHT if d.was_corrected else 1
        weighted_counts[d.final_category_name] += weight
        category_ids[d.final_category_name] = d.final_category_id

    # Sort by weighted frequency
    sorted_categories = weighted_counts.most_common()
    total_weight = sum(weighted_counts.values())
    total_matches = len(matches)

    # Calculate confidence (0-3)
    top_count = sorted_categories[0][1] if sorted_categories else 0
    if total_matches >= 10 and top_count / total_weight > 0.8:
        confidence = 3  # Strong match
    elif total_matches >= 3:
        confidence = 2  # Moderate match
    elif total_matches >= 1:
        confidence = 1  # Weak match
    else:
        confidence = 0

    result_matches = []
    for cat_name, count in sorted_categories[:3]:
        result_matches.append(
            {
                "category_name": cat_name,
                "category_id": category_ids[cat_name],
                "weighted_count": count,
                "percentage": round(count / total_weight * 100, 1),
            }
        )

    return {
        "matches": result_matches,
        "confidence": confidence,
        "match_type": match_type,
        "total_decisions": total_matches,
    }


def lookup_payee_batch(transactions: list[dict]) -> list[dict]:
    """Batch lookup for multiple transactions."""
    results = []
    for txn in transactions:
        result = lookup_payee(
            payee_id=txn.get("payee_id"),
            payee_name=txn.get("payee_name"),
            amount=txn.get("amount"),
        )
        result["transaction_id"] = txn.get("id")
        results.append(result)
    return results


def record_categorization_decisions(decisions: list[CategorizationDecision]) -> None:
    """Append categorization decisions to history."""
    _ensure_history_dir()
    with open(DECISIONS_FILE, "a") as f:
        for d in decisions:
            f.write(d.model_dump_json() + "\n")


def record_rebalance_decisions(decisions: list[RebalanceDecision]) -> None:
    """Append rebalance decisions to history."""
    _ensure_history_dir()
    with open(REBALANCES_FILE, "a") as f:
        for d in decisions:
            f.write(d.model_dump_json() + "\n")


def seed_from_transactions(transactions: list[TransactionInfo]) -> int:
    """Seed decision history from existing categorized YNAB transactions."""
    _ensure_history_dir()
    now = datetime.now(UTC)
    count = 0
    with open(DECISIONS_FILE, "a") as f:
        for t in transactions:
            if not t.category_id or not t.payee_id:
                continue
            decision = CategorizationDecision(
                timestamp=now,
                transaction_id=t.id,
                payee_id=t.payee_id,
                payee_name=t.payee_name,
                amount_milliunits=t.amount,
                proposed_category_id=t.category_id,
                proposed_category_name=t.category_name or "",
                final_category_id=t.category_id,
                final_category_name=t.category_name or "",
                source="seed",
                was_corrected=False,
            )
            f.write(decision.model_dump_json() + "\n")
            count += 1
    return count
