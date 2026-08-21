from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.novel_video.h3_provider import H3SegmentResult
from backend.novel_video.models import (
    AspectRatio,
    AssetVersion,
    H3ReferencePackage,
    NovelVideoProject,
    ProductionMode,
    ProductionRun,
    RunEvent,
    RunStatus,
    ShotRecord,
    ShotStatus,
)
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.routes import router as novel_video_router
from backend.novel_video.runner import NovelVideoRunner
from backend.novel_video.service import NovelVideoService
from backend.novel_video.video_router import NovelVideoRouter
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.task_queue import TaskQueue
from backend.orchestration.worker import SSEBroadcaster, TaskRunner
from backend.production.comfy_adapter import ComfyArtifact


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _package(shot_id: str = "shot-1") -> H3ReferencePackage:
    return H3ReferencePackage(
        shot_id=shot_id,
        prompt_version="prompt-v1",
        prompt_text="silver robot finds a green plant",
        base_seed=20260812,
        effective_seed=20260812,
        duration_seconds=5,
        legal_frame_count=124,
        width=864,
        height=480,
        aspect_ratio=AspectRatio.LANDSCAPE,
        picture_asset_version_ids=[],
        video_reference_asset_version_ids=[],
        audio_reference_asset_version_ids=[],
        workflow_version="h3-ref2va-api-v1",
        model_registry_ids={},
    )


