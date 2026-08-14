"""agent-ops -- well-behaved procurement agent. Local substitute for the
`agent-ops` Daytona sandbox. Subcommands map to demo beats in architecture.md
section 13.
"""
from __future__ import annotations

import argparse

from common import print_decision, submit_spend_request

AGENT_ID = "agent_ops"


def clean() -> None:
    """Beat 2: $200 API credits, auto-approves in ~2s."""
    d = submit_spend_request(
        AGENT_ID, "bank", "infrastructure", 20_000, "API credits top-up",
        vendor_name_raw="Hooli Cloud Platform",
    )
    print_decision("agent-ops clean", d)


def a2a(counterparty_agent_id: str = "agent_vendor") -> None:
    """Beat 3: agent-to-agent settlement for enrichment work, inside a signed warrant."""
    d = submit_spend_request(
        AGENT_ID, "agent", "infrastructure", 15_000,
        "settlement for data enrichment work performed by agent-vendor",
        counterparty_agent_id=counterparty_agent_id,
    )
    print_decision("agent-ops a2a", d)


def hero(as_of: str = "2026-07-13T10:05:00") -> None:
    """Beat 4: the block. $4,200 to a misspelled vendor that matches a real
    $4,080 payment 11 days earlier. `as_of` anchors evaluation to the seeded
    dataset's own timeline (see app/orchestrator.py's `now` parameter docs)
    so R4's 30-day lookback finds the seeded prior regardless of what day
    this script actually runs on."""
    d = submit_spend_request(
        AGENT_ID, "bank", "infrastructure", 420_000,
        "cloud hosting and infra services", vendor_name_raw="Accme Cloud Svcs", as_of=as_of,
    )
    print_decision("agent-ops hero-duplicate", d)


def route() -> None:
    """Beat 7: $9,000 routes for human sign-off, cites the warrant clause."""
    d = submit_spend_request(
        AGENT_ID, "bank", "infrastructure", 900_000, "annual infra contract renewal",
        vendor_name_raw="Contoso Data Systems",
    )
    print_decision("agent-ops route-for-approval", d)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("beat", choices=["clean", "a2a", "hero", "route"])
    args = parser.parse_args()
    {"clean": clean, "a2a": a2a, "hero": hero, "route": route}[args.beat]()
