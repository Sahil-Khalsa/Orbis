"""agent-runaway -- bursts requests. Local substitute for the `agent-runaway`
Daytona sandbox. Beat 5, D4: fires 9 requests as fast as the API will take
them; R5 should freeze the agent partway through and the trailing requests
should come back rejected with 423 (frozen) rather than adjudicated.
"""
from __future__ import annotations

import time

from common import print_decision, submit_spend_request

AGENT_ID = "agent_runaway"

VENDORS = [
    "ACME Cloud Services LLC", "Contoso Data Systems", "Cyberdyne Infra Systems",
    "Hooli Cloud Platform", "Titan Hardware Solutions", "Massive Dynamic Labs",
    "Stark Component Works", "Wonka Industrial Supply", "Aperture Research Labs",
]


def burst() -> None:
    print("[agent-runaway] bursting 9 requests...")
    for i, vendor in enumerate(VENDORS):
        try:
            d = submit_spend_request(
                AGENT_ID, "bank", "infrastructure", 1_000 + i * 137,
                "burst infra top-up", vendor_name_raw=vendor,
            )
            print_decision(f"agent-runaway #{i + 1}", d)
        except Exception as exc:
            print(f"[agent-runaway #{i + 1}] rejected: {exc}")
        time.sleep(0.3)


if __name__ == "__main__":
    burst()
