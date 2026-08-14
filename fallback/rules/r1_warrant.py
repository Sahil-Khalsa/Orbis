from __future__ import annotations

from fallback.state import State
from fallback.types import DestinationType, Extraction, Outcome, RuleResult, SpendRequest

RULE_ID = "R1"


def check(request: SpendRequest, extraction: Extraction, state: State) -> RuleResult:
    warrant = state.warrant

    if warrant is None:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_MISSING",
            detail="No warrant is attached to this request.",
        )

    if warrant["agent_id"] != request.agent_id:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_AGENT_MISMATCH",
            detail="This warrant does not belong to the requesting agent.",
            evidence_ids=[warrant["id"]],
        )

    if warrant["status"] != "active":
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_INACTIVE",
            detail=f"Warrant status is '{warrant['status']}', not active.",
            evidence_ids=[warrant["id"]],
        )

    now_date = state.now.date().isoformat()
    if not (warrant["valid_from"] <= now_date <= warrant["valid_until"]):
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_EXPIRED",
            detail=f"Warrant valid {warrant['valid_from']}..{warrant['valid_until']}, request at {now_date}.",
            evidence_ids=[warrant["id"]],
        )

    if request.category not in warrant["categories"]:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_CATEGORY_OUT_OF_SCOPE",
            detail=f"Category '{request.category}' not in warrant categories {warrant['categories']}.",
            evidence_ids=[warrant["id"]],
        )

    if request.amount_cents > warrant["ceiling_per_txn_cents"]:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_PER_TXN_CEILING_EXCEEDED",
            detail=f"{request.amount_cents}c exceeds per-txn ceiling {warrant['ceiling_per_txn_cents']}c.",
            evidence_ids=[warrant["id"]],
        )

    if warrant["spent_total_cents"] + request.amount_cents > warrant["ceiling_total_cents"]:
        return RuleResult(
            rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_TOTAL_CEILING_EXCEEDED",
            detail=(
                f"Spent {warrant['spent_total_cents']}c + {request.amount_cents}c exceeds "
                f"total ceiling {warrant['ceiling_total_cents']}c."
            ),
            evidence_ids=[warrant["id"]],
        )

    if request.destination_type == DestinationType.bank:
        scope = warrant["vendor_scope"]
        if scope != ["*"]:
            if not extraction.vendor_id_match or extraction.vendor_id_match not in scope:
                return RuleResult(
                    rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_DESTINATION_OUT_OF_SCOPE",
                    detail="Vendor is not within this warrant's vendor scope.",
                    evidence_ids=[warrant["id"]],
                )
    else:
        scope = warrant["counterparty_scope"]
        if scope != ["*"]:
            if not request.counterparty_agent_id or request.counterparty_agent_id not in scope:
                return RuleResult(
                    rule_id=RULE_ID, outcome=Outcome.BLOCK, reason_code="WARRANT_DESTINATION_OUT_OF_SCOPE",
                    detail="Counterparty agent is not within this warrant's counterparty scope.",
                    evidence_ids=[warrant["id"]],
                )

    return RuleResult(
        rule_id=RULE_ID, outcome=Outcome.AUTO_APPROVE, reason_code="WARRANT_OK",
        detail="Request is within warrant scope and ceilings.",
        evidence_ids=[warrant["id"]],
    )
