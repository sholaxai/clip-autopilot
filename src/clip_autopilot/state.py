"""SQLite-backed state so reruns are idempotent (no double posting)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .models import Network, ScheduledPost

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    clip_hash   TEXT NOT NULL,
    network     TEXT NOT NULL,
    publish_at  TEXT NOT NULL,
    external_id TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (clip_hash, network)
);
CREATE INDEX IF NOT EXISTS idx_posts_publish ON posts (network, publish_at);
"""


class StateStore:
    def __init__(self, path: Path | str = ":memory:"):
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def already_posted(self, clip_hash: str, network: Network) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM posts WHERE clip_hash = ? AND network = ?", (clip_hash, network.value)
        ).fetchone()
        return row is not None

    def record(self, clip_hash: str, post: ScheduledPost) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO posts (clip_hash, network, publish_at, external_id) "
                "VALUES (?, ?, ?, ?)",
                (clip_hash, post.network.value, post.publish_at.isoformat(), post.external_id),
            )

    def booked_slots(self, network: Network, since: datetime) -> list[datetime]:
        rows = self._conn.execute(
            "SELECT publish_at FROM posts WHERE network = ? AND publish_at >= ? ORDER BY 1",
            (network.value, since.isoformat()),
        ).fetchall()
        return [datetime.fromisoformat(r[0]) for r in rows]

    def close(self) -> None:
        self._conn.close()
