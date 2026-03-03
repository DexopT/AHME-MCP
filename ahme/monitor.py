from __future__ import annotations
import asyncio
import os
import psutil
from typing import Optional


class ResourceMonitor:
    """Polls CPU utilization and an optional lock file to detect AI idle state."""

    def __init__(
        self,
        cpu_threshold: float,
        poll_interval: float,
        lock_file: Optional[str] = None,
    ) -> None:
        self._threshold = cpu_threshold
        self._interval = poll_interval
        self._lock_file = lock_file

    def is_idle(self) -> bool:
        if self._lock_file and os.path.exists(self._lock_file):
            return False
        cpu = psutil.cpu_percent(interval=None)
        return cpu < self._threshold

    async def wait_until_idle(self, timeout: float = float("inf")) -> bool:
        """Blocks until system is idle or timeout expires. Returns True if idle."""
        elapsed = 0.0
        while elapsed < timeout:
            if self.is_idle():
                return True
            await asyncio.sleep(self._interval)
            elapsed += self._interval
        return False
