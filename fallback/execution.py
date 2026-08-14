"""Stripe test-mode execution + ledger write-back. architecture.md section 9.

idempotency_key = sha256(spend_request_id). Never write the ledger before
confirmation; never execute twice on retry; retry the same key once on
failure, then dead-letter to the human queue.

The requesting agent never touches this path -- it runs only from the
orchestrator, inside the Orbis service, after a decision is already
AUTO_APPROVE.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime

from fallback.db import new_id
from fallback.types import Decision, DestinationType, SpendRequest


def assert_stripe_test_mode() -> None:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key.startswith("sk_test_"):
        raise RuntimeError(
            "STRIPE_SECRET_KEY must start with 'sk_test_' -- refusing to boot with a live key."
        )


def _idempotency_key(spend_request_id: str) -> str:
    return hashlib.sha256(spend_request_id.encode()).hexdigest()


def _create_payment_intent(request: SpendRequest, idempotency_key: str) -> str:
    from stripe import StripeClient

    client = StripeClient(os.environ.get("STRIPE_SECRET_KEY", ""))
    intent = client.payment_intents.create(
        params={
            "amount": request.amount_cents,
            "currency": "usd",
            "description": f"Orbis spend request {request.id}",
            "confirm": False,
        },
        options={"idempotency_key": idempotency_key},
    )
    return intent.id


def _transfer_to_agent_wallet(conn: sqlite3.Connection, request: SpendRequest, idempotency_key: str) -> str:
    # No real money rail for agent-to-agent settlement in this build -- the
    # ledger entry itself *is* the settlement record. wallet_id is carried
    # for the UI to show "into which wallet."
    row = conn.execute(
        "SELECT wallet_id FROM agents WHERE id = ?", (request.counterparty_agent_id,)
    ).fetchone()
    wallet_id = row["wallet_id"] if row else "unknown_wallet"
    return f"a2a_{idempotency_key[:16]}_{wallet_id}"


def execute_decision(conn: sqlite3.Connection, request: SpendRequest, decision: Decision, now: datetime | None = None) -> None:
    now = now or datetime.now()
    idempotency_key = _idempotency_key(request.id)

    existing = conn.execute(
        "SELECT id FROM transactions WHERE spend_request_id = ?", (request.id,)
    ).fetchone()
    if existing:
        return  # already executed -- idempotent no-op, never double-execute on retry

    stripe_ref = None
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            if request.destination_type == DestinationType.bank:
                stripe_ref = _create_payment_intent(request, idempotency_key)
            else:
                stripe_ref = _transfer_to_agent_wallet(conn, request, idempotency_key)
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001 -- Stripe/network failures are expected here
            last_error = exc
            continue

    if last_error is not None:
        # Dead-letter to the human queue after one retry -- never leave a
        # decided-but-unexecuted request silently stuck.
        conn.execute(
            "UPDATE spend_requests SET status = 'queued' WHERE id = ?", (request.id,)
        )
        conn.commit()
        return

    txn_id = new_id("t")
    conn.execute(
        "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (txn_id, request.destination_type.value,
         _resolved_vendor_id(conn, request), request.counterparty_agent_id,
         request.category, request.amount_cents, now.isoformat(),
         # Not request.business_purpose_raw -- invariant 4: only the extractor
         # reads raw text. The ledger description is derived from typed
         # fields only, same as everything downstream of extraction.
         f"{request.category} payment", 0, stripe_ref, request.id),
    )

    conn.execute(
        "UPDATE budgets SET committed_cents = committed_cents + ? "
        "WHERE category = ? AND period_start <= ? AND period_end >= ?",
        (request.amount_cents, request.category, now.date().isoformat(), now.date().isoformat()),
    )
    if request.warrant_id:
        conn.execute(
            "UPDATE warrants SET spent_total_cents = spent_total_cents + ? WHERE id = ?",
            (request.amount_cents, request.warrant_id),
        )

    conn.execute("UPDATE spend_requests SET status = 'executed' WHERE id = ?", (request.id,))
    conn.commit()


def _resolved_vendor_id(conn: sqlite3.Connection, request: SpendRequest) -> str | None:
    if request.destination_type != DestinationType.bank or not request.vendor_name_raw:
        return None
    from fallback.matcher import match_vendor

    vendor_id, confidence = match_vendor(conn, request.vendor_name_raw)
    return vendor_id if confidence >= 0.90 else None
