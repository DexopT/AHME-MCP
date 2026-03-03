"""
Public API for the AHME daemon.

Usage:
    from ahme.api import AHME
    import asyncio

    engine = AHME("config.toml")
    engine.ingest(raw_conversation_text)
    asyncio.create_task(engine.run())          # start sidecar
    ...
    memory = engine.master_memory              # read compressed memory
    engine.stop()
"""
from __future__ import annotations
from ahme.config import load_config
from ahme.daemon import AHMEDaemon


class AHME:
    def __init__(self, config_path: str = "config.toml") -> None:
        cfg = load_config(config_path)
        self._daemon = AHMEDaemon(cfg)

    def ingest(self, raw_text: str) -> int:
        return self._daemon.ingest(raw_text)

    @property
    def master_memory(self) -> str:
        return self._daemon.master_memory

    def stop(self) -> None:
        self._daemon.stop()

    async def run(self) -> None:
        await self._daemon.run()
