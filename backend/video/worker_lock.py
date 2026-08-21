"""Process-scoped locks for local video generation."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path


class LeaseError(RuntimeError):
    """Raised when a live process already owns a generation lock."""


class WorkerLeaseLock:
    """OS advisory locks retained for the owner's lifetime.

    Unlike an mtime lease, operating-system locks are released as soon as a
    crashed/killed process exits.  The small JSON payload is audit evidence;
    it is not used to steal a live lock or to wait for a TTL.
    """

    def __init__(self, root: str | Path = "storage/chains", ttl_seconds: int = 3600, worker_id: str = ""):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds  # retained API compatibility; never used for stealing
        self.worker_id = worker_id or f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._held: set[str] = set()
        self._handles: dict[str, object] = {}

    def lease_path(self, shot_id: str) -> Path:
        return self.root / "leases" / f"{shot_id}.lease"

    def acquire(self, shot_id: str) -> str:
        if shot_id in self._handles:
            return self.worker_id
        path = self.lease_path(shot_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Do not use ``a+b`` here.  Windows gives append handles special file
        # pointer semantics: a seek followed by write still appends, which can
        # move the byte range away from the byte msvcrt locked.  A raw O_RDWR
        # handle has stable seek/write behaviour and is released by the OS if
        # the owning process is killed.
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(descriptor, "r+b", buffering=0)
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b" ")
            os.fsync(handle.fileno())
        try:
            self._lock_handle(handle)
        except OSError:
            handle.close()
            raise LeaseError(f"shot {shot_id} leased by a live process")
        handle.seek(0)
        payload = json.dumps({"worker_id": self.worker_id, "pid": os.getpid(), "started_at": time.time()})
        handle.write(payload.encode("utf-8"))
        handle.truncate()
        os.fsync(handle.fileno())
        self._handles[shot_id] = handle
        self._held.add(shot_id)
        return self.worker_id

    def release(self, shot_id: str) -> None:
        self._held.discard(shot_id)
        handle = self._handles.pop(shot_id, None)
        if handle is None:
            return
        try:
            self._unlock_handle(handle)
        finally:
            handle.close()

    def holder(self, shot_id: str) -> str:
        if shot_id in self._handles:
            return self.worker_id
        try:
            payload = json.loads(self.lease_path(shot_id).read_text(encoding="utf-8"))
            return str(payload.get("worker_id", ""))
        except OSError:
            return ""

    def held(self) -> list[str]:
        return sorted(self._held)

    @staticmethod
    def _lock_handle(handle) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_handle(handle) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
