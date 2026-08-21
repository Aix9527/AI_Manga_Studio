"""Phase 10.7-A: production worker task queue integration tests.

Covers the GPT acceptance flow: API/queue -> OrchestratorWorker poll ->
TaskRunner -> ChainRuntime -> completed task with StudioDashboard writeback.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.task_queue import TaskQueue
from backend.orchestration.worker import OrchestratorWorker, SSEBroadcaster, TaskRunner
from backend.pipeline import routes as pipeline_routes


def _shot(sid: str, keyframe: str, **kw) -> dict:
    data = {
        "id": sid,
        "location": "lab",
        "time_of_day": "night",
        "image_path": keyframe,
        "prompt_tail": f"shot {sid}",
        "negative_prompt": "bad",
        "seed": 42,
        "motion_level": "low",
        "width": 480,
        "height": 832,
        "frames": 81,
        "fps": 24,
    }
    data.update(kw)
    return data


@dataclass
class FakeArtifact:
    path: Path
    kind: str = "video"


class FakeVideoProvider:
    def __init__(self, out_root: Path):
        self.out_root = out_root
        self.requests = []
        self.generated = []

    async def generate(self, request):
        self.requests.append(request)
        request.output_path.write_bytes(b"dummy-video")
        self.generated.append(request.output_path.stem)
        return FakeArtifact(path=request.output_path)


class FakeImageProvider:
    def __init__(self, out_root: Path):
        self.out_root = out_root
        self.calls = []

    async def generate(self, request):
        self.calls.append(request)
        request.output_path.write_bytes(b"dummy-image")
        return FakeArtifact(path=request.output_path, kind="image")


def _fake_extractor(video_path: Path, out: Path) -> Path | None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"last-frame")
    return out


def _config(tmp_path: Path) -> OrchestrationConfig:
    return OrchestrationConfig(
        database_path=str(tmp_path / "db.sqlite"),
        checkpoint_dir=str(tmp_path / "ckpt"),
        project_root=str(tmp_path / "projects"),
        poll_interval_seconds=0.01,
    )


# ---------------------------------------------------------------- queue
def test_task_queue_claim_priority_retry_and_complete(tmp_path: Path):
    queue = TaskQueue(root=tmp_path / "tasks")
    low = queue.enqueue("video_chain", {"shots": []}, priority=0)
    high = queue.enqueue("video_chain", {"shots": []}, priority=5)

    claimed = queue.claim_next("worker-1", limit=2)
    assert [t.task_id for t in claimed] == [high.task_id, low.task_id]
    assert all(t.status == "running" and t.worker_id == "worker-1" for t in claimed)
    assert all(t.attempts == 1 for t in claimed)

    # Nothing left to claim while running
    assert queue.claim_next("worker-2", limit=10) == []

    # Retry: re-queues while attempts remain, then hard-fails
    queue.fail(high.task_id, "comfy timeout")
    retried = queue.get(high.task_id)
    assert retried.status == "queued"
    assert retried.attempts == 1

    claimed2 = queue.claim_next("worker-2", limit=1)
    assert claimed2 and claimed2[0].task_id == high.task_id
    queue.fail(high.task_id, "comfy timeout")   # attempts=2 -> re-queued
    assert queue.get(high.task_id).status == "queued"

    claimed3 = queue.claim_next("worker-2", limit=1)
    assert claimed3 and claimed3[0].task_id == high.task_id
    queue.fail(high.task_id, "comfy timeout")   # attempts=3 -> hard failed
    assert queue.get(high.task_id).status == "failed"

    queue.complete(low.task_id, {"ok": True})
    done = queue.get(low.task_id)
    assert done.status == "completed"
    assert done.result == {"ok": True}
    assert done.finished_at


def test_task_queue_persists_across_reload(tmp_path: Path):
    root = tmp_path / "tasks"
    queue = TaskQueue(root=root)
    task = queue.enqueue("video_chain", {"shots": [{"id": "gx_001"}]}, project_id="p1")
    queue.complete(task.task_id, {"summary": {}})

    reloaded = TaskQueue(root=root)
    assert reloaded.get(task.task_id).status == "completed"


# ------------------------------------------------------------- task runner
def test_runner_video_chain_10_shots_via_worker(tmp_path: Path):
    """GPT acceptance: 10-shot task -> Queue -> Worker -> ChainRuntime -> complete."""
    queue = TaskQueue(root=tmp_path / "tasks")
    broadcaster = SSEBroadcaster()
    config = _config(tmp_path)

    shots = [
        _shot(f"gx_{i:03d}", str(tmp_path / "kf" / f"k{i}.png"))
        for i in range(1, 11)
    ]
    provider = FakeVideoProvider(tmp_path / "videos")

    runner = TaskRunner(
        queue,
        broadcaster,
        config,
        workdir=tmp_path / "chains",
        video_provider_factory=lambda comfy_url="": provider,
        frame_extractor=_fake_extractor,
    )
    worker = OrchestratorWorker(
        db=None, repo=None, executor=None, broadcaster=broadcaster,
        config=config, task_queue=queue, task_runner=runner,
    )

    task = queue.enqueue(
        "video_chain",
        {"shots": shots, "resume": False},
        project_id="p1",
    )

    progress_queue = broadcaster.subscribe(task.task_id)
    worker._poll_tasks()

    done = queue.get(task.task_id)
    assert done.status == "completed", done.error
    results = done.result["results"]
    assert [r["status"] for r in results] == ["completed"] * 10
    assert provider.generated == [f"gx_{i:03d}" for i in range(1, 11)]
    summary = done.result["summary"]
    assert len(summary["completed"]) == 10

    # StudioDashboard writeback: shot_id/stage/progress/checkpoint populated
    assert done.stage == "complete"
    assert done.progress == 1.0
    assert done.checkpoint.get("completed") == [f"gx_{i:03d}" for i in range(1, 11)]
    assert done.gpu_time_s >= 0.0

    # Live per-shot progress events were broadcast for StudioDashboard
    progress_events = []
    while not progress_queue.empty():
        progress_events.append(progress_queue.get_nowait())
    assert any("chain_generate" in e for e in progress_events), progress_events


def test_runner_video_generation_single_shot(tmp_path: Path):
    queue = TaskQueue(root=tmp_path / "tasks")
    broadcaster = SSEBroadcaster()
    config = _config(tmp_path)
    provider = FakeVideoProvider(tmp_path / "videos")

    runner = TaskRunner(
        queue, broadcaster, config,
        workdir=tmp_path / "chains",
        video_provider_factory=lambda comfy_url="": provider,
        frame_extractor=_fake_extractor,
    )
    task = queue.enqueue(
        "video_generation",
        {"shot": _shot("gx_001", str(tmp_path / "k1.png")), "resume": False},
        project_id="p1",
    )
    asyncio.run(runner.execute_task(task))

    done = queue.get(task.task_id)
    assert done.status == "completed"
    assert done.result["results"][0]["shot_id"] == "gx_001"
    assert provider.generated == ["gx_001"]


def test_runner_image_generation(tmp_path: Path):
    queue = TaskQueue(root=tmp_path / "tasks")
    broadcaster = SSEBroadcaster()
    config = _config(tmp_path)
    image_provider = FakeImageProvider(tmp_path / "images")

    runner = TaskRunner(
        queue, broadcaster, config,
        workdir=tmp_path / "chains",
        image_provider_factory=lambda comfy_url="": image_provider,
    )
    task = queue.enqueue(
        "image_generation",
        {
            "prompt": "a hero",
            "negative_prompt": "bad",
            "seed": 7,
            "width": 432,
            "height": 768,
            "output_path": str(tmp_path / "images" / "hero.png"),
            "shot_id": "gx_001",
        },
        project_id="p1",
    )
    asyncio.run(runner.execute_task(task))

    done = queue.get(task.task_id)
    assert done.status == "completed"
    assert (tmp_path / "images" / "hero.png").exists()
    assert done.result["kind"] == "image"


def test_runner_failed_chain_is_requeued_then_failed(tmp_path: Path):
    queue = TaskQueue(root=tmp_path / "tasks")
    broadcaster = SSEBroadcaster()
    config = _config(tmp_path)

    class BoomProvider:
        async def generate(self, request):
            raise RuntimeError("comfy timeout")

    runner = TaskRunner(
        queue, broadcaster, config,
        workdir=tmp_path / "chains",
        video_provider_factory=lambda comfy_url="": BoomProvider(),
        frame_extractor=_fake_extractor,
    )
    task = queue.enqueue(
        "video_chain",
        {"shots": [_shot("gx_001", str(tmp_path / "k1.png"))], "resume": False},
        project_id="p1",
        retry_policy={"max_attempts": 2, "backoff_seconds": 0.0},
    )
    first = queue.claim_next("worker-1", limit=1)[0]
    asyncio.run(runner.execute_task(first))  # attempt 1 fails -> re-queued
    assert queue.get(task.task_id).status == "queued"

    # Worker re-claims the task (attempts -> 2) before the retry execution
    second = queue.claim_next("worker-1", limit=1)[0]
    assert second.task_id == task.task_id
    asyncio.run(runner.execute_task(second))  # attempt 2 fails -> failed
    failed = queue.get(task.task_id)
    assert failed.status == "failed"
    assert "comfy timeout" in failed.error
    assert failed.finished_at


# ------------------------------------------------------------- API routes
def test_task_api_enqueue_and_status(tmp_path: Path):
    queue = TaskQueue(root=tmp_path / "tasks")
    app = FastAPI()
    app.state.task_queue = queue
    app.include_router(pipeline_routes.router)
    client = TestClient(app)

    resp = client.post(
        "/api/pipeline/tasks",
        json={
            "task_type": "video_chain",
            "project_id": "p1",
            "priority": 3,
            "checkpoint_id": "ck-1",
            "payload": {"shots": [{"id": "gx_001"}]},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["task_type"] == "video_chain"
    assert body["checkpoint_id"] == "ck-1"
    assert body["priority"] == 3

    task_id = body["task_id"]
    got = client.get(f"/api/pipeline/tasks/{task_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "queued"

    listed = client.get("/api/pipeline/tasks", params={"status": "queued"})
    assert listed.json()["total"] == 1

    missing = client.get("/api/pipeline/tasks/nope")
    assert missing.status_code == 404
