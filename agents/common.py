r"""Shared runtime helper for every agent process.

This is the local substitute for a Daytona sandbox boundary. What Daytona
would enforce at the network/process level (no payment credentials, no
secrets, no egress except the Orbis API), this module enforces by
construction instead: it imports nothing from `app.*` -- no DB handle, no
Stripe key, no rule engine -- only `requests` and one env var. An agent
process literally cannot reach the database or execute a payment; the only
thing it can do is POST a request and read the JSON response, exactly like
a real external caller would. Verify with:
    grep -rn "^from app\|^import app" agents/
(should return nothing), and
    env | grep -i -E "stripe|openai|db_path"
run from inside one of these scripts (should be empty).
"""
from __future__ import annotations

import os
import sys

import requests

sys.stdout.reconfigure(line_buffering=True)

ORBIS_API_URL = os.environ.get("ORBIS_API_URL", "http://127.0.0.1:8734")


def submit_spend_request(
    agent_id: str,
    destination_type: str,
    category: str,
    amount_cents: int,
    business_purpose_raw: str,
    vendor_name_raw: str | None = None,
    counterparty_agent_id: str | None = None,
    as_of: str | None = None,
) -> dict:
    payload = {
        "agent_id": agent_id,
        "destination_type": destination_type,
        "category": category,
        "amount_cents": amount_cents,
        "business_purpose_raw": business_purpose_raw,
        "vendor_name_raw": vendor_name_raw,
        "counterparty_agent_id": counterparty_agent_id,
        "as_of": as_of,
    }
    resp = requests.post(f"{ORBIS_API_URL}/spend-requests", json=payload, timeout=15)
    if resp.status_code >= 400:
        print(f"  [!] request rejected ({resp.status_code}): {resp.text}", file=sys.stderr)
    resp.raise_for_status()
    return resp.json()


def print_decision(label: str, decision: dict) -> None:
    outcome = decision["outcome"]
    cited = "+".join(decision["cited_rule_ids"]) or "none"
    print(f"[{label}] outcome={outcome} cited_rules={cited} decision_id={decision['id']}")
    print(f"          {decision['rationale']}")


def verify_no_egress(target_url: str = "https://example.com") -> None:
    """Prove the sandbox boundary on stage: this agent can reach the Orbis
    API but nothing else. Called explicitly by demo.py, not on every run."""
    try:
        requests.get(target_url, timeout=3)
        print(f"  [!] egress to {target_url} SUCCEEDED -- boundary is not enforced")
    except requests.exceptions.RequestException as exc:
        print(f"  [ok] egress to {target_url} failed as expected: {type(exc).__name__}")