def _release_case(tmp_path: Path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel.db")))
    project = NovelVideoProject(
        id="project-1", name="Novel", root=tmp_path / "project",
        owner_principal="alice",
    )
    repo.create_project(project)
    run = ProductionRun(
        id="run-1", project_id=project.id, chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
    )
    repo.save_run(run)
    repo.update_run_status(run.id, RunStatus.PLANNING)
    repo.update_run_status(run.id, RunStatus.RENDERING)
    shot = ShotRecord(
        id="shot-1", run_id=run.id, chapter_id="scene-1", sequence=1,
        reference_package=_package(),
    )
    repo.save_shot(shot)
    service = NovelVideoService(repo=repo, projects_root=tmp_path)
    queue = TaskQueue(root=tmp_path / "tasks")
    scheduler = NovelVideoRunner(
        service=service, task_queue=queue, media_validator=lambda _path: None,
    )
    service.attach_runner(scheduler)
    return repo, project, service, queue, scheduler, run, shot


async def _manual_complete_current_attempt(case):
    repo, project, _service, queue, scheduler, run, original_shot = case
    await scheduler.execute_run(run.id)
    shot = repo.get_shot(original_shot.id)
    task_id = scheduler._task_id(run.id, shot)
    task = queue.claim_next("test-worker", limit=1)[0]
    assert task.task_id == task_id
    identity = scheduler._generation_identity(shot)
    repo.mark_generation_started(run.id, shot.id)
    output_root = project.root / "outputs" / "formal"
    output_root.mkdir(parents=True, exist_ok=True)
    video_path = output_root / task.payload["output_video"]
    tail_path = output_root / task.payload["output_tail"]
    video_path.write_bytes(f"video:{task_id}".encode())
    tail_path.write_bytes(f"tail:{task_id}".encode())
    video, tail = repo.record_generation_success(
        run.id,
        shot_id=shot.id,
        video_path=video_path,
        tail_path=tail_path,
        prompt_id=f"prompt-{task_id}",
        metadata={},
        generation_identity=identity,
    )
    result = {
        "path": str(video.path),
        "kind": "video",
        "video_asset_id": video.id,
        "tail_asset_id": tail.id,
        "prompt_id": video.metadata["prompt_id"],
        "generation_identity": identity,
    }
    queue.complete(task_id, result)
    return task, result, video, tail, identity


def _append_strict_evidence(repo, project, run, shot, video, identity, root: Path):
    evidence_path = root / f"evidence-{video.id}.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text('{"approved":true}', encoding="utf-8")
    return repo.append_asset(AssetVersion(
        id=f"evidence-{video.id}",
        project_id=project.id,
        run_id=run.id,
        shot_id=shot.id,
        parent_id=video.id,
        kind="qa_evidence",
        state="approved",
        path=evidence_path,
        sha256=_digest(evidence_path),
        metadata={
            "candidate_video_asset_id": video.id,
            "generation_identity": identity,
        },
    ))


async def _strict_approved_case(tmp_path: Path):
    case = _release_case(tmp_path)
    repo, project, service, _queue, scheduler, run, original_shot = case
    _task, _result, video, tail, identity = await _manual_complete_current_attempt(case)
    await scheduler.execute_run(run.id)
    assert repo.get_run(run.id).status is RunStatus.AWAITING_REVIEW
    evidence = _append_strict_evidence(
        repo, project, run, original_shot, video, identity,
        project.root / "qa",
    )
    approved = service.review_shot_candidate(
        original_shot.id,
        approve=True,
        candidate_video_id=video.id,
        candidate_tail_id=tail.id,
        qa={
            "score": 0.97,
            "reason": "continuity and media pass",
            "reviewer": "gpt-review",
            "version": "release-v1",
            "evidence_asset_ids": [evidence.id],
        },
    )
    return case, approved, video, tail, evidence, identity


@pytest.mark.asyncio
async def test_runner_skips_only_fully_authenticated_strict_approved_pair(tmp_path: Path):
    case, approved, *_ = await _strict_approved_case(tmp_path)
    repo, _project, _service, queue, scheduler, run, _shot = case

    assert scheduler._is_exact_approved(approved) is True
    task_ids = {task.task_id for task in queue.list()}
    await scheduler.execute_run(run.id)

    assert repo.get_shot(approved.id).status is ShotStatus.APPROVED
    assert {task.task_id for task in queue.list()} == task_ids
    assert repo.get_run(run.id).status is RunStatus.BLOCKED
    blocked = [event for event in repo.list_events(run.id)
               if event.event_type == "video_generation_blocked"]
    assert blocked[-1].payload["reason"] == "audio_composer_not_configured"


def _replace_event(repo: NovelVideoRepository, run_id: str, mutate) -> None:
    with repo.database.transaction(immediate=True) as conn:
        row = conn.execute(
            "SELECT sequence, payload FROM novel_video_events "
            "WHERE run_id = ? AND event_type = 'shot_approved' ORDER BY sequence DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        event = RunEvent.model_validate_json(row["payload"])
        payload = dict(event.payload)
        mutate(payload)
        changed = event.model_copy(update={"payload": payload})
        conn.execute(
            "UPDATE novel_video_events SET payload = ? WHERE sequence = ?",
            (changed.model_dump_json(), row["sequence"]),
        )


def _replace_decision(repo: NovelVideoRepository, shot_id: str, mutate) -> None:
    with repo.database.transaction(immediate=True) as conn:
        row = conn.execute(
            "SELECT transaction_token, payload FROM novel_video_shot_decisions WHERE shot_id = ?",
            (shot_id,),
        ).fetchone()
        payload = json.loads(row["payload"])
        mutate(payload)
        conn.execute(
            "UPDATE novel_video_shot_decisions SET payload = ? WHERE transaction_token = ?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), row["transaction_token"]),
        )


def _replace_asset(repo: NovelVideoRepository, asset_id: str, **changes) -> AssetVersion:
    asset = repo.get_asset(asset_id)
    payload = asset.model_dump(mode="python")
    payload.update(changes)
    changed = AssetVersion.model_validate(payload)
    with repo.database.transaction(immediate=True) as conn:
        conn.execute(
            """UPDATE novel_video_assets
               SET project_id = ?, run_id = ?, shot_id = ?, parent_id = ?, kind = ?,
                   state = ?, path = ?, sha256 = ?, payload = ? WHERE id = ?""",
            (
                changed.project_id, changed.run_id, changed.shot_id,
                changed.parent_id, changed.kind, changed.state,
                str(changed.path), changed.sha256, changed.model_dump_json(), asset_id,
            ),
        )
    return changed


def _stale(identity: dict[str, str]) -> dict[str, str]:
    return {**identity, "attempt_id": identity["attempt_id"] + "-stale"}


def _mutate_strict_approval(
    mutation: str, repo: NovelVideoRepository, run, approved, video, tail,
    evidence, identity,
) -> None:
    if mutation == "decision_generation_identity":
        _replace_decision(repo, approved.id, lambda row: row.update(
            {"generation_identity": _stale(identity)}
        ))
    elif mutation == "event_generation_identity":
        _replace_event(repo, run.id, lambda payload: payload.update(
            {"generation_identity": _stale(identity)}
        ))
    elif mutation == "event_video_asset_id":
        _replace_event(repo, run.id, lambda payload: payload.update(
            {"video_asset_id": "approved-video-stale"}
        ))
    elif mutation == "event_tail_asset_id":
        _replace_event(repo, run.id, lambda payload: payload.update(
            {"tail_asset_id": "approved-tail-stale"}
        ))
    elif mutation == "event_decision_token":
        _replace_event(repo, run.id, lambda payload: payload.update(
            {"decision_token": "stale-decision-token"}
        ))
    elif mutation == "evidence_kind":
        _replace_asset(repo, evidence.id, kind="review_note")
    elif mutation == "evidence_project":
        _replace_asset(repo, evidence.id, project_id="other-project")
    elif mutation == "evidence_run":
        _replace_asset(repo, evidence.id, run_id="other-run")
    elif mutation == "evidence_shot":
        _replace_asset(repo, evidence.id, shot_id="other-shot")
    elif mutation == "evidence_state":
        _replace_asset(repo, evidence.id, state="rejected")
    elif mutation == "evidence_hash":
        _replace_asset(repo, evidence.id, sha256="0" * 64)
    elif mutation == "evidence_file":
        evidence.path.write_bytes(b"tampered-evidence")
    elif mutation == "evidence_candidate_link":
        _replace_asset(
            repo, evidence.id, parent_id="other-video",
            metadata={
                **dict(evidence.metadata),
                "candidate_video_asset_id": "other-video",
            },
        )
    elif mutation == "evidence_generation_identity":
        _replace_asset(
            repo, evidence.id,
            metadata={
                **dict(evidence.metadata),
                "generation_identity": _stale(identity),
            },
        )
    elif mutation == "decision_evidence_digest":
        def mutate(row):
            row["qa"]["evidence_sha256"][evidence.id] = "0" * 64
        _replace_decision(repo, approved.id, mutate)
    else:  # pragma: no cover - protects the regression matrix itself
        raise AssertionError(mutation)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", [
    "decision_generation_identity",
    "event_generation_identity",
    "event_video_asset_id",
    "event_tail_asset_id",
    "event_decision_token",
    "evidence_kind",
    "evidence_project",
    "evidence_run",
    "evidence_shot",
    "evidence_state",
    "evidence_hash",
    "evidence_file",
    "evidence_candidate_link",
    "evidence_generation_identity",
    "decision_evidence_digest",
])
async def test_runner_strict_approved_skip_fails_closed_on_each_identity_mutation(
    tmp_path: Path, mutation: str,
):
    case, approved, video, tail, evidence, identity = await _strict_approved_case(tmp_path)
    repo, _project, _service, _queue, scheduler, run, _shot = case
    _mutate_strict_approval(
        mutation, repo, run, approved, video, tail, evidence, identity,
    )

    current = repo.get_shot(approved.id)
    assert scheduler._is_exact_approved(current) is False
    await scheduler.execute_run(run.id)

    assert repo.get_run(run.id).status is RunStatus.BLOCKED
    assert repo.get_shot(approved.id).status is ShotStatus.BLOCKED
    failures = [event for event in repo.list_events(run.id)
                if event.event_type == "video_generation_blocked"]
    assert failures[-1].payload["reason"] == "approved_asset_invalid"


