# tests/test_daemon.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ahme.config import load_config
from ahme.daemon import AHMEDaemon

@pytest.fixture
def cfg(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f"""
[chunking]
chunk_size_tokens = 50
overlap_tokens = 5

[queue]
db_path = "{str(tmp_path / 'test.db').replace(chr(92), '/')}"
max_retries = 2

[monitor]
poll_interval_seconds = 0.05
cpu_idle_threshold_percent = 99.0

[ollama]
base_url = "http://localhost:11434"
model = "qwen2:1.5b"
timeout_seconds = 5

[merger]
batch_size = 3

[logging]
log_file = "{str(tmp_path / 'ahme.log').replace(chr(92), '/')}"
memory_file = "{str(tmp_path / '.ahme_memory.md').replace(chr(92), '/')}"
max_bytes = 1048576
backup_count = 1
""")
    return load_config(str(cfg_file))

@pytest.mark.asyncio
async def test_ingest_enqueues_chunks(cfg):
    daemon = AHMEDaemon(cfg)
    text = " ".join(["word"] * 200)
    count = daemon.ingest(text)
    assert count > 0
    assert daemon.db.pending_count() == count

@pytest.mark.asyncio
async def test_daemon_processes_queue_and_stops(cfg):
    daemon = AHMEDaemon(cfg)
    daemon.ingest(" ".join(["word"] * 100))

    from ahme.compressor import SummaryResult
    mock_result = SummaryResult(chunk_id=1, level=1, key_facts=["ok"], decisions=[], open_questions=[], entities=[])
    daemon._compressor.compress = AsyncMock(return_value=mock_result)

    # Run daemon briefly
    task = asyncio.create_task(daemon.run())
    await asyncio.sleep(0.5)
    daemon.stop()
    await asyncio.wait_for(task, timeout=2.0)
