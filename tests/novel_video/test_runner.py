from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from backend.novel_video.models import AssetVersion, AspectRatio, NovelVideoProject, ProductionMode, ProductionRun, RunEvent, RunStatus, ShotRecord, ShotStatus
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.service import NovelVideoService
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.task_queue import TaskQueue


def _plan(sequence: int, continuity: str) -> dict:
    return {"prompt": f"shot {sequence}", "negative_prompt": "", "base_seed": 7, "prompt_version": "v1",
            "workflow_version": "h3-ref2va-v1", "duration_seconds": 5, "width": 864, "height": 480,
            "aspect_ratio": AspectRatio.LANDSCAPE, "megapixel_profile": 0.4, "multiple": 32,
            "model_registry_ids": {}, "character_reference_asset_version_ids": [], "scene_reference_asset_version_ids": [],
            "video_reference_asset_version_ids": [], "audio_reference_asset_version_ids": [], "continuity": continuity,
            "inherit_tail": continuity == "same_action"}


@pytest.fixture
def prepared(tmp_path: Path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path / "project")
    repo.create_project(project)
    run = ProductionRun(id="run-1", project_id=project.id, chapter_indexes=[1], mode=ProductionMode.ONE_CLICK)
    repo.save_run(run)
    for sequence, continuity in ((1, "time_jump"), (2, "same_action"), (3, "same_action")):
        repo.save_shot(ShotRecord(id=f"shot-{sequence}", run_id=run.id, chapter_id="scene", sequence=sequence, plan=_plan(sequence, continuity)))
    service = NovelVideoService(repo=repo, projects_root=tmp_path)
    queue = TaskQueue(root=tmp_path / "tasks")
    return repo, service, queue, run


def _runner(service, queue, **kwargs):
    from backend.novel_video.runner import NovelVideoRunner
    return NovelVideoRunner(service=service, task_queue=queue, media_validator=lambda _: None, **kwargs)


async def _advance_to_rendering(runner, run_id):
    await runner.execute_run(run_id)
    assert runner.repo.get_run(run_id).status is RunStatus.RENDERING


@pytest.mark.asyncio
async def test_runner_enqueues_one_deterministic_formal_task_and_never_calls_provider(prepared):
    repo, service, queue, run = prepared
    runner = _runner(service, queue)
    await _advance_to_rendering(runner, run.id)

    await runner.execute_run(run.id)
    first = queue.list()
    await runner.execute_run(run.id)

    assert len(first) == len(queue.list()) == 1
    task = first[0]
    assert task.task_type == "video_generation"
    assert task.payload["formal_novel_video"] is True
    assert task.payload["run_id"] == run.id
    assert task.payload["package"]["shot_id"] == "shot-1"


def _approved_pair(repo, project, run, shot, tmp_path: Path, binding: dict | None = None):
    video_path, tail_path = tmp_path / f"{shot.id}.mp4", tmp_path / f"{shot.id}-tail.png"
    video_path.write_bytes(b"video"); tail_path.write_bytes(b"tail")
    candidate_video = repo.append_asset(AssetVersion(id=f"candidate-video-{shot.id}", project_id=project.id, run_id=run.id, shot_id=shot.id, kind="video", state="candidate", path=video_path, sha256=sha256(video_path.read_bytes()).hexdigest(), metadata={"generation_identity": binding or {}}))
    candidate_tail = repo.append_asset(AssetVersion(id=f"candidate-tail-{shot.id}", project_id=project.id, run_id=run.id, shot_id=shot.id, parent_id=candidate_video.id, kind="tail", state="candidate", path=tail_path, sha256=sha256(tail_path.read_bytes()).hexdigest()))
    approved_dir = tmp_path / "approved"; approved_dir.mkdir(exist_ok=True)
    approved_video_path, approved_tail_path = approved_dir / video_path.name, approved_dir / tail_path.name
    approved_video_path.write_bytes(video_path.read_bytes()); approved_tail_path.write_bytes(tail_path.read_bytes())
    video = repo.append_asset(AssetVersion(id=f"video-{shot.id}", project_id=project.id, run_id=run.id, shot_id=shot.id, parent_id=candidate_video.id, kind="video", state="approved", path=approved_video_path, sha256=sha256(approved_video_path.read_bytes()).hexdigest(), metadata={"generation_identity": binding or {}}))
    tail = repo.append_asset(AssetVersion(id=f"tail-{shot.id}", project_id=project.id, run_id=run.id, shot_id=shot.id, parent_id=candidate_tail.id, kind="tail", state="approved", path=approved_tail_path, sha256=sha256(approved_tail_path.read_bytes()).hexdigest()))
    repo.mark_generation_started(run.id, shot.id)
    repo.update_shot_status(shot.id, ShotStatus.VALIDATING)
    repo.update_shot_status(shot.id, ShotStatus.APPROVED)
    saved = repo.save_shot(repo.get_shot(shot.id).model_copy(update={"approved_video_asset_id": video.id, "approved_tail_asset_id": tail.id}))
    evidence_path = approved_dir / f"{shot.id}-evidence.json"; evidence_path.write_bytes(b"evidence")
    evidence = repo.append_asset(AssetVersion(id=f"evidence-{shot.id}", project_id=project.id, run_id=run.id, shot_id=shot.id, kind="qa_evidence", state="approved", path=evidence_path, sha256=sha256(evidence_path.read_bytes()).hexdigest()))
    repo.append_event(RunEvent(run_id=run.id, event_type="shot_approved", payload={"shot_id": shot.id, "qa": {"score": 1, "reason": "pass", "reviewer": "test", "version": "1", "evidence_sha256": {evidence.id: evidence.sha256}}}))
    return saved