class _ExactOutputH3:
    async def generate(self, request):
        request.output_video.parent.mkdir(parents=True, exist_ok=True)
        prompt_id = f"prompt-{request.output_video.stem}"
        request.output_video.write_bytes(f"video:{prompt_id}".encode())
        request.output_tail.write_bytes(f"tail:{prompt_id}".encode())
        return H3SegmentResult(
            prompt_id=prompt_id,
            video_path=request.output_video,
            tail_frame_path=request.output_tail,
            audio_present=False,
            comfy_output=ComfyArtifact(request.output_video.name),
            metadata={"media": {}, "models": {}, "recovery": {}},
        )


async def _run_exact_task_runner(case):
    repo, _project, _service, queue, _scheduler, _run, _shot = case
    claimed = queue.claim_next("real-task-runner", limit=1)
    assert len(claimed) == 1
    worker = TaskRunner(
        queue,
        SSEBroadcaster(),
        OrchestrationConfig(),
        workdir=queue.root / "locks",
        novel_video_repository=repo,
        formal_router_factory=lambda **_kwargs: NovelVideoRouter(
            h3=_ExactOutputH3(), wan=None,
        ),
    )
    await worker.execute_task(claimed[0])
    completed = queue.get(claimed[0].task_id)
    assert completed.status == "completed"
    return completed


