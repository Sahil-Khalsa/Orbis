"""Adjudication orchestrator. architecture.md section 6.

    1. extract(raw fields)
    2. load state
    3. run all 6 rules
    4. injection_flags non-empty -> ROUTE_TO_HUMAN, INJECTION_SUSPECTED
    5. outcome = resolve(results)
    6. DEFER -> reasoner -> faithfulness validator
    7. assert cited_rule_ids or cited_warrant_id
    8. persist decision + rule_results
    9. AUTO_APPROVE -> execute() | ROUTE -> queue | BLOCK -> stop
   10. if R5 fired -> freeze agent, hold its pending requests

Four decisions made deliberately conservative here, not spelled out in the
rule logic itself:

  - CLEAR_DEFERRAL never resolves straight to AUTO_APPROVE. The reasoner's
    return type has no approval value (invariant 1's letter), but silently
    re-resolving a cleared deferral to all-AUTO_APPROVE would violate its
    spirit -- money would move because a model said the ambiguity was
    resolved. CLEAR_DEFERRAL still routes to a human.
  - DEFER with no reasoner configured (no OPENAI_API_KEY) routes to a human
    with reason REASONER_UNAVAILABLE, rather than blocking outright or
    (worse) approving. This keeps every other demo beat runnable with zero
    external dependencies.
  - cited_warrant_id is set whenever a warrant was resolved, not only when
    a rule fired against it -- otherwise a clean six-pass AUTO_APPROVE has
    an empty citation and invariant 3's assert kills the simplest beat.
  - injection_flags forces ROUTE_TO_HUMAN ahead of rule resolution
    entirely, per architecture.md section 7.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from fallback.db import dumps, new_id
from fallback.execution import execute_decision
from fallback.extractor import extract
from fallback.reasoner import faithfulness_check, reasoner_configured, run_reasoner
from fallback.rules import resolve, run_all
from fallback.state import load_state
from fallback.types import Decision, DecidedBy, Outcome, RuleResult, SpendRequest


def adjudicate(conn: sqlite3.Connection, request: SpendRequest, now: datetime | None = None) -> Decision:
    now = now or datetime.now()

    extraction = extract(conn, request)
    _persist_extraction(conn, request.id, extraction)
    state = load_state(conn, request, extraction.vendor_id_match, extraction.match_confidence, now)
    results = run_all(request, extraction, state)

    decided_by = DecidedBy.engine
    rationale_extra = ""

    if extraction.injection_flags:
        outcome = Outcome.ROUTE_TO_HUMAN
        rationale_extra = f"Injection flags on submitted text: {extraction.injection_flags}."
    else:
        raw_outcome = resolve(results)
        if raw_outcome == Outcome.DEFER:
            reasoner_output = run_reasoner(conn, request, extraction, state)
            if reasoner_output is None:
                outcome = Outcome.ROUTE_TO_HUMAN
                if reasoner_configured():
                    rationale_extra = "Reasoner call failed (see server log); routed for human review."
                else:
                    rationale_extra = "Reasoner unavailable (no model configured); routed for human review."
            elif not faithfulness_check(reasoner_output, conn, extraction, state):
                outcome = Outcome.ROUTE_TO_HUMAN
                rationale_extra = "Reasoner rationale failed the faithfulness validator; discarded."
            elif reasoner_output.verdict == "BLOCK":
                outcome = Outcome.BLOCK
                decided_by = DecidedBy.reasoner
                rationale_extra = reasoner_output.rationale
            elif reasoner_output.verdict == "ROUTE":
                outcome = Outcome.ROUTE_TO_HUMAN
                decided_by = DecidedBy.reasoner
                rationale_extra = reasoner_output.rationale
            else:  # CLEAR_DEFERRAL -- still a human confirms before money moves.
                outcome = Outcome.ROUTE_TO_HUMAN
                decided_by = DecidedBy.reasoner
                rationale_extra = f"Reasoner cleared the deferral, pending human confirmation: {reasoner_output.rationale}"
        else:
            outcome = raw_outcome

    fired_rules = [r for r in results if r.outcome != Outcome.AUTO_APPROVE]
    cited_rule_ids = [r.rule_id for r in fired_rules]
    cited_warrant_id = state.warrant["id"] if state.warrant else None

    assert cited_rule_ids or cited_warrant_id, "invariant 3: every decision must cite a rule or a warrant"

    rationale_parts = [f"{r.rule_id} {r.reason_code}: {r.detail}" for r in fired_rules]
    if rationale_extra:
        rationale_parts.append(rationale_extra)
    rationale = " | ".join(rationale_parts) or "All six rules passed within warrant scope."

    decision = Decision(
        id=new_id("d"),
        spend_request_id=request.id,
        outcome=outcome.value,
        decided_at=now.isoformat(),
        decided_by=decided_by,
        rationale=rationale,
        cited_rule_ids=cited_rule_ids,
        cited_warrant_id=cited_warrant_id,
        rule_results=results,
    )

    _persist(conn, decision)

    if outcome == Outcome.AUTO_APPROVE:
        conn.execute("UPDATE spend_requests SET status = 'decided' WHERE id = ?", (request.id,))
        conn.commit()
        execute_decision(conn, request, decision, now)
    elif outcome == Outcome.ROUTE_TO_HUMAN:
        conn.execute("UPDATE spend_requests SET status = 'queued' WHERE id = ?", (request.id,))
        conn.commit()
    else:  # BLOCK
        conn.execute("UPDATE spend_requests SET status = 'decided' WHERE id = ?", (request.id,))
        conn.commit()

    if any(r.rule_id == "R5" for r in fired_rules):
        _freeze_agent(conn, request.agent_id)

    return decision


def _persist_extraction(conn: sqlite3.Connection, spend_request_id: str, extraction) -> None:
    conn.execute(
        "INSERT INTO extractions VALUES (?,?,?,?,?,?,?,?)",
        (new_id("ex"), spend_request_id, extraction.vendor_name_norm, extraction.vendor_id_match,
         extraction.match_confidence, extraction.purpose_class.value,
         dumps([li.model_dump() for li in extraction.line_items]), dumps(extraction.injection_flags)),
    )
    conn.commit()


def _persist(conn: sqlite3.Connection, decision: Decision) -> None:
    conn.execute(
        "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)",
        (decision.id, decision.spend_request_id, decision.outcome, decision.decided_at,
         decision.decided_by.value, decision.rationale, dumps(decision.cited_rule_ids),
         decision.cited_warrant_id),
    )
    for r in decision.rule_results:
        conn.execute(
            "INSERT INTO rule_results VALUES (?,?,?,?,?,?,?)",
            (new_id("rr"), decision.id, r.rule_id, r.outcome.value, r.reason_code, r.detail,
             dumps(r.evidence_ids)),
        )
    conn.commit()


def _freeze_agent(conn: sqlite3.Connection, agent_id: str) -> None:
    """R5's freeze side effect lives here, not in the rule -- rules are pure."""
    conn.execute("UPDATE agents SET status = 'frozen' WHERE id = ?", (agent_id,))
    conn.execute(
        "UPDATE spend_requests SET status = 'queued' WHERE agent_id = ? AND status = 'submitted'",
        (agent_id,),
    )
    conn.commit()
