from fallback.db import connect
from fallback.seed import build
from fallback.shadow import run_shadow_report, summarize

EXPECTED_RULE_SIGNATURES = {
    ("R1",), ("R2", "R6"), ("R3", "R4"), ("R3", "R6"), ("R4",), ("R5",), ("R6",),
}


def test_shadow_report_finds_exactly_seven_violations(tmp_path):
    db_path = str(tmp_path / "orbis_test.db")
    build(seed=42, db_path=db_path)
    conn = connect(db_path)
    try:
        findings = run_shadow_report(conn)
    finally:
        conn.close()

    report = summarize(findings)
    assert report["count"] == 7, (
        f"expected exactly 7 findings, got {report['count']}: {report['findings']}"
    )
    signatures = {tuple(f["rule_ids"]) for f in report["findings"]}
    assert signatures == EXPECTED_RULE_SIGNATURES
