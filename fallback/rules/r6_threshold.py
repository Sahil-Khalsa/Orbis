from __future__ import annotations

from fallback.state import State
from fallback.types import Extraction, Outcome, RuleResult, SpendRequest

RULE_ID = "R6"
HARD_THRESHOLD_CENTS = 500_000
SOFT_THRESHOLD_CENTS = 200_000
SOFT_THRESHOLD_CATEGORIES = {"legal", "contractor", "marketing"}


def check(request: SpendRequest, extraction: Extraction, state: State) -> RuleResult:
    if request.amount_cents > HARD_THRESHOLD_CENTS:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.ROUTE_TO_HUMAN, reason_code="APPROVAL_REQUIRED",
            detail=f"{request.amount_cents}c exceeds the ${HARD_THRESHOLD_CENTS/100:,.0f} hard threshold.",
        )

    if request.amount_cents > SOFT_THRESHOLD_CENTS and request.category in SOFT_THRESHOLD_CATEGORIES:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.ROUTE_TO_HUMAN, reason_code="APPROVAL_REQUIRED",
            detail=(
                f"{request.amount_cents}c exceeds ${SOFT_THRESHOLD_CENTS/100:,.0f} for category "
                f"'{request.category}'."
            ),
        )

    return RuleResult(
        rule_id=RULE_ID, outcome=Outcome.AUTO_APPROVE, reason_code="BELOW_THRESHOLD",
        detail="Amount is below routing thresholds.",
    )