def _review_client(service: NovelVideoService):
    app = FastAPI()
    app.include_router(novel_video_router, prefix="/api/core/novel-video")
    app.state.novel_video_service = service
    app.state.novel_video_capabilities = {"release-capability": "alice"}
    app.state.novel_video_sessions = {}
    app.state.novel_video_proxy_assertion_bypass = True
    app.state.novel_video_allowed_origins = {"http://localhost:5173"}
    return TestClient(app, headers={
        "X-Novel-Video-Capability": "release-capability",
        "Origin": "http://localhost:5173",
    })


@pytest.mark.asyncio
async def test_service_api_taskqueue_reject_retry_approve_and_stale_replay_e2e(
    tmp_path: Path,
):
    case = _release_case(tmp_path)
    repo, project, service, queue, scheduler, run, shot = case
    await scheduler.execute_run(run.id)
    attempt0 = await _run_exact_task_runner(case)
    result0 = dict(attempt0.result)
    output0 = (
        attempt0.payload["output_video"], attempt0.payload["output_tail"],
    )
    await scheduler.execute_run(run.id)
    assert repo.get_run(run.id).status is RunStatus.AWAITING_REVIEW

    with _review_client(service) as client:
        assert client.post("/api/core/novel-video/session").status_code == 204
        client.headers.pop("X-Novel-Video-Capability", None)
        reject_body = {
            "approve": False,
            "candidate_video_id": result0["video_asset_id"],
            "candidate_tail_id": result0["tail_asset_id"],
        }
        rejected = client.post(
            f"/api/core/novel-video/shots/{shot.id}/review", json=reject_body,
        )
        assert rejected.status_code == 200, rejected.text

        assert repo.get_asset(result0["video_asset_id"]).state == "rejected"
        assert repo.get_asset(result0["tail_asset_id"]).state == "rejected"
        assert repo.get_shot(shot.id).retry_nonce == 1
        assert repo.get_run(run.id).status is RunStatus.RENDERING

        await scheduler.execute_run(run.id)
        attempt1_id = scheduler._task_id(run.id, repo.get_shot(shot.id))
        assert attempt1_id != attempt0.task_id
        attempt1_queued = queue.get(attempt1_id)
        assert attempt1_queued is not None
        assert (
            attempt1_queued.payload["output_video"],
            attempt1_queued.payload["output_tail"],
        ) != output0

        stale_while_retrying = client.post(
            f"/api/core/novel-video/shots/{shot.id}/review", json=reject_body,
        )
        assert stale_while_retrying.status_code == 200
        assert repo.get_shot(shot.id).retry_nonce == 1
        assert queue.get(attempt1_id).status == "queued"

        attempt1 = await _run_exact_task_runner(case)
        result1 = dict(attempt1.result)
        assert attempt1.task_id == attempt1_id
        assert result1["generation_identity"]["task_id"] == attempt1_id
        await scheduler.execute_run(run.id)
        assert repo.get_run(run.id).status is RunStatus.AWAITING_REVIEW

        candidate1 = repo.get_asset(result1["video_asset_id"])
        evidence = _append_strict_evidence(
            repo, project, run, shot, candidate1,
            result1["generation_identity"], project.root / "qa",
        )
        approved = client.post(
            f"/api/core/novel-video/shots/{shot.id}/review",
            json={
                "approve": True,
                "candidate_video_id": result1["video_asset_id"],
                "candidate_tail_id": result1["tail_asset_id"],
                "qa": {
                    "score": 0.98,
                    "reason": "retry continuity passes",
                    "reviewer": "gpt-review",
                    "version": "release-v1",
                    "evidence_asset_ids": [evidence.id],
                },
            },
        )
        assert approved.status_code == 200, approved.text
        assert repo.get_run(run.id).status is RunStatus.RENDERING
        assert repo.get_shot(shot.id).status is ShotStatus.APPROVED

        before_replay = repo.get_shot(shot.id)
        stale_after_approval = client.post(
            f"/api/core/novel-video/shots/{shot.id}/review", json=reject_body,
        )
        assert stale_after_approval.status_code == 200
        after_replay = repo.get_shot(shot.id)
        assert after_replay == before_replay
        assert len([
            event for event in repo.list_events(run.id)
            if event.event_type == "shot_candidate_rejected"
        ]) == 1

    await scheduler.execute_run(run.id)
    assert repo.get_shot(shot.id).status is ShotStatus.APPROVED
    assert repo.get_run(run.id).status is RunStatus.BLOCKED
    assert len(queue.list()) == 2


