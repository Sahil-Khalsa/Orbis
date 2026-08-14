"""Deterministic vendor name matching -- no model call.

Used both by the shadow report (backtesting historical raw vendor text) and
by the real extractor (which layers an LLM purpose-classification pass on
top of this same matcher for live requests).

Normalization is deliberately minimal: lowercase and whitespace-collapse
only. Do not strip legal suffixes (LLC, Inc) or expand abbreviations
(Svcs -> Services) -- either one pushes the ACME/Accme demo pair's score
above the 0.90 ambiguous-match ceiling and R3 stops deferring to the
reasoner. See tests/test_matcher.py.
"""
from __future__ import annotations

import re
import sqlite3

from rapidfuzz import fuzz

WHITESPACE_RE = re.compile(r"\s+")


def normalize(name: str) -> str:
    return WHITESPACE_RE.sub(" ", name.strip().lower())


def score(raw_name: str, candidate_name: str) -> float:
    """Match confidence in [0, 1]."""
    return fuzz.ratio(normalize(raw_name), normalize(candidate_name)) / 100.0


def match_vendor(conn: sqlite3.Connection, vendor_name_raw: str) -> tuple[str | None, float]:
    """Best (vendor_id, confidence) match against all known vendors' canonical name + aliases."""
    from fallback.db import loads

    best_id: str | None = None
    best_score = 0.0
    for row in conn.execute("SELECT id, canonical_name, aliases FROM vendors").fetchall():
        candidates = [row["canonical_name"], *loads(row["aliases"])]
        vendor_best = max(score(vendor_name_raw, c) for c in candidates)
        if vendor_best > best_score:
            best_score = vendor_best
            best_id = row["id"]
    return best_id, round(best_score, 4)
