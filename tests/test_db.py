# tests/test_db.py
import pytest
from ahme.db import QueueDB, ChunkStatus

def test_enqueue_and_dequeue(tmp_path):
    db = QueueDB(str(tmp_path / "test.db"))
    db.enqueue(chunk_id=1, text="hello world", level=1)
    row = db.dequeue()
    assert row is not None
    assert row["chunk_id"] == 1
    assert row["text"] == "hello world"
    assert row["level"] == 1

def test_dequeue_returns_none_when_empty(tmp_path):
    db = QueueDB(str(tmp_path / "test.db"))
    assert db.dequeue() is None

def test_mark_done(tmp_path):
    db = QueueDB(str(tmp_path / "test.db"))
    db.enqueue(chunk_id=1, text="hello", level=1)
    row = db.dequeue()
    db.mark_done(row["id"])
    assert db.dequeue() is None

def test_increment_retry_and_fail(tmp_path):
    db = QueueDB(str(tmp_path / "test.db"))
    db.enqueue(chunk_id=1, text="hello", level=1)
    row = db.dequeue()
    db.increment_retry(row["id"], max_retries=1)
    # After exceeding max_retries it should be marked failed, not re-queued
    assert db.dequeue() is None

def test_pending_count(tmp_path):
    db = QueueDB(str(tmp_path / "test.db"))
    db.enqueue(chunk_id=1, text="a", level=1)
    db.enqueue(chunk_id=2, text="b", level=1)
    assert db.pending_count() == 2
