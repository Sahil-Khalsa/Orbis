"""Orbis API + UI. B2/B6/D5.

Boots only with a Stripe test-mode key (invariant 2 -- refuse to boot on a
live key). The money path itself doesn't require OPENAI_API_KEY; without
one, DEFER cases route to a human instead of calling a model (see
fallback.orchestrator).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

load_dotenv()

from fallback.db import connect, dumps, get_conn, loads, new_id
from fallback.execution import assert_stripe_test_mode, execute_decision
from fallback.orchestrator import adjudicate
from fallback.shadow import run_shadow_report, summarize
from fallback.types import Decision, DecidedBy, DestinationType, Outcome, SpendRequest, SpendRequestStatus

assert_stripe_test_mode()

app = FastAPI(title="Orbis")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def db() -> sqlite3.Connection:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


class SpendRequestIn(BaseModel):
    agent_id: str
    destination_type: DestinationType
    category: str
    amount_cents: int
    business_purpose_raw: str
    vendor_name_raw: Optional[str] = None
    counterparty_agent_id: Optional[str] = None
    warrant_id: Optional[str] = None
    as_of: Optional[str] = None  # demo-only: evaluate as of this timestamp instead of real now


class ApprovalIn(BaseModel):
    principal_id: str
    note: str = ""


def _resolve_warrant(conn: sqlite3.Connection, agent_id: str, category: str) -> Optional[str]:
    row = conn.execute(
        "SELECT id FROM warrants WHERE agent_id = ? AND status = 'active' "
        "AND categories LIKE ? ORDER BY valid_from DESC",
        (agent_id, f'%"{category}"%'),
    ).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        "SELECT id FROM warrants WHERE agent_id = ? AND status = 'active' AND categories LIKE '%\"*\"%'",
        (agent_id,),
    ).fetchone()
    return row["id"] if row else None


def _decision_dict(conn: sqlite3.Connection, decision_id: str) -> dict:
    d = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
    if not d:
        raise HTTPException(404, "decision not found")
    rule_results = conn.execute(
        "SELECT * FROM rule_results WHERE decision_id = ? ORDER BY rule_id", (decision_id,)
    ).fetchall()
    sr = conn.execute("SELECT * FROM spend_requests WHERE id = ?", (d["spend_request_id"],)).fetchone()
    warrant = None
    if d["cited_warrant_id"]:
        wrow = conn.execute("SELECT * FROM warrants WHERE id = ?", (d["cited_warrant_id"],)).fetchone()
        warrant = dict(wrow) if wrow else None
    ex = conn.execute(
        "SELECT * FROM extractions WHERE spend_request_id = ? ORDER BY id DESC LIMIT 1",
        (d["spend_request_id"],),
    ).fetchone()
    extraction = None
    if ex:
        extraction = {
            "vendor_name_norm": ex["vendor_name_norm"], "vendor_id_match": ex["vendor_id_match"],
            "match_confidence": ex["match_confidence"], "purpose_class": ex["purpose_class"],
            "injection_flags": loads(ex["injection_flags"]),
        }
    return {
        "id": d["id"],
        "spend_request_id": d["spend_request_id"],
        "outcome": d["outcome"],
        "decided_at": d["decided_at"],
        "decided_by": d["decided_by"],
        "rationale": d["rationale"],
        "cited_rule_ids": loads(d["cited_rule_ids"]),
        "cited_warrant_id": d["cited_warrant_id"],
        "warrant_clause": warrant["clause_text"] if warrant else None,
        "rule_results": [
            {"rule_id": r["rule_id"], "outcome": r["outcome"], "reason_code": r["reason_code"],
             "detail": r["detail"], "evidence_ids": loads(r["evidence_ids"])}
            for r in rule_results
        ],
        "spend_request": dict(sr) if sr else None,
        "extraction": extraction,
    }


@app.post("/spend-requests")
def submit_spend_request(payload: SpendRequestIn, conn: sqlite3.Connection = Depends(db)) -> dict:
    if payload.destination_type == DestinationType.bank and not payload.vendor_name_raw:
        raise HTTPException(400, "vendor_name_raw is required for destination_type=bank")
    if payload.destination_type == DestinationType.agent and not payload.counterparty_agent_id:
        raise HTTPException(400, "counterparty_agent_id is required for destination_type=agent")

    agent = conn.execute("SELECT * FROM agents WHERE id = ?", (payload.agent_id,)).fetchone()
    if not agent:
        raise HTTPException(404, f"unknown agent_id {payload.agent_id}")
    if agent["status"] == "frozen":
        raise HTTPException(423, f"agent {payload.agent_id} is frozen pending human review")

    now = datetime.fromisoformat(payload.as_of) if payload.as_of else datetime.now()
    warrant_id = payload.warrant_id or _resolve_warrant(conn, payload.agent_id, payload.category)

    request = SpendRequest(
        id=new_id("sr"), agent_id=payload.agent_id, warrant_id=warrant_id,
        destination_type=payload.destination_type, vendor_name_raw=payload.vendor_name_raw,
        counterparty_agent_id=payload.counterparty_agent_id, category=payload.category,
        amount_cents=payload.amount_cents, business_purpose_raw=payload.business_purpose_raw,
        submitted_at=now.isoformat(), status=SpendRequestStatus.submitted,
    )
    conn.execute(
        "INSERT INTO spend_requests VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (request.id, request.agent_id, request.warrant_id, request.destination_type.value,
         request.vendor_name_raw, request.counterparty_agent_id, request.category,
         request.amount_cents, request.business_purpose_raw, request.submitted_at, request.status.value),
    )
    conn.commit()

    decision = adjudicate(conn, request, now=now)
    return _decision_dict(conn, decision.id)


@app.get("/spend-requests/{spend_request_id}")
def get_spend_request(spend_request_id: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    d = conn.execute(
        "SELECT id FROM decisions WHERE spend_request_id = ? ORDER BY decided_at DESC LIMIT 1",
        (spend_request_id,),
    ).fetchone()
    if not d:
        raise HTTPException(404, "no decision for this spend request")
    return _decision_dict(conn, d["id"])


@app.get("/queue")
def get_queue(conn: sqlite3.Connection = Depends(db)) -> list[dict]:
    rows = conn.execute(
        "SELECT sr.id AS spend_request_id FROM spend_requests sr WHERE sr.status = 'queued' "
        "ORDER BY sr.submitted_at ASC"
    ).fetchall()
    out = []
    for row in rows:
        d = conn.execute(
            "SELECT id FROM decisions WHERE spend_request_id = ? ORDER BY decided_at DESC LIMIT 1",
            (row["spend_request_id"],),
        ).fetchone()
        if d:
            out.append(_decision_dict(conn, d["id"]))
    return out


@app.post("/decisions/{decision_id}/approve")
def approve_decision(decision_id: str, payload: ApprovalIn, conn: sqlite3.Connection = Depends(db)) -> dict:
    detail = _decision_dict(conn, decision_id)
    if detail["spend_request"]["status"] != "queued":
        raise HTTPException(
            409, f"decision {decision_id} is not awaiting approval "
                 f"(status={detail['spend_request']['status']}, outcome={detail['outcome']})"
        )
    conn.execute(
        "INSERT INTO approvals VALUES (?,?,?,?,?,?)",
        (new_id("ap"), decision_id, payload.principal_id, "approve", payload.note, datetime.now().isoformat()),
    )
    conn.commit()
    sr_row = detail["spend_request"]
    request = SpendRequest(
        id=sr_row["id"], agent_id=sr_row["agent_id"], warrant_id=sr_row["warrant_id"],
        destination_type=DestinationType(sr_row["destination_type"]), vendor_name_raw=sr_row["vendor_name_raw"],
        counterparty_agent_id=sr_row["counterparty_agent_id"], category=sr_row["category"],
        amount_cents=sr_row["amount_cents"], business_purpose_raw=sr_row["business_purpose_raw"],
        submitted_at=sr_row["submitted_at"], status=sr_row["status"],
    )
    decision = Decision(
        id=detail["id"], spend_request_id=detail["spend_request_id"], outcome=detail["outcome"],
        decided_at=detail["decided_at"], decided_by=DecidedBy(detail["decided_by"]),
        rationale=detail["rationale"], cited_rule_ids=detail["cited_rule_ids"],
        cited_warrant_id=detail["cited_warrant_id"],
    )
    execute_decision(conn, request, decision, datetime.now())
    return _decision_dict(conn, decision_id)


@app.post("/decisions/{decision_id}/deny")
def deny_decision(decision_id: str, payload: ApprovalIn, conn: sqlite3.Connection = Depends(db)) -> dict:
    detail = _decision_dict(conn, decision_id)
    conn.execute(
        "INSERT INTO approvals VALUES (?,?,?,?,?,?)",
        (new_id("ap"), decision_id, payload.principal_id, "deny", payload.note, datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE spend_requests SET status = 'decided' WHERE id = ?", (detail["spend_request_id"],)
    )
    conn.commit()
    return _decision_dict(conn, decision_id)


@app.get("/agents")
def list_agents(conn: sqlite3.Connection = Depends(db)) -> list[dict]:
    rows = conn.execute("SELECT * FROM agents").fetchall()
    return [dict(r) for r in rows]


@app.post("/agents/{agent_id}/unfreeze")
def unfreeze_agent(agent_id: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    conn.execute("UPDATE agents SET status = 'active' WHERE id = ?", (agent_id,))
    conn.commit()
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not row:
        raise HTTPException(404, "unknown agent")
    return dict(row)


@app.get("/shadow-report")
def shadow_report(conn: sqlite3.Connection = Depends(db)) -> dict:
    return summarize(run_shadow_report(conn))


# --- UI (server-rendered) --------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def ui_home(request: Request, conn: sqlite3.Connection = Depends(db)):
    agents = [dict(r) for r in conn.execute("SELECT * FROM agents").fetchall()]
    return templates.TemplateResponse(request, "home.html", {"agents": agents})


@app.get("/ui/queue", response_class=HTMLResponse)
def ui_queue(request: Request, conn: sqlite3.Connection = Depends(db)):
    items = get_queue(conn)
    return templates.TemplateResponse(request, "queue.html", {"items": items})


@app.get("/ui/decisions/{decision_id}", response_class=HTMLResponse)
def ui_decision(decision_id: str, request: Request, conn: sqlite3.Connection = Depends(db)):
    detail = _decision_dict(conn, decision_id)
    return templates.TemplateResponse(request, "decision.html", {"d": detail})


@app.get("/ui/shadow", response_class=HTMLResponse)
def ui_shadow(request: Request, conn: sqlite3.Connection = Depends(db)):
    report = summarize(run_shadow_report(conn))
    return templates.TemplateResponse(request, "shadow.html", {"report": report})
