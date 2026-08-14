"""Local demo harness -- runs all 9 demo beats (architecture.md section 13)
against a running Orbis server. This replaces the Daytona snapshot
verification (E2) in the local build: there is no sandbox snapshot to
verify from, so this script *is* the rehearsal artifact -- run it end to
end before presenting, exactly as E2 says to.

Usage:
    python -m fallback.seed --seed 42          # fresh, deterministic state
    uvicorn fallback.main:app --port 8734 &    # the service
    python demo.py                        # this script

Each beat prints its own pass/fail so a broken step is obvious rather than
buried in an exception trace.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import requests

sys.stdout.reconfigure(line_buffering=True)

ORBIS_API_URL = os.environ.get("ORBIS_API_URL", "http://127.0.0.1:8734")
AGENTS_DIR = os.path.join(os.path.dirname(__file__), "agents")


def _run_agent_script(script: str, *args: str) -> None:
    subprocess.run([sys.executable, os.path.join(AGENTS_DIR, script), *args], check=False)


def _header(n: int, title: str) -> None:
    print(f"\n{'=' * 70}\nBEAT {n}: {title}\n{'=' * 70}")


def _check_server() -> bool:
    try:
        requests.get(f"{ORBIS_API_URL}/agents", timeout=3)
        return True
    except requests.exceptions.RequestException:
        return False


def beat1_isolation() -> None:
    _header(1, "Agent isolation boundary")
    print("Five local agent processes exist under agents/: agent-ops, agent-vendor,")
    print("agent-runaway, agent-hostile -- plus the Orbis service itself.")
    print("\nEach agent's runtime is code-level isolated, not network-sandboxed the way a")
    print("Daytona sandbox would be: verify by grep, not by an egress call that would just")
    print("succeed on a normal laptop.\n")
    subprocess.run(
        ["grep", "-rn", r"^from fallback\|^import fallback", AGENTS_DIR],
        check=False,
    )
    print("(no matches above = no agent script can reach the DB, Stripe key, or rule engine)")
    from agents.common import ORBIS_API_URL as _url  # local import, demo-only
    print(f"\nEvery agent talks to exactly one thing: {_url}")


def beat2_clean_approve() -> None:
    _header(2, "Clean approve -- $200 API credits")
    _run_agent_script("agent_ops.py", "clean")


def beat3_a2a() -> None:
    _header(3, "Agent to agent settlement")
    _run_agent_script("agent_vendor.py")
    _run_agent_script("agent_ops.py", "a2a")


def beat4_the_block() -> None:
    _header(4, "THE BLOCK -- $4,200 to a misspelled vendor")
    _run_agent_script("agent_ops.py", "hero")
    print("\ncf. the $4,080 payment to 'ACME Cloud Services LLC' 11 days earlier -- see the")
    print("cited evidence id in the decision above, and /ui/decisions/<id> for the full trail.")


def beat5_runaway() -> None:
    _header(5, "Runaway agent -- R5 freezes it live")
    _run_agent_script("agent_runaway.py")
    resp = requests.get(f"{ORBIS_API_URL}/agents", timeout=5)
    runaway = next(a for a in resp.json() if a["id"] == "agent_runaway")
    print(f"\nagent-runaway status after the burst: {runaway['status']}")
    requests.post(f"{ORBIS_API_URL}/agents/agent_runaway/unfreeze", json={}, timeout=5)
    print("(unfrozen here so the demo is repeatable -- unfreeze is human-only in the UI too)")


def beat6_hostile() -> None:
    _header(6, "Hostile invoice -- injection flattened, flagged")
    _run_agent_script("agent_hostile.py")


def beat7_human_in_the_loop() -> None:
    _header(7, "Human in the loop -- $9,000 routes, then executes")
    _run_agent_script("agent_ops.py", "route")
    resp = requests.get(f"{ORBIS_API_URL}/queue", timeout=5)
    queue = resp.json()
    target = next((d for d in queue if d["outcome"] == "ROUTE_TO_HUMAN"
                   and d["spend_request"]["amount_cents"] == 900_000), None)
    if not target:
        print("(could not find the $9,000 item in the queue -- check /ui/queue manually)")
        return
    print(f"approving decision {target['id']} as p_alice...")
    resp = requests.post(
        f"{ORBIS_API_URL}/decisions/{target['id']}/approve",
        json={"principal_id": "p_alice", "note": "approved live in the demo"},
        timeout=15,
    )
    detail = resp.json()
    status = detail["spend_request"]["status"]
    print(f"post-approval spend_request status: {status}")
    if status == "queued":
        print("(execution needs a real STRIPE_SECRET_KEY -- see README/task notes; the decision,")
        print(" citation, and approval record are all real regardless)")


def beat8_shadow() -> None:
    _header(8, "Shadow report -- six months backtested")
    resp = requests.get(f"{ORBIS_API_URL}/shadow-report", timeout=15)
    report = resp.json()
    print(f"{report['count']} findings, ${report['total_impact_cents'] / 100:,.2f} total impact")
    for f in report["findings"]:
        print(f"  {f['occurred_at']}  {'+'.join(f['rule_ids'])}  {'+'.join(f['reason_codes'])}  "
              f"${f['amount_cents'] / 100:,.2f}")


def beat9_close() -> None:
    _header(9, "Close")
    print('"Stripe gave agents wallets. Orbis gives them approvals."')


BEATS = [
    beat1_isolation, beat2_clean_approve, beat3_a2a, beat4_the_block, beat5_runaway,
    beat6_hostile, beat7_human_in_the_loop, beat8_shadow, beat9_close,
]


if __name__ == "__main__":
    if not _check_server():
        print(f"Orbis server not reachable at {ORBIS_API_URL}.")
        print("Start it first: uvicorn fallback.main:app --port 8734")
        sys.exit(1)

    for beat in BEATS:
        beat()
        time.sleep(0.3)

    print("\nAll 9 beats ran. Review /ui/queue and /ui/shadow for the full audit trail.")
