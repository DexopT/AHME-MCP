# tests/test_monitor.py
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from ahme.monitor import ResourceMonitor

@pytest.mark.asyncio
async def test_is_idle_when_cpu_low():
    monitor = ResourceMonitor(cpu_threshold=80.0, poll_interval=0.1)
    with patch("psutil.cpu_percent", return_value=10.0):
        assert await monitor.wait_until_idle(timeout=1.0) is True

@pytest.mark.asyncio
async def test_not_idle_when_cpu_high():
    monitor = ResourceMonitor(cpu_threshold=80.0, poll_interval=0.05)
    with patch("psutil.cpu_percent", return_value=95.0):
        # Should timeout because CPU is always busy
        assert await monitor.wait_until_idle(timeout=0.2) is False

@pytest.mark.asyncio
async def test_lock_file_makes_system_busy(tmp_path):
    lock = tmp_path / "agent.lock"
    lock.write_text("locked")
    monitor = ResourceMonitor(
        cpu_threshold=80.0, poll_interval=0.05, lock_file=str(lock)
    )
    with patch("psutil.cpu_percent", return_value=5.0):
        assert await monitor.wait_until_idle(timeout=0.2) is False
