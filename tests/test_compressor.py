# tests/test_compressor.py
import pytest
import json
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from ahme.compressor import Compressor, SummaryResult

MOCK_RESPONSE = json.dumps({
    "key_facts": ["User asked about Python.", "Agent explained async."],
    "decisions": ["Use asyncio for concurrency."],
    "open_questions": [],
    "entities": ["Python", "asyncio"]
})

@pytest.mark.asyncio
async def test_compress_returns_summary_result():
    comp = Compressor(base_url="http://localhost:11434", model="qwen2:1.5b", timeout=30)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": MOCK_RESPONSE}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(comp._client, "post", new=AsyncMock(return_value=mock_resp)):
        result = await comp.compress(chunk_id=1, text="some conversation text", level=1)

    assert isinstance(result, SummaryResult)
    assert result.chunk_id == 1
    assert "Python" in result.entities

@pytest.mark.asyncio
async def test_compress_raises_on_http_error():
    comp = Compressor(base_url="http://localhost:11434", model="qwen2:1.5b", timeout=5)
    with patch.object(
        comp._client, "post", new=AsyncMock(side_effect=httpx.ConnectError("refused"))
    ):
        with pytest.raises(httpx.ConnectError):
            await comp.compress(chunk_id=1, text="text", level=1)
