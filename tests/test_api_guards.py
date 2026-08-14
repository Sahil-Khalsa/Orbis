import os

from fastapi.testclient import TestClient

from fallback.db import connect, dumps, reset_db

os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")


def _make_client(tmp_path):
    db_path = str(tmp_path / "orbis_test.db")
    reset_db(db_path)

    conn = connect(db_path)
    conn.execute("INSERT INTO principals VALUES (?,?,?,?)", ("p1", "Alice", "a@x.com", "finance_lead"))
    conn.execute(
        "INSERT INTO agents VALUES (?,?,?,?,?,?,?)",
        ("a1", "agent-ops", "p1", "local:agent-ops", "spender", None, "active"),
    )
    conn.execute(
        "INSERT INTO warrants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("w1", "a1", "p1", dumps(["infrastructure"]), 100, 100_000_000, 0,
         dumps(["*"]), dumps(["*"]), "2020-01-01", "2030-01-01", "active", "clause"),
    )
    conn.execute(
        "INSERT INTO vendors VALUES (?,?,?,?,?)",
        ("v1", "ACME Cloud Services LLC", dumps([]), "approved", "2020-01-01"),
    )
    conn.commit()
    conn.close()

    import fallback.main as main_module

    def override_db():
        c = connect(db_path)
        try:
            yield c
        finally:
            c.close()

    main_module.app.dependency_overrides[main_module.db] = override_db
    return TestClient(main_module.app)


def test_cannot_approve_a_block_decision(tmp_path):
    """R1's per-txn ceiling is 100c; a 500c request BLOCKs outright. Approving
    a BLOCK must be rejected -- money never moves outside the routed path."""
    client = _make_client(tmp_path)
    resp = client.post("/spend-requests", json={
        "agent_id": "a1", "destination_type": "bank", "vendor_name_raw": "ACME Cloud Services LLC",
        "category": "infrastructure", "amount_cents": 500, "business_purpose_raw": "test",
    })
    assert resp.status_code == 200
    decision = resp.json()
    assert decision["outcome"] == "BLOCK"
    assert decision["spend_request"]["status"] == "decided"

    approve = client.post(f"/decisions/{decision['id']}/approve", json={"principal_id": "p1"})
    assert approve.status_code == 409
