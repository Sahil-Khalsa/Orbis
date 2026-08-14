from __future__ import annotations

from fallback.state import State
from fallback.types import DestinationType, Extraction, Outcome, RuleResult, SpendRequest

RULE_ID = "R3"


def check(request: SpendRequest, extraction: Extraction, state: State) -> RuleResult:
    if request.destination_type == DestinationType.agent:
        return _check_agent_counterparty(request, state)
    return _check_vendor_counterparty(extraction, state)


def _check_vendor_counterparty(extraction: Extraction, state: State) -> RuleResult:
    confidence = extraction.match_confidence
    vendor = state.vendor

    if vendor is not None and confidence >= 0.90:
        if vendor["status"] == "approved":
            return RuleResult(
                rule_id=RULE_ID, outcome=Outcome.AUTO_APPROVE, reason_code="VENDOR_APPROVED",
                detail=f"Vendor '{vendor['canonical_name']}' is approved.", evidence_ids=[vendor["id"]],
            )
        if vendor["status"] == "pending":
            return RuleResult(
                rule_id=RULE_ID, outcome=Outcome.ROUTE_TO_HUMAN, reason_code="PENDING_VENDOR",
                detail=f"Vendor '{vendor['canonical_name']}' is pending onboarding.", evidence_ids=[vendor["id"]],
            )
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="VENDOR_BLOCKED",
            detail=f"Vendor '{vendor['canonical_name']}' is blocked.", evidence_ids=[vendor["id"]],
        )

    if vendor is not None and 0.65 <= confidence < 0.90:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.DEFER, reason_code="VENDOR_MATCH_AMBIGUOUS",
            detail=(
                f"Match confidence {confidence:.2f} for '{extraction.vendor_name_norm}' against "
                f"'{vendor['canonical_name']}' is in the ambiguous band."
            ),
            evidence_ids=[vendor["id"]],
        )

    return RuleResult(
        rule_id=RULE_ID, outcome=Outcome.ROUTE_TO_HUMAN, reason_code="NEW_VENDOR",
        detail=f"'{extraction.vendor_name_norm}' does not resolve to a known vendor (confidence {confidence:.2f}).",
    )


def _check_agent_counterparty(request: SpendRequest, state: State) -> RuleResult:
    agent = state.payee_agent

    if agent is None:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.ROUTE_TO_HUMAN, reason_code="NEW_COUNTERPARTY_AGENT",
            detail="Counterparty agent is not a registered payee agent.",
        )

    if agent["status"] == "frozen":
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="COUNTERPARTY_AGENT_FROZEN",
            detail=f"Payee agent '{agent['name']}' is frozen.", evidence_ids=[agent["id"]],
        )

    return RuleResult(
        rule_id=RULE_ID, outcome=Outcome.AUTO_APPROVE, reason_code="COUNTERPARTY_AGENT_OK",
        detail=f"Payee agent '{agent['name']}' is active and registered.", evidence_ids=[agent["id"]],
    )
