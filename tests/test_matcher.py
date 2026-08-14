from fallback.matcher import score

ACME_CANONICAL = "ACME Cloud Services LLC"
ACME_MISSPELLED = "Accme Cloud Svcs"


def test_hero_demo_pair_lands_in_ambiguous_band():
    """R3 defers to the reasoner only if this stays in [0.65, 0.90)."""
    s = score(ACME_MISSPELLED, ACME_CANONICAL)
    assert 0.65 <= s < 0.90, f"score {s} left the ambiguous band -- R3 would resolve this deterministically"


def test_identical_name_matches_confidently():
    assert score(ACME_CANONICAL, ACME_CANONICAL) >= 0.90


def test_unrelated_name_scores_low():
    assert score("Greenfield Legal Partners", ACME_CANONICAL) < 0.65
