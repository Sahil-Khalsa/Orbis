from __future__ import annotations

from fallback.state import State
from fallback.types import OUTCOME_PRECEDENCE, Extraction, Outcome, RuleResult, SpendRequest

from . import r1_warrant, r2_budget, r3_counterparty, r4_duplicate, r5_velocity, r6_threshold

ALL_RULES = [r1_warrant, r2_budget, r3_counterparty, r4_duplicate, r5_velocity, r6_threshold]


def run_all(request: SpendRequest, extraction: Extraction, state: State) -> list[RuleResult]:
    """Run all six rules. No short-circuit -- the decision view shows every result."""
    return [module.check(request, extraction, state) for module in ALL_RULES]


def resolve(results: list[RuleResult]) -> Outcome:
    """BLOCK > ROUTE_TO_HUMAN > DEFER > AUTO_APPROVE."""
    present = {r.outcome for r in results}
    for outcome in OUTCOME_PRECEDENCE:
        if outcome in present:
            return outcome
    return Outcome.AUTO_APPROVE
