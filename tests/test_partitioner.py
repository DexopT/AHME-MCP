# tests/test_partitioner.py
import pytest
from ahme.partitioner import Partitioner

def test_single_chunk_for_short_text():
    p = Partitioner(chunk_size_tokens=100, overlap_tokens=10)
    chunks = p.partition("hello world")
    assert len(chunks) == 1
    assert chunks[0] == "hello world"

def test_overlap_is_applied():
    # Build text that spans > 1 chunk
    p = Partitioner(chunk_size_tokens=50, overlap_tokens=10)
    long_text = " ".join(["word"] * 200)
    chunks = p.partition(long_text)
    assert len(chunks) > 1
    # Overlap: end of chunk[0] should appear at start of chunk[1]
    last_tokens_chunk0 = chunks[0].split()[-5:]
    first_tokens_chunk1 = chunks[1].split()[:5]
    assert last_tokens_chunk0 == first_tokens_chunk1

def test_no_infinite_loop_when_overlap_near_chunk_size():
    # overlap must never be >= chunk_size
    p = Partitioner(chunk_size_tokens=20, overlap_tokens=19)
    text = " ".join(["word"] * 100)
    chunks = p.partition(text)
    assert len(chunks) >= 1  # must terminate

def test_empty_text_returns_empty():
    p = Partitioner(chunk_size_tokens=100, overlap_tokens=10)
    assert p.partition("") == []