@pytest.mark.parametrize("shot_status", [
    ShotStatus.DRAFT,
    ShotStatus.QUEUED,
    ShotStatus.RUNNING,
    ShotStatus.VALIDATING,
    ShotStatus.BLOCKED,
    ShotStatus.FAILED,
    ShotStatus.APPROVED,
])
@pytest.mark.parametrize("candidate_kind", ["video", "tail"])
def test_standalone_formal_video_and_tail_approval_is_denied_in_every_shot_state(
    tmp_path: Path, shot_status: ShotStatus, candidate_kind: str,
):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "denial.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path / "project")
    repo.create_project(project)
    run = ProductionRun(
        id="run-1", project_id=project.id, chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
    )
    repo.save_run(run)
    shot = repo.save_shot(ShotRecord(
        id="shot-1", run_id=run.id, chapter_id="scene-1", sequence=1,
        reference_package=_package(),
    ))
    transition_paths = {
        ShotStatus.DRAFT: (),
        ShotStatus.QUEUED: (ShotStatus.LOCKED, ShotStatus.QUEUED),
        ShotStatus.RUNNING: (ShotStatus.LOCKED, ShotStatus.QUEUED, ShotStatus.RUNNING),
        ShotStatus.VALIDATING: (
            ShotStatus.LOCKED, ShotStatus.QUEUED, ShotStatus.RUNNING,
            ShotStatus.VALIDATING,
        ),
        ShotStatus.BLOCKED: (ShotStatus.BLOCKED,),
        ShotStatus.FAILED: (
            ShotStatus.LOCKED, ShotStatus.QUEUED, ShotStatus.RUNNING,
            ShotStatus.FAILED,
        ),
        ShotStatus.APPROVED: (
            ShotStatus.LOCKED, ShotStatus.QUEUED, ShotStatus.RUNNING,
            ShotStatus.VALIDATING, ShotStatus.APPROVED,
        ),
    }
    for target in transition_paths[shot_status]:
        shot = repo.update_shot_status(shot.id, target)
    candidate_dir = project.root / "outputs" / "formal"
    candidate_dir.mkdir(parents=True)
    video_path = candidate_dir / "candidate.mp4"
    tail_path = candidate_dir / "candidate.png"
    video_path.write_bytes(b"formal-video")
    tail_path.write_bytes(b"formal-tail")
    identity = {
        "task_id": "formal-task",
        "run_id": run.id,
        "shot_id": shot.id,
        "attempt_id": "formal-task:1",
        "package_sha256": sha256(json.dumps(
            shot.reference_package.model_dump(mode="json"),
            sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest(),
    }
    video = repo.append_asset(AssetVersion(
        id="candidate-video", project_id=project.id, run_id=run.id,
        shot_id=shot.id, kind="video", state="candidate", path=video_path,
        sha256=_digest(video_path),
        metadata={"prompt_id": "prompt-1", "generation_identity": identity},
    ))
    tail = repo.append_asset(AssetVersion(
        id="candidate-tail", project_id=project.id, run_id=run.id,
        shot_id=shot.id, parent_id=video.id, kind="tail", state="candidate",
        path=tail_path, sha256=_digest(tail_path),
        metadata={"prompt_id": "prompt-1", "generation_identity": identity},
    ))
    service = NovelVideoService(repo=repo, projects_root=tmp_path)
    candidate = video if candidate_kind == "video" else tail

    with pytest.raises(
        ValueError, match="formal shot video/tail approval requires the exact pair review endpoint",
    ):
        service.approve_asset(candidate.id, approve_tail=candidate_kind == "tail")

    current = repo.get_shot(shot.id)
    assert current.approved_video_asset_id is None
    assert current.approved_tail_asset_id is None
    assert not [asset for asset in repo.list_assets(run.id)
                if asset.kind in {"video", "tail"} and asset.state == "approved"]
