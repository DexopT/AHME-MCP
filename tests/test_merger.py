# tests/test_merger.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ahme.compressor import SummaryResult
from ahme.merger import Merger

def _make_result(chunk_id: int) -> SummaryResult:
    return SummaryResult(
        chunk_id=chunk_id,
        level=1,
        key_facts=[f"fact from chunk {chunk_id}"],
        decisions=[f"decision {chunk_id}"],
        open_questions=[],
        entities=[f"Entity{chunk_id}"],
    )

@pytest.mark.asyncio
async def test_merge_combines_summaries():
    summaries = [_make_result(i) for i in range(1, 4)]
    merger = Merger(batch_size=5)

    mock_compressed = SummaryResult(
        chunk_id=0, level=2,
        key_facts=["merged fact"],
        decisions=["merged decision"],
        open_questions=[],
        entities=["MergedEntity"],
    )
    mock_compressor = MagicMock()
    mock_compressor.compress = AsyncMock(return_value=mock_compressed)

    result = await merger.merge(summaries, level=2, compressor=mock_compressor)
    assert result.level == 2
    assert result.key_facts == ["merged fact"]

@pytest.mark.asyncio
async def test_merge_batches_large_inputs():
    summaries = [_make_result(i) for i in range(1, 12)]
    merger = Merger(batch_size=5)

    mock_compressor = MagicMock()
    call_count = 0

    async def fake_compress(chunk_id, text, level):
        nonlocal call_count
        call_count += 1
        return SummaryResult(chunk_id=chunk_id, level=level, key_facts=["f"], decisions=[], open_questions=[], entities=[])

    mock_compressor.compress = fake_compress
    await merger.merge(summaries, level=2, compressor=mock_compressor)
    # 11 summaries / batch_size 5 → 3 batches (5+5+1) → 3 calls minimum
    assert call_count >= 3
