from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.novel_video.h3_frames import legal_h3_frames
from backend.novel_video.models import (
    AssetVersion,
    AspectRatio,
    H3ReferencePackage,
    NovelVideoProject,
    ProductionMode,
    ProductionRun,
    RunStatus,
    ShotRecord,
)
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.runner import NovelVideoRunner
from backend.novel_video.service import NovelVideoService
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.task_queue import TaskQueue
from backend.orchestration.worker import TaskRunner


def _asset(
    repo: NovelVideoRepository,
    *,
    project_id: str,
    run_id: str,
    asset_id: str,
    kind: str,
    path: Path,
) -> AssetVersion:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"asset:{asset_id}".encode("utf-8"))
    return repo.append_asset(
        AssetVersion(
            id=asset_id,
            project_id=project_id,
            run_id=run_id,
            kind=kind,
            state="approved",
            path=path,
            sha256=sha256(path.read_bytes()).hexdigest(),
        )
    )


@pytest.fixture
def formal_assets(tmp_path: Path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "formal-assets.db")))
    project = NovelVideoProject(
        id="project-h3-unified",
        name="H3 Unified",
        root=tmp_path / "project",
    )
    project.root.mkdir(parents=True, exist_ok=True)
    repo.create_project(project)
    run = ProductionRun(
        id="run-h3-unified",
        project_id=project.id,
        chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
    )
    repo.save_run(run)
    repo.update_run_status(run.id, RunStatus.PLANNING)
    repo.update_run_status(run.id, RunStatus.RENDERING)
    run = repo.get_run(run.id)
    assert run is not None and run.status is RunStatus.RENDERING

    character = _asset(
        repo,
        project_id=project.id,
        run_id=run.id,
        asset_id="character-ref",
        kind="character",
        path=project.root / "refs" / "character.png",
    )
    scene = _asset(
        repo,
        project_id=project.id,
        run_id=run.id,
        asset_id="scene-ref",
        kind="scene",
        path=project.root / "refs" / "scene.png",
    )
    motion = _asset(
        repo,
        project_id=project.id,
        run_id=run.id,
        asset_id="motion-ref",
        kind="video",
        path=project.root / "refs" / "motion.mp4",
    )
    voice = _asset(
        repo,
        project_id=project.id,
        run_id=run.id,
        asset_id="voice-ref",
        kind="dialogue_audio",
        path=project.root / "refs" / "voice.wav",
    )

    package = H3ReferencePackage(
        shot_id="shot-h3-unified",
        prompt_version="h3-unified-v1",
        prompt_text="雨夜走廊追逐",
        negative_prompt="static",
        base_seed=7,
        effective_seed=11,
        duration_seconds=5,
        legal_frame_count=legal_h3_frames(5),
        width=480,
        height=832,
        aspect_ratio=AspectRatio.PORTRAIT,
        picture_asset_version_ids=[character.id, scene.id],
        video_reference_asset_version_ids=[motion.id],
        audio_reference_asset_version_ids=[voice.id],
        workflow_version="h3_unified",
        continuity_reason="time_jump",
    )
    shot = ShotRecord(
        id=package.shot_id,
        run_id=run.id,
        chapter_id="chapter-1",
        sequence=1,
        reference_package=package,
        plan={"continuity": "time_jump"},
    )
    repo.save_shot(shot)
    queue = TaskQueue(root=tmp_path / "tasks")
    service = NovelVideoService(repo=repo, projects_root=tmp_path)
    scheduler = NovelVideoRunner(service=service, task_queue=queue)
    return repo, project, run, shot, queue, scheduler, motion, voice


def test_scheduler_persists_verified_video_and_audio_reference_paths(formal_assets) -> None:
    repo, _project, run, shot, queue, scheduler, motion, voice = formal_assets

    scheduler._enqueue_formal_task(run, shot)

    task = queue.list()[0]
    assert task.payload["video_paths"] == [str(motion.path)]
    assert task.payload["audio_paths"] == [str(voice.path)]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("video_paths", "unapproved-motion.mp4"),
        ("audio_paths", "unapproved-voice.wav"),
    ],
)
def test_worker_rejects_tampered_formal_media_paths(
    formal_assets, tmp_path: Path, field: str, replacement: str,
) -> None:
    repo, _project, run, shot, queue, scheduler, _motion, _voice = formal_assets
    scheduler._enqueue_formal_task(run, shot)
    task = queue.list()[0]
    forged = tmp_path / replacement
    forged.write_bytes(b"forged")
    payload = dict(task.payload)
    payload[field] = [str(forged)]
    task = replace(task, payload=payload)
    runner = TaskRunner(
        queue,
        SimpleNamespace(),
        SimpleNamespace(),
        workdir=tmp_path / "work",
        novel_video_repository=repo,
        formal_router_factory=lambda **_: None,
    )

    with pytest.raises(ValueError, match="paths do not match approved references"):
        runner._formal_replay_context(task)


def test_worker_builds_formal_request_with_verified_video_and_audio_paths(formal_assets, tmp_path: Path) -> None:
    repo, _project, run, shot, queue, scheduler, motion, voice = formal_assets
    scheduler._enqueue_formal_task(run, shot)
    task = queue.list()[0]
    runner = TaskRunner(
        queue,
        SimpleNamespace(),
        SimpleNamespace(),
        workdir=tmp_path / "work",
        novel_video_repository=repo,
        formal_router_factory=lambda **_: None,
    )

    _payload, _run, _project, package, request, _identity, _task = runner._formal_replay_context(task)

    assert package.video_reference_asset_version_ids == [motion.id]
    assert package.audio_reference_asset_version_ids == [voice.id]
    assert request.video_paths == (motion.path,)
    assert request.audio_paths == (voice.path,)


def test_scheduler_rejects_reference_when_approved_bytes_change(formal_assets) -> None:
    _repo, _project, run, shot, _queue, scheduler, motion, _voice = formal_assets
    motion.path.write_bytes(b"tampered-after-approval")

    with pytest.raises(Exception, match="approved reference asset does not verify"):
        scheduler._enqueue_formal_task(run, shot)
