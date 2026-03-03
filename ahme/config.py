from __future__ import annotations
import tomllib
from dataclasses import dataclass


@dataclass
class ChunkingConfig:
    chunk_size_tokens: int
    overlap_tokens: int


@dataclass
class QueueConfig:
    db_path: str
    max_retries: int


@dataclass
class MonitorConfig:
    poll_interval_seconds: float
    cpu_idle_threshold_percent: float


@dataclass
class OllamaConfig:
    base_url: str
    model: str
    timeout_seconds: int


@dataclass
class MergerConfig:
    batch_size: int


@dataclass
class LoggingConfig:
    log_file: str
    memory_file: str
    max_bytes: int
    backup_count: int


@dataclass
class AHMEConfig:
    chunking: ChunkingConfig
    queue: QueueConfig
    monitor: MonitorConfig
    ollama: OllamaConfig
    merger: MergerConfig
    logging: LoggingConfig


import pathlib

def load_config(path: str = "config.toml") -> AHMEConfig:
    config_path = pathlib.Path(path).resolve()
    base_dir = config_path.parent
    
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    
    # Resolve relative paths relative to config.toml directory
    def resolve_path(p: str) -> str:
        pth = pathlib.Path(p)
        if not pth.is_absolute():
            return str(base_dir / pth)
        return str(pth)

    raw["queue"]["db_path"] = resolve_path(raw["queue"]["db_path"])
    raw["logging"]["log_file"] = resolve_path(raw["logging"]["log_file"])
    raw["logging"]["memory_file"] = resolve_path(raw["logging"]["memory_file"])

    return AHMEConfig(
        chunking=ChunkingConfig(**raw["chunking"]),
        queue=QueueConfig(**raw["queue"]),
        monitor=MonitorConfig(**raw["monitor"]),
        ollama=OllamaConfig(**raw["ollama"]),
        merger=MergerConfig(**raw["merger"]),
        logging=LoggingConfig(**raw["logging"]),
    )


def override_paths(cfg: AHMEConfig, ns_dir: pathlib.Path) -> AHMEConfig:
    """Return a new config with DB, log, and memory file paths redirected to ns_dir."""
    return AHMEConfig(
        chunking=cfg.chunking,
        queue=QueueConfig(
            db_path=str(ns_dir / "ahme_queue.db"),
            max_retries=cfg.queue.max_retries,
        ),
        monitor=cfg.monitor,
        ollama=cfg.ollama,
        merger=cfg.merger,
        logging=LoggingConfig(
            log_file=str(ns_dir / "ahme.log"),
            memory_file=str(ns_dir / ".ahme_memory.md"),
            max_bytes=cfg.logging.max_bytes,
            backup_count=cfg.logging.backup_count,
        ),
    )
