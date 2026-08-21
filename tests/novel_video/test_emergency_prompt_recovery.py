from __future__ import annotations

import json
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.novel_video.h3_provider import reconcile_emergency_prompt_journals
from backend.novel_video.models import NovelVideoProject, ProductionMode, ProductionRun, ShotRecord
from backend.novel_video.repository import NovelVideoRepository
from backend.orchestration.database import OrchestrationDatabase


@dataclass(frozen=True)
class Cancelled:
    state: str


class Adapter:
    def __init__(self, state="verified_cancelled", error: Exception | None = None):
        self.state, self.error, self.ids = state, error, []

    async def cancel_job(self, prompt_id):
        self.ids.append(prompt_id)
        if self.error:
            raise self.error
        return Cancelled(self.state)


def _repo(tmp_path: Path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "db.sqlite")))
    project = NovelVideoProject(id="project-1", name="P", root=tmp_path)
    repo.create_project(project)
    run = ProductionRun(id="run-1", project_id=project.id, chapter_indexes=[1], mode=ProductionMode.ONE_CLICK)
    repo.save_run(run)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="c", sequence=1))
    return repo


def _journal(root: Path, checkpoint: dict, prompt="prompt-1") -> Path:
    path = root / "outputs" / "formal" / "segment.mp4.h3.emergency.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"token": prompt, "state": "prompt_checkpoint_failed", "checkpoint": checkpoint, "workflow": {}}), encoding="utf-8")
    return path


def _checkpoint(root: Path, run_id="run-1"):
    core = {
        "task_id": "task-1", "run_id": run_id, "shot_id": "shot-1", "attempt_id": "task-1:1",
        "prompt": "move", "negative_prompt": "", "base_seed": 42, "effective_seed": 42,
        "width": 864, "height": 480, "fps": 24, "duration_seconds": 5,
        "legal_frame_count": 124, "aspect_ratio": "16:9", "megapixel_profile": 0.4,
        "inputs": [], "video_asset_ids": [], "audio_asset_ids": [], "models": {},
        "workflow_version": "h3-ref2va-v1", "output_video": str((root / "outputs" / "formal" / "segment.mp4").resolve()),
        "output_tail": str((root / "outputs" / "formal" / "tail.png").resolve()),
    }
    return {**core, "idempotency_hash": sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()}


@pytest.mark.asyncio
async def test_startup_restores_canonical_checkpoint_without_cancelling(tmp_path):
    repo = _repo(tmp_path)
    checkpoint = _checkpoint(tmp_path)
    path = _journal(tmp_path, checkpoint)
    adapter = Adapter()

    result = await reconcile_emergency_prompt_journals([tmp_path], repo, lambda: adapter)

    assert result[0]["state"] == "checkpoint_reconciled"
    assert repo.get_generation_checkpoint("run-1", "shot-1")["prompt_id"] == "prompt-1"
    assert adapter.ids == []
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "checkpoint_reconciled"


@pytest.mark.asyncio
async def test_unpersistable_journal_records_verified_or_uncertain_cancel(tmp_path):
    repo = _repo(tmp_path)
    checkpoint = _checkpoint(tmp_path, "missing")
    path = _journal(tmp_path, checkpoint)
    verified = Adapter("verified_cancelled")
    result = await reconcile_emergency_prompt_journals([tmp_path], repo, lambda: verified)
    assert result[0]["state"] == "verified_cancelled"
    assert verified.ids == ["prompt-1"]

    path.write_text(json.dumps({"token": "prompt-2", "state": "prompt_checkpoint_failed", "checkpoint": checkpoint, "workflow": {}}), encoding="utf-8")
    uncertain = Adapter(error=RuntimeError("queue unavailable"))
    result = await reconcile_emergency_prompt_journals([tmp_path], repo, lambda: uncertain)
    assert result[0]["state"] == "cancel_uncertain"
    assert "queue unavailable" in json.loads(path.read_text(encoding="utf-8"))["reconciliation"]["cancel_error"]

    retry = Adapter("verified_cancelled")
    result = await reconcile_emergency_prompt_journals([tmp_path], repo, lambda: retry)
    assert result[0]["state"] == "verified_cancelled"
    assert retry.ids == ["prompt-2"]
