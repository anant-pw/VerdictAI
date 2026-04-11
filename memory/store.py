"""
memory/store.py — Layer 4
Stores every test result to SQLite for trend detection and self-healing.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("SENTINEL_DB", "memory/sentinel.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create table if not exists."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TEXT    NOT NULL,
                suite_name    TEXT    NOT NULL,
                test_id       TEXT    NOT NULL,
                verdict       TEXT    NOT NULL,
                score         INTEGER,
                reason        TEXT,
                response      TEXT,
                latency_ms    INTEGER
            )
        """)
        conn.commit()


def save_result(suite_name: str, result: dict):
    """Append one test result to the DB."""
    judge = result.get("judge") or {}
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO results
                (run_timestamp, suite_name, test_id, verdict, score, reason, response, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            suite_name,
            result["id"],
            result["verdict"],
            judge.get("score"),
            judge.get("reason"),
            result.get("response", "")[:2000],  # cap at 2000 chars
            result.get("latency_ms"),
        ))
        conn.commit()


def get_history(test_id: str, limit: int = 10) -> list[dict]:
    """Return last N runs for a test_id."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM results
            WHERE test_id = ?
            ORDER BY run_timestamp DESC
            LIMIT ?
        """, (test_id, limit)).fetchall()
    return [dict(r) for r in rows]


def get_consecutive_failures(test_id: str, n: int = 3) -> int:
    """
    Return count of consecutive FAILs from latest run backwards.
    Used for self-healing trigger in Layer 5.
    """
    history = get_history(test_id, limit=n)
    count = 0
    for row in history:
        if row["verdict"] == "FAIL":
            count += 1
        else:
            break
    return count