@pytest.mark.asyncio
async def test_pending_tail_compiles_only_from_preceding_same_run_approved_tail(prepared, tmp_path):
    repo, service, queue, run = prepared
    runner = _runner(service, queue)
    await _advance_to_rendering(runner, run.id)
    project = repo.get_project(run.project_id)
    # First scheduling unit compiles the package; only then can a completed
    # formal worker result be authenticated as an exact approved checkpoint.
    await runner.execute_run(run.id)
    first = repo.get_shot("shot-1")
    _approved_pair(repo, project, run, first, tmp_path, runner._binding(first))

    await runner.execute_run(run.id)

    second = repo.get_shot("shot-2")
    assert second.reference_package is not None
    assert second.reference_package.picture_asset_version_ids == [repo.get_shot("shot-1").approved_tail_asset_id]
    assert "<Picture 1>" in second.reference_package.prompt_text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ProductionMode.ONE_CLICK, ProductionMode.PROFESSIONAL])
async def test_candidate_without_visual_reviewer_pauses_at_review_gate(prepared, tmp_path, mode):
    repo, service, queue, run = prepared
    run = repo.save_run(run.model_copy(update={"mode": mode}))
    runner = _runner(service, queue)
    await _advance_to_rendering(runner, run.id) if mode is ProductionMode.ONE_CLICK else service.command(run.id, "start")
    if mode is ProductionMode.PROFESSIONAL:
        assert repo.get_run(run.id).status is RunStatus.AWAITING_REVIEW
        return
    await runner.execute_run(run.id)  # compile and enqueue the authoritative task
    shot = repo.get_shot("shot-1")
    # Simulate authoritative TaskRunner candidate persistence, not a provider call here.
    project = repo.get_project(run.project_id)
    output_root = project.root / "outputs" / "formal"
    output_root.mkdir(parents=True)
    video_path, tail_path = output_root / "candidate.mp4", output_root / "candidate-tail.png"
    video_path.write_bytes(b"video"); tail_path.write_bytes(b"tail")
    repo.mark_generation_started(run.id, shot.id)
    repo.record_generation_success(run.id, shot_id=shot.id, video_path=video_path, tail_path=tail_path, prompt_id="p1", metadata={}, generation_identity=runner._binding(shot))
    candidates = {asset.kind: asset for asset in repo.list_assets(run.id) if asset.shot_id == shot.id and asset.state == "candidate"}
    queue.complete(runner._task_id(run.id, repo.get_shot(shot.id)), {"video_asset_id": candidates["video"].id, "tail_asset_id": candidates["tail"].id})

    await runner.execute_run(run.id)
    assert repo.get_run(run.id).status is RunStatus.AWAITING_REVIEW
    assert repo.get_run(run.id).review_gate == "shot_candidate"


@pytest.mark.asyncio
async def test_one_click_auto_approval_requires_complete_injected_visual_qa(prepared, tmp_path):
    repo, service, queue, run = prepared
    scheduler = _runner(service, queue)
    await _advance_to_rendering(scheduler, run.id)
    await scheduler.execute_run(run.id)  # compile and enqueue shot 1
    shot = repo.get_shot("shot-1")
    project = repo.get_project(run.project_id)
    output_root = project.root / "outputs" / "formal"
    output_root.mkdir(parents=True)
    video_path, tail_path = output_root / "candidate.mp4", output_root / "candidate-tail.png"
    video_path.write_bytes(b"video"); tail_path.write_bytes(b"tail")
    repo.mark_generation_started(run.id, shot.id)
    repo.record_generation_success(run.id, shot_id=shot.id, video_path=video_path, tail_path=tail_path,
                                   prompt_id="p1", metadata={}, generation_identity=scheduler._binding(shot))
    candidates = {asset.kind: asset for asset in repo.list_assets(run.id) if asset.shot_id == shot.id and asset.state == "candidate"}
    queue.complete(scheduler._task_id(run.id, shot), {
        "video_asset_id": candidates["video"].id,
        "tail_asset_id": candidates["tail"].id,
        "prompt_id": "p1",
    })
    evidence_path = output_root / "qa-evidence.json"
    evidence_path.write_bytes(b"review evidence")
    repo.append_asset(AssetVersion(id="gpt-evidence-1", project_id=project.id, run_id=run.id, shot_id=shot.id,
                                   kind="qa_evidence", state="approved", path=evidence_path,
                                   sha256=sha256(evidence_path.read_bytes()).hexdigest()))

    # The scheduler must use the pair transaction boundary; standalone asset
    # approval would reintroduce the crash window between two approved rows.
    service.approve_asset = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("runner must not call approve_asset")
    )
    reviewer = lambda **_: {"approved": True, "score": 0.9, "reason": "continuity passes",
                             "evidence_asset_ids": ["gpt-evidence-1"], "reviewer": "gpt-review", "version": "v1"}
    await _runner(service, queue, visual_reviewer=reviewer).execute_run(run.id)

    approved = repo.get_shot(shot.id)
    assert approved.status is ShotStatus.APPROVED
    assert approved.approved_video_asset_id and approved.approved_tail_asset_id
    event = [event for event in repo.list_events(run.id) if event.event_type == "shot_approved"][-1]
    assert event.payload["qa"]["reviewer"] == "gpt-review"


@pytest.mark.asyncio
async def test_concurrent_scheduler_lease_and_queued_task_are_not_blocked(prepared):
    repo, service, queue, run = prepared
    first, second = _runner(service, queue), _runner(service, queue)
    assert await first._claim_run(run.id)
    assert not await second._claim_run(run.id)
    await first._release_run(run.id)
    await _advance_to_rendering(first, run.id)
    await first.execute_run(run.id)
    await second.execute_run(run.id)
    assert repo.get_run(run.id).status is RunStatus.RENDERING
    assert len(queue.list(status="queued")) == 1
