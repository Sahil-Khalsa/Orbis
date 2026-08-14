"""Shadow report -- backtest the rule engine over historical spend_requests.

Acceptance: exactly 7 findings (architecture.md section 10/11). Two dedup
passes keep the count meaningful instead of one row per rule-fire:

1. Per spend_request: every non-AUTO_APPROVE rule result on the same
   request is one story, not several (the ACME/Accme hero case trips both
   R3 and R4 on one transaction).
2. Across spend_requests: raw findings that share the same set of fired
   rules and the same resolved counterparty/agent collapse into one (the
   velocity burst trips R5 on 4 separate requests; that is one incident).

This intentionally runs rules only, not the full adjudicate() pipeline --
extractor/reasoner classify ambiguous *live* requests, but backtesting
historical ledger entries needs no model call: vendor resolution is the
deterministic matcher, and purpose_class is just the stored category.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from fallback.db import loads
from fallback.matcher import match_vendor, normalize
from fallback.rules import run_all
from fallback.state import load_state
from fallback.types import DestinationType, Extraction, Outcome, PurposeClass, SpendRequest


@dataclass
class RawFlag:
    txn_id: str
    occurred_at: str
    amount_cents: int
    agent_id: str
    category: str
    rule_ids: list[str]
    reason_codes: list[str]
    details: list[str]
    evidence_ids: list[str]
    vendor_id_match: str | None
    counterparty_agent_id: str | None


@dataclass
class Finding:
    txn_ids: list[str]
    rule_ids: list[str]
    reason_codes: list[str]
    amount_cents: int
    occurred_at: str
    detail: str
    evidence_ids: list[str] = field(default_factory=list)


def _identity(flag: RawFlag) -> str:
    if ("R3" in flag.rule_ids or "R4" in flag.rule_ids) and flag.vendor_id_match:
        return f"vendor:{flag.vendor_id_match}"
    if flag.counterparty_agent_id:
        return f"counterparty_agent:{flag.counterparty_agent_id}"
    return f"agent:{flag.agent_id}"


def _evaluate_request(conn: sqlite3.Connection, sr_row: dict) -> RawFlag | None:
    request = SpendRequest(
        id=sr_row["id"],
        agent_id=sr_row["agent_id"],
        warrant_id=sr_row["warrant_id"],
        destination_type=DestinationType(sr_row["destination_type"]),
        vendor_name_raw=sr_row["vendor_name_raw"],
        counterparty_agent_id=sr_row["counterparty_agent_id"],
        category=sr_row["category"],
        amount_cents=sr_row["amount_cents"],
        business_purpose_raw=sr_row["business_purpose_raw"],
        submitted_at=sr_row["submitted_at"],
        status=sr_row["status"],
    )

    vendor_id_match: str | None = None
    confidence = 0.0
    if request.destination_type == DestinationType.bank and request.vendor_name_raw:
        vendor_id_match, confidence = match_vendor(conn, request.vendor_name_raw)

    extraction = Extraction(
        spend_request_id=request.id,
        vendor_name_norm=normalize(request.vendor_name_raw) if request.vendor_name_raw else "",
        vendor_id_match=vendor_id_match,
        match_confidence=confidence,
        purpose_class=PurposeClass(request.category),
    )

    now = datetime.fromisoformat(request.submitted_at)
    state = load_state(conn, request, vendor_id_match, confidence, now, historical=True)
    results = [r for r in run_all(request, extraction, state) if r.outcome != Outcome.AUTO_APPROVE]
    if not results:
        return None

    evidence: list[str] = []
    for r in results:
        evidence.extend(r.evidence_ids)

    return RawFlag(
        txn_id=request.id,
        occurred_at=request.submitted_at,
        amount_cents=request.amount_cents,
        agent_id=request.agent_id,
        category=request.category,
        rule_ids=[r.rule_id for r in results],
        reason_codes=[r.reason_code for r in results],
        details=[f"{r.rule_id} {r.reason_code}: {r.detail}" for r in results],
        evidence_ids=evidence,
        vendor_id_match=vendor_id_match,
        counterparty_agent_id=request.counterparty_agent_id,
    )


def run_shadow_report(conn: sqlite3.Connection) -> list[Finding]:
    raw_flags: list[RawFlag] = []
    for sr_row in conn.execute("SELECT * FROM spend_requests ORDER BY submitted_at").fetchall():
        flag = _evaluate_request(conn, dict(sr_row))
        if flag:
            raw_flags.append(flag)

    groups: dict[tuple, list[RawFlag]] = {}
    for flag in raw_flags:
        key = (tuple(sorted(flag.rule_ids)), _identity(flag))
        groups.setdefault(key, []).append(flag)

    findings: list[Finding] = []
    for group in groups.values():
        group.sort(key=lambda f: f.occurred_at)
        head = group[0]
        evidence: list[str] = []
        for f in group:
            evidence.extend(f.evidence_ids)
        findings.append(
            Finding(
                txn_ids=[f.txn_id for f in group],
                rule_ids=head.rule_ids,
                reason_codes=head.reason_codes,
                amount_cents=head.amount_cents,
                occurred_at=head.occurred_at,
                detail="; ".join(head.details) + (f" (+{len(group)-1} more)" if len(group) > 1 else ""),
                evidence_ids=sorted(set(evidence)),
            )
        )

    findings.sort(key=lambda f: f.occurred_at)
    return findings


def summarize(findings: list[Finding]) -> dict:
    return {
        "count": len(findings),
        "total_impact_cents": sum(f.amount_cents for f in findings),
        "findings": [
            {
                "txn_id": f.txn_ids[0],
                "all_txn_ids": f.txn_ids,
                "rule_ids": f.rule_ids,
                "reason_codes": f.reason_codes,
                "amount_cents": f.amount_cents,
                "occurred_at": f.occurred_at,
                "detail": f.detail,
                "evidence_ids": f.evidence_ids,
            }
            for f in findings
        ],
    }


if __name__ == "__main__":
    from fallback.db import get_conn

    with get_conn() as conn:
        findings = run_shadow_report(conn)
        report = summarize(findings)
        print(f"Findings: {report['count']}  Total impact: ${report['total_impact_cents']/100:,.2f}")
        for f in report["findings"]:
            print(f"  {f['occurred_at']}  {f['txn_id']}  {'+'.join(f['rule_ids'])}  "
                  f"{'+'.join(f['reason_codes'])}  ${f['amount_cents']/100:,.2f}")
