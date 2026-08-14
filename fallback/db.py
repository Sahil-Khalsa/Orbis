"""SQLite connection, schema init, and JSON (de)serialization helpers.

Every table with a list-valued column stores it as a JSON text blob --
SQLite has no array type. The helpers below keep that encode/decode in one
place instead of scattered across callers.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = os.environ.get("ORBIS_DB_PATH", str(Path(__file__).resolve().parent.parent / "orbis.db"))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def new_id(prefix: str = "") -> str:
    token = uuid.uuid4().hex[:12]
    return f"{prefix}_{token}" if prefix else token


def dumps(value: Any) -> str:
    return json.dumps(value if value is not None else [])


def loads(value: str | None) -> Any:
    if not value:
        return []
    return json.loads(value)


def connect(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


def reset_db(db_path: str | None = None) -> None:
    path = db_path or DB_PATH
    if os.path.exists(path):
        os.remove(path)
    conn = connect(path)
    try:
        init_db(conn)
    finally:
        conn.close()


@contextmanager
def get_conn(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)
