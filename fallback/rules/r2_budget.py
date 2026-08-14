from __future__ import annotations

from fallback.state import State
from fallback.types import Extraction, Outcome, RuleResult, SpendRequest

RULE_ID = "R2"


def check(request: SpendRequest, extraction: Extraction, state: State) -> RuleResult:
    budget = state.budget

    if budget is None:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.ROUTE_TO_HUMAN, reason_code="BUDGET_UNAVAILABLE",
            detail=f"No budget period found for category '{request.category}' at this date.",
        )

    if budget["budgeted_cents"] <= 0:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.ROUTE_TO_HUMAN, reason_code="BUDGET_UNAVAILABLE",
            detail="Budget for this category is zero or unset.",
            evidence_ids=[budget["id"]],
        )

    ratio = (budget["committed_cents"] + request.amount_cents) / budget["budgeted_cents"]
    detail = (
        f"(committed {budget['committed_cents']}c + amount {request.amount_cents}c) / "
        f"budgeted {budget['budgeted_cents']}c = {ratio:.3f}"
    )

    if ratio <= 1.05:
        outcome, reason = Outcome.AUTO_APPROVE, "BUDGET_WITHIN_LIMIT"
    elif ratio <= 1.20:
        outcome, reason = Outcome.ROUTE_TO_HUMAN, "BUDGET_HEADROOM_LOW"
    else:
        outcome, reason = Outcome.BLOCK, "BUDGET_EXCEEDED"

    return RuleResult(
        rule_id=RULE_ID, outcome=outcome, reason_code=reason, detail=detail, evidence_ids=[budget["id"]],
    )
