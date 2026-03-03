from __future__ import annotations
import asyncio
import logging
import pathlib
import signal
from logging.handlers import RotatingFileHandler
from ahme.config import AHMEConfig
from ahme.db import QueueDB
from ahme.partitioner import Partitioner
from ahme.monitor import ResourceMonitor
from ahme.compressor import Compressor
from ahme.merger import Merger


def _setup_logging(cfg: AHMEConfig) -> logging.Logger:
    logger = logging.getLogger("ahme")
    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler(
        cfg.logging.log_file,
        maxBytes=cfg.logging.max_bytes,
        backupCount=cfg.logging.backup_count,
    )
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    return logger


class AHMEDaemon:
    def __init__(self, cfg: AHMEConfig) -> None:
        self._cfg = cfg
        self._log = _setup_logging(cfg)
        self.db = QueueDB(cfg.queue.db_path)
        self._partitioner = Partitioner(
            chunk_size_tokens=cfg.chunking.chunk_size_tokens,
            overlap_tokens=cfg.chunking.overlap_tokens,
        )
        self._monitor = ResourceMonitor(
            cpu_threshold=cfg.monitor.cpu_idle_threshold_percent,
            poll_interval=cfg.monitor.poll_interval_seconds,
        )
        self._compressor = Compressor(
            base_url=cfg.ollama.base_url,
            model=cfg.ollama.model,
            timeout=cfg.ollama.timeout_seconds,
        )
        self._merger = Merger(batch_size=cfg.merger.batch_size)
        self._running = False
        self._master_memory: str = ""

    def ingest(self, raw_text: str) -> int:
        """Partition raw_text and enqueue all chunks. Returns chunk count."""
        chunks = self._partitioner.partition(raw_text)
        for idx, text in enumerate(chunks):
            self.db.enqueue(chunk_id=idx + 1, text=text, level=1)
        self._log.info(f"Ingested {len(chunks)} chunks into queue.")
        return len(chunks)

    def stop(self) -> None:
        self._running = False

    def reset(self, keep_master: bool = True) -> None:
        """Clear all DB data and optionally re-seed with the current master memory.

        This implements the 'context-window replacement' pattern:
        the compressed memory becomes the sole seed for the next session,
        discarding all raw chunks and intermediate summaries.
        """
        self.db.clear_all()
        self._log.info("Context window cleared (DB wiped).")
        if keep_master and self._master_memory:
            # Re-ingest the master memory as the new seed at level 1
            self.ingest(self._master_memory)
            self._log.info("Master memory re-seeded into queue.")

    @property
    def master_memory(self) -> str:
        return self._master_memory

    async def run(self) -> None:
        self._running = True
        self._log.info("AHME daemon started.")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                pass  # Windows

        while self._running:
            if self.db.pending_count() == 0:
                await asyncio.sleep(self._cfg.monitor.poll_interval_seconds)
                continue

            idle = await self._monitor.wait_until_idle(
                timeout=self._cfg.monitor.poll_interval_seconds * 5
            )
            if not idle:
                await asyncio.sleep(self._cfg.monitor.poll_interval_seconds)
                continue

            row = self.db.dequeue()
            if row is None:
                continue

            try:
                result = await self._compressor.compress(
                    chunk_id=row["chunk_id"], text=row["text"], level=row["level"]
                )
                self.db.save_summary(
                    chunk_id=row["chunk_id"], level=row["level"], summary=result.to_text()
                )
                self.db.mark_done(row["id"])
                self._log.info(f"Compressed chunk {row['chunk_id']} (level {row['level']}).")
                await self._maybe_merge(row["level"])
            except Exception as exc:
                self._log.warning(f"Chunk {row['chunk_id']} failed: {exc}")
                self.db.increment_retry(row["id"], max_retries=self._cfg.queue.max_retries)

        await self._compressor.aclose()
        self.db.close()
        self._log.info("AHME daemon stopped.")

    async def _maybe_merge(self, level: int) -> None:
        summaries_rows = self.db.get_summaries_by_level(level)
        if len(summaries_rows) < self._cfg.merger.batch_size:
            return
        from ahme.compressor import SummaryResult
        summaries = [
            SummaryResult(
                chunk_id=r["chunk_id"],
                level=r["level"],
                key_facts=[r["summary"]],
            )
            for r in summaries_rows
        ]
        self._log.info(f"Merging {len(summaries)} level-{level} summaries...")
        master = await self._merger.merge(summaries, level=level + 1, compressor=self._compressor)
        self._master_memory = master.to_text()
        self._write_memory_file()
        self._log.info("Master memory block updated.")

    def _write_memory_file(self) -> None:
        """Persist master memory to a markdown file readable by any AI tool."""
        try:
            path = pathlib.Path(self._cfg.logging.memory_file)
            path.write_text(
                f"# AHME Master Memory Block\n\n{self._master_memory}\n",
                encoding="utf-8",
            )
            self._log.info(f"Memory file written: {path}")
        except Exception as exc:
            self._log.warning(f"Could not write memory file: {exc}")
