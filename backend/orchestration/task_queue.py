"""Production Task Queue (Phase 10.7-A).

A small, thread-safe, file-backed queue of production tasks consumed by
:class:`backend.orchestration.worker.TaskRunner`.  The queue is deliberately
decoupled from the legacy job/step orchestration so long video chains can be
submitted through the pipeline API and executed by a worker without creating
hundreds of DB rows.

Task status writeback shape (StudioDashboard):
``{task_id, shot_id, stage, progress, gpu_time, checkpoint}``.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_TYPES = ("image_generation", "video_generation", "video_chain")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_retry_policy() -> dict:
    return {"max_attempts": 3, "backoff_seconds": 2.0}


@dataclass
class WorkerTask:
    """A queued unit of production work (Phase 10.7-A)."""

    task_id: str = ""
    task_type: str = "video_chain"   # image_generation | video_generation | video_chain
    project_id: str = "default"
    priority: int = 0                # higher value is claimed first
    retry_policy: dict = field(default_factory=default_retry_policy)
    checkpoint_id: str = ""          # ChainCheckpoint manifest key for resume
    payload: dict = field(default_factory=dict)
    status: str = "queued"           # queued | running | completed | failed
    attempts: int = 0
    worker_id: str = ""
    # --- status writeback (StudioDashboard) ---
    shot_id: str = ""
    stage: str = ""
    progress: float = 0.0
    gpu_time_s: float = 0.0
    checkpoint: dict = field(default_factory=dict)
    # --- result ---
    error: str = ""
    result: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    finished_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class TaskQueue:
    """Thread-safe, file-backed queue with atomic claim and retry semantics.

    Layout: ``<root>/tasks.json`` → ``{"tasks": {task_id: WorkerTask}}``.
    """

    def __init__(self, root: str | Path = "storage/tasks"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tasks.json"
        self._lock = threading.RLock()
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------ io
    def _load(self) -> None:
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = payload.get("tasks", {})
            except Exception:
                self._data = {}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"tasks": self._data}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def _task(self, raw: dict) -> WorkerTask:
        return WorkerTask(**{k: raw.get(k, v) for k, v in WorkerTask.__dataclass_fields__.items()})

    # ----------------------------------------------------------------- api
    def enqueue(
        self,
        task_type: str,
        payload: dict,
        *,
        project_id: str = "default",
        priority: int = 0,
        retry_policy: dict | None = None,
        checkpoint_id: str = "",
        task_id: str = "",
    ) -> WorkerTask:
        if task_type not in TASK_TYPES:
            raise ValueError(f"unknown task_type: {task_type!r} (expected {TASK_TYPES})")
        with self._lock:
            task = WorkerTask(
                task_id=task_id or uuid.uuid4().hex[:16],
                task_type=task_type,
                project_id=project_id,
                priority=priority,
                retry_policy=retry_policy or default_retry_policy(),
                checkpoint_id=checkpoint_id,
                payload=payload,
            )
            self._data[task.task_id] = task.to_dict()
            self._save()
            return task

    def claim_next(self, worker_id: str, limit: int = 2) -> list[WorkerTask]:
        """Atomically claim queued tasks (highest priority first)."""
        with self._lock:
            claimed: list[WorkerTask] = []
            ordered = sorted(
                self._data.items(),
                key=lambda kv: (-int(kv[1].get("priority", 0)), kv[1].get("created_at", "")),
            )
            for tid, raw in ordered:
                if len(claimed) >= limit:
                    break
                if raw.get("status") != "queued":
                    continue
                if (raw.get("payload") or {}).get("formal_novel_video"):
                    checkpoint = dict(raw.get("checkpoint") or {})
                    # Queue retries/recovery are execution leases, not new
                    # semantic media-generation attempts.  Bind one stable
                    # identity at the first claim and preserve it forever.
                    checkpoint.setdefault(
                        "formal_generation_attempt_id",
                        f"{tid}:{int(raw.get('attempts', 0)) + 1}",
                    )
                    raw["checkpoint"] = checkpoint
                raw["status"] = "running"
                raw["worker_id"] = worker_id
                raw["attempts"] = int(raw.get("attempts", 0)) + 1
                raw["updated_at"] = _now()
                claimed.append(self._task(raw))
            if claimed:
                self._save()
            return claimed

    def update(self, task_id: str, **fields: Any) -> WorkerTask | None:
        with self._lock:
            raw = self._data.get(task_id)
            if not raw:
                return None
            for key, value in fields.items():
                if key in WorkerTask.__dataclass_fields__:
                    raw[key] = value
            raw["updated_at"] = _now()
            self._save()
            return self._task(raw)

    def complete(self, task_id: str, result: dict | None = None) -> WorkerTask | None:
        return self.update(
            task_id,
            status="completed",
            result=result or {},
            finished_at=_now(),
            stage="complete",
            progress=1.0,
        )

    def fail(self, task_id: str, error: str) -> WorkerTask | None:
        """Mark a task failed, re-queueing it while retry attempts remain."""
        with self._lock:
            raw = self._data.get(task_id)
            if not raw:
                return None
            attempts = int(raw.get("attempts", 0))
            max_attempts = int((raw.get("retry_policy") or {}).get("max_attempts", 3))
            if attempts < max_attempts:
                raw["status"] = "queued"
                raw["worker_id"] = ""
                raw["priority"] = int(raw.get("priority", 0)) + 1  # retries jump the queue
                raw["error"] = error
            else:
                raw["status"] = "failed"
                raw["error"] = error
                raw["finished_at"] = _now()
            raw["updated_at"] = _now()
            self._save()
            return self._task(raw)

    def fail_terminal(self, task_id: str, error: str) -> WorkerTask | None:
        """Fail a task without retrying it (used by formal durable workflows)."""
        with self._lock:
            raw = self._data.get(task_id)
            if not raw:
                return None
            raw.update({
                "status": "failed", "error": error, "finished_at": _now(),
                "updated_at": _now(), "stage": "failed",
            })
            self._save()
            return self._task(raw)

    def recover_orphaned_formal_tasks(self) -> list[WorkerTask]:
        """Make crashed formal `running` tasks claimable with their same id.

        Formal prompt state lives in the novel-video checkpoint; this only
        repairs the queue lease/status and deliberately never creates a task.
        """
        with self._lock:
            recovered: list[WorkerTask] = []
            for raw in self._data.values():
                if raw.get("status") != "running" or not (raw.get("payload") or {}).get("formal_novel_video"):
                    continue
                raw.update({"status": "queued", "worker_id": "", "stage": "formal_recovery", "updated_at": _now()})
                recovered.append(self._task(raw))
            if recovered:
                self._save()
            return recovered

    def get(self, task_id: str) -> WorkerTask | None:
        with self._lock:
            raw = self._data.get(task_id)
            return self._task(raw) if raw else None

    def list(self, status: str | None = None) -> list[WorkerTask]:
        with self._lock:
            items = [self._task(raw) for raw in self._data.values()]
        if status:
            items = [t for t in items if t.status == status]
        return sorted(items, key=lambda t: (t.created_at, t.task_id))
