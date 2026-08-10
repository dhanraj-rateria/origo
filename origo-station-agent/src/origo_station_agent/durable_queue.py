"""A push that fails after a pass shouldn't lose the pass's results. SQLite, not
Postgres/Redis — this runs on the same box as everything else here, doesn't need
another service, and survives a process restart, which is the actual requirement."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class DurableQueue:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS pending_pushes (id INTEGER PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        self._conn.commit()

    def enqueue(self, events: list[dict]) -> None:
        import time
        self._conn.execute("INSERT INTO pending_pushes (payload, created_at) VALUES (?, ?)", (json.dumps(events), time.time()))
        self._conn.commit()

    def drain(self) -> list[tuple[int, list[dict]]]:
        rows = self._conn.execute("SELECT id, payload FROM pending_pushes ORDER BY id").fetchall()
        return [(rid, json.loads(payload)) for rid, payload in rows]

    def ack(self, row_id: int) -> None:
        self._conn.execute("DELETE FROM pending_pushes WHERE id = ?", (row_id,))
        self._conn.commit()