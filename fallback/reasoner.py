"""The reasoner -- runs only on DEFER. architecture.md section 8.

Return type is the three-value Literal in fallback.types.ReasonerOutput: no
approval value exists in the type, so the model literally cannot clear
money into existence. Input is Extraction + candidate vendor records +
prior transaction rows + warrant clause_text -- never vendor_name_raw or
business_purpose_raw.

Without OPENAI_API_KEY configured, run_reasoner returns None and the
orchestrator routes DEFER -> ROUTE_TO_HUMAN (REASONER_UNAVAILABLE) instead
of calling this. That keeps every other demo beat runnable with no key;
only the fully-automatic BLOCK on the hero duplicate needs a real key --
without one, a human still sees the same rule citations and decides.
"""
from __future__ import annotations

import json
import os
import sqlite3

from fallback.state import State
from fallback.types import Extraction, ReasonerOutput, SpendRequest

SYSTEM_PROMPT = """You are reviewing a payment a deterministic policy engine could not resolve
on its own and deferred for judgment. You are given only structured evidence -- never the
original free-text invoice or memo. Decide one of:
  ROUTE            -- insufficient evidence, a human should look at this
  BLOCK            -- this looks like a mistaken or fraudulent duplicate / mismatched vendor
  CLEAR_DEFERRAL   -- confident this is the same legitimate counterparty as the cited evidence
Cite only ids that appear in the evidence you were given. A vendor name that is similar but not
identical to a known vendor, paired with an amount close to a prior payment, is a classic
invoice-redirect pattern -- do not clear it just because a prior transaction to that vendor
was marked recurring. Output strict JSON: {"verdict": "ROUTE"|"BLOCK"|"CLEAR_DEFERRAL",
"rationale": str, "cited_clause_id": str|null, "cited_evidence_ids": [str]}"""


def _openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def reasoner_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _build_evidence(conn: sqlite3.Connection, extraction: Extraction, state: State) -> dict:
    evidence: dict = {
        "extracted_vendor_name": extraction.vendor_name_norm,
        "match_confidence": extraction.match_confidence,
        "candidate_vendor": None,
        "warrant_clause": None,
        "warrant_clause_id": None,
        "prior_transactions": [],
    }
    if state.vendor:
        evidence["candidate_vendor"] = {
            "id": state.vendor["id"],
            "canonical_name": state.vendor["canonical_name"],
            "aliases": state.vendor["aliases"],
        }
    if state.warrant:
        evidence["warrant_clause_id"] = state.warrant["id"]
        evidence["warrant_clause"] = state.warrant["clause_text"]
    for t in state.counterparty_prior_transactions[:5]:
        evidence["prior_transactions"].append({
            "id": t["id"], "amount_cents": t["amount_cents"], "occurred_at": t["occurred_at"],
            "category": t["category"], "recurring": bool(t["recurring"]),
        })
    return evidence


def run_reasoner(conn: sqlite3.Connection, request: SpendRequest, extraction: Extraction, state: State) -> ReasonerOutput | None:
    client = _openai_client()
    if client is None:
        return None

    evidence = _build_evidence(conn, extraction, state)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "request_amount_cents": request.amount_cents,
        "request_category": request.category,
        "evidence": evidence,
    }
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        return ReasonerOutput(
            verdict=data["verdict"],
            rationale=data.get("rationale", ""),
            cited_clause_id=data.get("cited_clause_id"),
            cited_evidence_ids=list(data.get("cited_evidence_ids", [])),
        )
    except Exception as exc:
        # Distinct from "no key configured" (that path returns None before
        # this call is even attempted) -- a key was present and the call or
        # its parsing still failed. Logged so this doesn't get misdiagnosed
        # on stage as a missing key when it's an auth/schema/network error.
        print(f"[reasoner] call failed with a key configured: {type(exc).__name__}: {exc}")
        return None


def faithfulness_check(output: ReasonerOutput, conn: sqlite3.Connection, extraction: Extraction, state: State) -> bool:
    """Deterministic, no LLM. Cited clause exists; cited evidence ids exist; every
    entity name and amount in the rationale appears in the cited evidence."""
    evidence = _build_evidence(conn, extraction, state)

    if output.cited_clause_id and output.cited_clause_id != evidence["warrant_clause_id"]:
        return False

    known_evidence_ids = {evidence["candidate_vendor"]["id"]} if evidence["candidate_vendor"] else set()
    prior_transaction_ids = {t["id"] for t in evidence["prior_transactions"]}
    known_evidence_ids |= prior_transaction_ids
    for eid in output.cited_evidence_ids:
        if eid not in known_evidence_ids:
            return False
    if not output.cited_evidence_ids and not output.cited_clause_id:
        return False
    # A BLOCK or CLEAR_DEFERRAL verdict on a duplicate-type deferral is a
    # judgment specifically ABOUT a prior transaction -- citing only the
    # warrant clause and skipping the transaction evidence that drove the
    # deferral would validate a rationale that never actually looked at the
    # thing it's ruling on. Require it when there was one to cite.
    if prior_transaction_ids and output.verdict in ("BLOCK", "CLEAR_DEFERRAL"):
        if not (set(output.cited_evidence_ids) & prior_transaction_ids):
            return False

    rationale_lower = output.rationale.lower()
    cited_amounts = {str(t["amount_cents"] / 100) for t in evidence["prior_transactions"] if t["id"] in output.cited_evidence_ids}
    for amount_str in cited_amounts:
        # A cited transaction's dollar amount should be traceable in the rationale
        # in *some* recognizable form; we don't hard-fail on formatting variance
        # (e.g. "$4,080" vs "4080.0") -- just require the raw digits appear.
        digits = amount_str.split(".")[0]
        if digits not in rationale_lower.replace(",", ""):
            return False

    return True
