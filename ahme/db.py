from __future__ import annotations
import sqlite3
import enum
from typing import Optional


class ChunkStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    INTEGER NOT NULL,
    text        TEXT NOT NULL,
    level       INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'pending',
    retries     INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
    updated_at  REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    INTEGER NOT NULL,
    level       INTEGER NOT NULL,
    summary     TEXT NOT NULL,
    created_at  REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);
"""


class QueueDB:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def enqueue(self, chunk_id: int, text: str, level: int = 1) -> None:
        self._conn.execute(
            "INSERT INTO chunks (chunk_id, text, level, status) VALUES (?, ?, ?, ?)",
            (chunk_id, text, level, ChunkStatus.PENDING),
        )
        self._conn.commit()

    def dequeue(self) -> Optional[sqlite3.Row]:
        row = self._conn.execute(
            "SELECT * FROM chunks WHERE status = ? ORDER BY id ASC LIMIT 1",
            (ChunkStatus.PENDING,),
        ).fetchone()
        if row is None:
            return None
        self._conn.execute(
            "UPDATE chunks SET status = ?, updated_at = unixepoch('now','subsec') WHERE id = ?",
            (ChunkStatus.PROCESSING, row["id"]),
        )
        self._conn.commit()
        return row

    def mark_done(self, row_id: int) -> None:
        self._conn.execute(
            "UPDATE chunks SET status = ?, updated_at = unixepoch('now','subsec') WHERE id = ?",
            (ChunkStatus.DONE, row_id),
        )
        self._conn.commit()

    def increment_retry(self, row_id: int, max_retries: int) -> None:
        row = self._conn.execute(
            "SELECT retries FROM chunks WHERE id = ?", (row_id,)
        ).fetchone()
        new_retries = row["retries"] + 1
        if new_retries >= max_retries:
            status = ChunkStatus.FAILED
        else:
            status = ChunkStatus.PENDING
        self._conn.execute(
            "UPDATE chunks SET status = ?, retries = ?, updated_at = unixepoch('now','subsec') WHERE id = ?",
            (status, new_retries, row_id),
        )
        self._conn.commit()

    def save_summary(self, chunk_id: int, level: int, summary: str) -> None:
        self._conn.execute(
            "INSERT INTO summaries (chunk_id, level, summary) VALUES (?, ?, ?)",
            (chunk_id, level, summary),
        )
        self._conn.commit()

    def get_summaries_by_level(self, level: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM summaries WHERE level = ? ORDER BY id ASC",
            (level,),
        ).fetchall()

    def pending_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM chunks WHERE status = ?",
            (ChunkStatus.PENDING,),
        ).fetchone()
        return row["cnt"]

    def clear_all(self) -> None:
        """Wipe all chunks and summaries. Used to reset context window after compression."""
        self._conn.executescript("DELETE FROM chunks; DELETE FROM summaries;")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
