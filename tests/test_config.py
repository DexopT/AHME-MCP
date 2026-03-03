# tests/test_config.py
import tomllib
import pytest
from ahme.config import load_config, AHMEConfig

def test_load_config_returns_dataclass(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""
[chunking]
chunk_size_tokens = 1500
overlap_tokens = 150

[queue]
db_path = "test.db"
max_retries = 3

[monitor]
poll_interval_seconds = 2.0
cpu_idle_threshold_percent = 30.0

[ollama]
base_url = "http://localhost:11434"
model = "qwen2:1.5b"
timeout_seconds = 60

[merger]
batch_size = 5

[logging]
log_file = "ahme.log"
memory_file = ".ahme_memory.md"
max_bytes = 5242880
backup_count = 3
""")
    cfg = load_config(str(cfg_file))
    assert isinstance(cfg, AHMEConfig)
    assert cfg.chunking.chunk_size_tokens == 1500
    assert cfg.ollama.model == "qwen2:1.5b"
    assert cfg.queue.max_retries == 3
