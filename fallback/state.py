"""Pre-loaded state for rule evaluation.

Rules are pure functions: check(request, extraction, state) -> RuleResult.
All I/O -- DB queries, aggregate computation -- happens here in load_state,
so rules themselves never touch the database or the clock directly. That's
what makes them replayable: the shadow report calls load_state with a
historical `now` and gets point-in-time-correct state back.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fallback.db import loads
from fallback.types import DestinationType, SpendRequest


@dataclass
class State:
    now: datetime
    warrant: dict | None
    budget: dict | None
    vendor: dict | None
    payee_agent: dict | None
    # Prior transactions to the same resolved counterparty, any category,
    # any age -- R4 applies the 30-day/5%/same-category filter itself.
    counterparty_prior_transactions: list[dict] = field(default_factory=list)
    agent_request_count_10min: int = 0
    agent_trailing_1h_spend_cents: int = 0
    agent_baseline_hourly_cents: float = 0.0


def _parse(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


def load_state(
    conn: sqlite3.Connection,
    request: SpendRequest,
    vendor_id_match: str | None,
    match_confidence: float,
    now: datetime,
    historical: bool = False,
) -> State:
    """
    historical=True reconstructs point-in-time committed/spent totals from
    transaction history instead of trusting the live running counters --
    required for the shadow report, where "now" is in the past and the
    counters on warrants/budgets reflect the *final* state, not the state
    as of that historical request.
    """
    warrant = None
    if request.warrant_id:
        row = conn.execute("SELECT * FROM warrants WHERE id = ?", (request.warrant_id,)).fetchone()
        if row:
            warrant = dict(row)
            warrant["categories"] = loads(warrant["categories"])
            warrant["vendor_scope"] = loads(warrant["vendor_scope"])
            warrant["counterparty_scope"] = loads(warrant["counterparty_scope"])
            if historical:
                spent_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(t.amount_cents), 0) AS total
                    FROM transactions t JOIN spend_requests sr ON t.spend_request_id = sr.id
                    WHERE sr.warrant_id = ? AND t.occurred_at < ?
                    """,
                    (request.warrant_id, now.isoformat()),
                ).fetchone()
                warrant["spent_total_cents"] = spent_row["total"] if spent_row else 0

    budget = None
    budget_row = conn.execute(
        "SELECT * FROM budgets WHERE category = ? AND period_start <= ? AND period_end >= ?",
        (request.category, now.date().isoformat(), now.date().isoformat()),
    ).fetchone()
    if budget_row:
        budget = dict(budget_row)
        if historical:
            committed_row = conn.execute(
                """
                SELECT COALESCE(SUM(amount_cents), 0) AS total FROM transactions
                WHERE category = ? AND occurred_at >= ? AND occurred_at < ?
                """,
                (request.category, budget["period_start"], now.isoformat()),
            ).fetchone()
            budget["committed_cents"] = committed_row["total"] if committed_row else 0

    vendor = None
    if vendor_id_match:
        vendor_row = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id_match,)).fetchone()
        if vendor_row:
            vendor = dict(vendor_row)
            vendor["aliases"] = loads(vendor["aliases"])

    payee_agent = None
    if request.destination_type == DestinationType.agent and request.counterparty_agent_id:
        agent_row = conn.execute(
            "SELECT * FROM agents WHERE id = ? AND kind = 'payee'", (request.counterparty_agent_id,)
        ).fetchone()
        if agent_row:
            payee_agent = dict(agent_row)

    counterparty_prior_transactions: list[dict] = []
    if request.destination_type == DestinationType.bank and vendor_id_match:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE vendor_id = ? AND occurred_at < ? ORDER BY occurred_at DESC",
            (vendor_id_match, now.isoformat()),
        ).fetchall()
        counterparty_prior_transactions = [dict(r) for r in rows]
    elif request.destination_type == DestinationType.agent and request.counterparty_agent_id:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE counterparty_agent_id = ? AND occurred_at < ? ORDER BY occurred_at DESC",
            (request.counterparty_agent_id, now.isoformat()),
        ).fetchall()
        counterparty_prior_transactions = [dict(r) for r in rows]

    ten_min_ago = (now - timedelta(minutes=10)).isoformat()
    count_row = conn.execute(
        "SELECT COUNT(*) AS c FROM spend_requests WHERE agent_id = ? AND submitted_at >= ? AND submitted_at < ?",
        (request.agent_id, ten_min_ago, now.isoformat()),
    ).fetchone()
    agent_request_count_10min = count_row["c"] if count_row else 0

    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    trailing_1h_row = conn.execute(
        """
        SELECT COALESCE(SUM(t.amount_cents), 0) AS total
        FROM transactions t JOIN spend_requests sr ON t.spend_request_id = sr.id
        WHERE sr.agent_id = ? AND t.occurred_at >= ? AND t.occurred_at < ?
        """,
        (request.agent_id, one_hour_ago, now.isoformat()),
    ).fetchone()
    agent_trailing_1h_spend_cents = trailing_1h_row["total"] if trailing_1h_row else 0

    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    trailing_30d_row = conn.execute(
        """
        SELECT COALESCE(SUM(t.amount_cents), 0) AS total
        FROM transactions t JOIN spend_requests sr ON t.spend_request_id = sr.id
        WHERE sr.agent_id = ? AND t.occurred_at >= ? AND t.occurred_at < ?
        """,
        (request.agent_id, thirty_days_ago, now.isoformat()),
    ).fetchone()
    trailing_30d_total = trailing_30d_row["total"] if trailing_30d_row else 0

    # Dividing by a fixed 30*24 hours understates the baseline -- and makes
    # it trivial to exceed -- for an agent with less than 30 days of actual
    # history. Divide by the actual elapsed history instead (capped at 30
    # days), and require a minimum warm-up before trusting it at all; a
    # cold-start agent gets baseline=0, which R5's spend-ratio check
    # (guarded by MIN_BASELINE_CENTS_FOR_CHECK) then simply skips.
    MIN_WARMUP_DAYS = 30
    earliest_row = conn.execute(
        "SELECT MIN(submitted_at) AS earliest FROM spend_requests WHERE agent_id = ?",
        (request.agent_id,),
    ).fetchone()
    earliest = earliest_row["earliest"] if earliest_row else None
    history_days = (now - _parse(earliest)).days if earliest else 0
    if history_days >= MIN_WARMUP_DAYS:
        elapsed_hours = min(history_days, 30) * 24
        agent_baseline_hourly_cents = trailing_30d_total / elapsed_hours
    else:
        agent_baseline_hourly_cents = 0.0

    return State(
        now=now,
        warrant=warrant,
        budget=budget,
        vendor=vendor,
        payee_agent=payee_agent,
        counterparty_prior_transactions=counterparty_prior_transactions,
        agent_request_count_10min=agent_request_count_10min,
        agent_trailing_1h_spend_cents=agent_trailing_1h_spend_cents,
        agent_baseline_hourly_cents=agent_baseline_hourly_cents,
    )
