from __future__ import annotations

from fallback.state import State
from fallback.types import Extraction, Outcome, RuleResult, SpendRequest

RULE_ID = "R5"
MAX_REQUESTS_PER_10MIN = 5
SPEND_MULTIPLIER = 4
# A cold-start agent (little or no trailing-30-day history) has a baseline
# near zero, which makes any spend at all trivially exceed 4x baseline.
# More generally: real spend is bursty, not smooth -- a single ordinary
# transaction landing in one hour routinely dwarfs a thin 24/7-averaged
# hourly baseline for any agent that transacts a few times a day rather
# than continuously. Require a baseline high enough to reflect genuinely
# frequent activity before trusting the spend-ratio branch; below that,
# rely on the count-based check instead.
MIN_BASELINE_CENTS_FOR_CHECK = 50_000


def check(request: SpendRequest, extraction: Extraction, state: State) -> RuleResult:
    # state.agent_request_count_10min counts prior requests only; this request
    # would make it count + 1, so >5 total means count >= 5.
    if state.agent_request_count_10min >= MAX_REQUESTS_PER_10MIN:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="VELOCITY_ANOMALY",
            detail=(
                f"{state.agent_request_count_10min + 1} requests within 10 minutes "
                f"exceeds the limit of {MAX_REQUESTS_PER_10MIN}."
            ),
        )

    baseline = state.agent_baseline_hourly_cents
    if baseline >= MIN_BASELINE_CENTS_FOR_CHECK and state.agent_trailing_1h_spend_cents > SPEND_MULTIPLIER * baseline:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="VELOCITY_ANOMALY",
            detail=(
                f"Trailing 1h spend {state.agent_trailing_1h_spend_cents}c exceeds "
                f"{SPEND_MULTIPLIER}x the 30-day hourly baseline ({baseline:.0f}c)."
            ),
        )

    return RuleResult(
        rule_id=RULE_ID, outcome=Outcome.AUTO_APPROVE, reason_code="VELOCITY_NORMAL",
        detail="Request rate and trailing spend are within normal bounds.",
    )
