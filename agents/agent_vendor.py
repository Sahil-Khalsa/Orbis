"""agent-vendor -- payee agent. Local substitute for the `agent-vendor`
Daytona sandbox. Does not submit spend requests; it *receives* them (D3,
architecture.md: "the exception is kind, not privilege"). This script's job
in the demo is just to narrate that it did the enrichment work and issued
an invoice -- agent-ops is the one who submits the resulting A2A payment
(see agents/agent_ops.py:a2a).
"""
from __future__ import annotations

import os
import sys

import requests

sys.stdout.reconfigure(line_buffering=True)

ORBIS_API_URL = os.environ.get("ORBIS_API_URL", "http://127.0.0.1:8734")
AGENT_ID = "agent_vendor"


def announce_invoice() -> None:
    resp = requests.get(f"{ORBIS_API_URL}/agents", timeout=15)
    resp.raise_for_status()
    me = next((a for a in resp.json() if a["id"] == AGENT_ID), None)
    if not me:
        print("[agent-vendor] not registered")
        return
    print(f"[agent-vendor] work complete: data enrichment for agent-ops")
    print(f"[agent-vendor] invoice issued -- $150.00, wallet {me['wallet_id']}")
    print("[agent-vendor] awaiting settlement via Orbis A2A transfer")


if __name__ == "__main__":
    announce_invoice()
