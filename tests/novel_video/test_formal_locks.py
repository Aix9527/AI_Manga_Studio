from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from backend.video.worker_lock import LeaseError, WorkerLeaseLock


def _holder_script() -> str:
    return r"""
import sys, time
from pathlib import Path
from backend.video.worker_lock import WorkerLeaseLock
lock = WorkerLeaseLock(root=Path(sys.argv[1]), worker_id=sys.argv[3])
lock.acquire(sys.argv[2])
print('LOCKED', flush=True)
time.sleep(60)
"""


def _start_holder(root: Path, key: str, worker: str) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [sys.executable, "-c", _holder_script(), str(root), key, worker],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "LOCKED"
    return process


def _kill(process: subprocess.Popen[str]) -> None:
    process.kill()
    process.wait(timeout=10)


def test_live_process_owner_cannot_be_stolen(tmp_path: Path) -> None:
    process = _start_holder(tmp_path, "formal-gpu", "live-owner")
    try:
        contender = WorkerLeaseLock(root=tmp_path, worker_id="contender")
        with pytest.raises(LeaseError):
            contender.acquire("formal-gpu")
        assert contender.held() == []
    finally:
        _kill(process)


def test_killed_process_releases_same_task_lock_without_ttl_wait(tmp_path: Path) -> None:
    process = _start_holder(tmp_path, "shot-1", "crashed-owner")
    _kill(process)

    restarted = WorkerLeaseLock(root=tmp_path, worker_id="restart-owner", ttl_seconds=3600)
    started = time.monotonic()
    assert restarted.acquire("shot-1") == "restart-owner"
    assert time.monotonic() - started < 2
    restarted.release("shot-1")


def test_global_lock_serializes_different_shots_across_processes(tmp_path: Path) -> None:
    first = _start_holder(tmp_path, "formal-gpu", "shot-a-process")
    try:
        second = WorkerLeaseLock(root=tmp_path, worker_id="shot-b-process")
        with pytest.raises(LeaseError):
            second.acquire("formal-gpu")
        # Per-shot keys do not collide; it is the global key that serializes GPU work.
        assert second.acquire("shot-b") == "shot-b-process"
        second.release("shot-b")
    finally:
        _kill(first)

