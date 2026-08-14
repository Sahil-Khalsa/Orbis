from __future__ import annotations

from datetime import timedelta

from fallback.state import State
from fallback.types import Extraction, Outcome, RuleResult, SpendRequest

RULE_ID = "R4"
LOOKBACK_DAYS = 30
AMOUNT_TOLERANCE = 0.05


def check(request: SpendRequest, extraction: Extraction, state: State) -> RuleResult:
    cutoff = (state.now - timedelta(days=LOOKBACK_DAYS)).isoformat()

    for prior in state.counterparty_prior_transactions:
        if prior["occurred_at"] < cutoff:
            continue
        if prior["category"] != request.category:
            continue
        prior_amount = prior["amount_cents"]
        if prior_amount <= 0:
            continue
        pct_diff = abs(request.amount_cents - prior_amount) / prior_amount
        if pct_diff > AMOUNT_TOLERANCE:
            continue

        if prior["recurring"]:
            return RuleResult(
                rule_id=RULE_ID, outcome=Outcome.DEFER, reason_code="DUPLICATE_CANDIDATE_RECURRING",
                detail=(
                    f"Matches prior recurring txn {prior['id']} ({prior_amount}c on {prior['occurred_at']}), "
                    f"{pct_diff:.1%} amount difference."
                ),
                evidence_ids=[prior["id"]],
            )

        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="DUPLICATE_SUSPECTED",
            detail=(
                f"Matches prior non-recurring txn {prior['id']} ({prior_amount}c on {prior['occurred_at']}), "
                f"{pct_diff:.1%} amount difference, same category, within {LOOKBACK_DAYS} days."
            ),
            evidence_ids=[prior["id"]],
        )

    return RuleResult(
        rule_id=RULE_ID, outcome=Outcome.AUTO_APPROVE, reason_code="NO_DUPLICATE_FOUND",
        detail="No matching prior transaction within the lookback window.",
    )
