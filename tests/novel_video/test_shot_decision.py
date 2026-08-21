from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

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
from backend.novel_video.repository import ConcurrentTransitionError, NovelVideoRepository
from backend.novel_video.service import NovelVideoService
from backend.orchestration.database import OrchestrationDatabase


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def decision_case(tmp_path: Path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "decision.db")))
    project = NovelVideoProject(id="project-1", name="decision", root=tmp_path / "project")
    repo.create_project(project)
    run = ProductionRun(
        id="run-1", project_id=project.id, chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
    )
    repo.save_run(run)
    repo.update_run_status(run.id, RunStatus.PLANNING)
    repo.update_run_status(run.id, RunStatus.RENDERING)
    package = H3ReferencePackage(
        shot_id="shot-1", prompt_version="v1", prompt_text="continue", base_seed=7,
        effective_seed=7, duration_seconds=5, legal_frame_count=124, width=864,
        height=480, aspect_ratio=AspectRatio.LANDSCAPE,
        picture_asset_version_ids=[], video_reference_asset_version_ids=[],
        audio_reference_asset_version_ids=[], workflow_version="h3-ref2va-v1",
        model_registry_ids={},
    )
    shot = ShotRecord(
        id="shot-1", run_id=run.id, chapter_id="scene-1", sequence=1,
        status=ShotStatus.DRAFT, reference_package=package,
    )
    repo.save_shot(shot)
    repo.mark_generation_started(run.id, shot.id)
    binding = {
        "run_id": run.id,
        "shot_id": shot.id,
        "package_sha256": sha256(json.dumps(
            package.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode()).hexdigest(),
    }
    output = project.root / "outputs" / "formal"
    output.mkdir(parents=True)
    video_path, tail_path = output / "candidate.mp4", output / "candidate-tail.png"
    video_path.write_bytes(b"candidate-video-bytes")
    tail_path.write_bytes(b"candidate-tail-bytes")
    video, tail = repo.record_generation_success(
        run.id, shot_id=shot.id, video_path=video_path, tail_path=tail_path,
        prompt_id="prompt-1", metadata={}, generation_identity=binding,
    )
    evidence_path = output / "qa.json"
    evidence_path.write_bytes(b"visual-review-evidence")
    evidence = repo.append_asset(AssetVersion(
        id="evidence-1", project_id=project.id, run_id=run.id, shot_id=shot.id,
        kind="qa_evidence", state="approved", path=evidence_path,
        sha256=_digest(evidence_path),
    ))
    task_id = "formal-task-1"
    repo.append_event(RunEvent(
        run_id=run.id, event_type="formal_task_enqueued",
        payload={"shot_id": shot.id, "task_id": task_id, "binding": binding},
    ))
    qa = {
        "score": 0.95, "reason": "continuity passes", "reviewer": "gpt-review",
        "version": "v1", "evidence_asset_ids": [evidence.id],
    }
    service = NovelVideoService(repo=repo, projects_root=tmp_path)
    return service, repo, project, run, shot, video, tail, binding, qa, task_id


def _commit(case):
    service, _, _, run, shot, video, tail, binding, qa, task_id = case
    return service.commit_shot_candidate_decision(
        shot.id, candidate_video_id=video.id, candidate_tail_id=tail.id,
        binding=binding, qa=qa, expected_lease_id=None, task_id=task_id,
        task_result={"video_asset_id": video.id, "tail_asset_id": tail.id,
                     "prompt_id": "prompt-1"},
    )


def test_strict_formal_candidate_requires_attached_queue_authority(decision_case):
    service, repo, project, run, shot, _video, _tail, binding, _qa, _task_id = decision_case
    identity = {
        "task_id": "formal-strict", "run_id": run.id, "shot_id": shot.id,
        "attempt_id": "formal-strict:1", "package_sha256": binding["package_sha256"],
    }
    path, tail_path = project.root / "outputs" / "strict.mp4", project.root / "outputs" / "strict.png"
    path.write_bytes(b"strict-video"); tail_path.write_bytes(b"strict-tail")
    video = repo.append_asset(AssetVersion(
        id="strict-video", project_id=project.id, run_id=run.id, shot_id=shot.id,
        kind="video", state="candidate", path=path, sha256=_digest(path),
        metadata={"prompt_id": "strict-prompt", "generation_identity": identity},
    ))
    tail = repo.append_asset(AssetVersion(
        id="strict-tail", project_id=project.id, run_id=run.id, shot_id=shot.id,
        parent_id=video.id, kind="tail", state="candidate", path=tail_path,
        sha256=_digest(tail_path),
    ))

    with pytest.raises(ValueError, match="attached TaskQueue"):
        service._candidate_task_identity(run.id, shot.id, video, tail, binding)
    assert repo.get_shot(shot.id).retry_nonce == 0


@pytest.mark.parametrize(
    "fault_point, expected_final_count",
    [
        ("before_first_publish", 0),
        ("between_publishes", 1),
        ("after_both_before_db", 2),
        ("after_db_before_manifest_commit", 2),
    ],
)
def test_candidate_pair_decision_exactly_recovers_every_crash_window(
    decision_case, fault_point: str, expected_final_count: int,
):
    service, repo, project, run, shot, *_ = decision_case
    fired = {"value": False}

    def crash(point: str) -> None:
        if point == fault_point and not fired["value"]:
            fired["value"] = True
            raise KeyboardInterrupt(f"crash at {point}")

    service._shot_decision_fault = crash
    with pytest.raises(KeyboardInterrupt, match=fault_point):
        _commit(decision_case)

    approved_dir = project.root / "shots" / shot.id / "approved"
    finals = [path for path in approved_dir.glob("*") if path.is_file() and not path.name.startswith(".")]
    assert len(finals) == expected_final_count
    if fault_point != "after_db_before_manifest_commit":
        assert repo.list_assets(run.id, state="approved") == [
            asset for asset in repo.list_assets(run.id, state="approved")
            if asset.kind == "qa_evidence"
        ]

    service._shot_decision_fault = lambda _point: None
    first = _commit(decision_case)
    replay = _commit(decision_case)

    assert first == replay
    assert first.status is ShotStatus.APPROVED
    pair = [asset for asset in repo.list_assets(run.id, state="approved")
            if asset.kind in {"video", "tail"}]
    assert len(pair) == 2
    decisions = [event for event in repo.list_events(run.id)
                 if event.event_type == "shot_approved"]
    assert len(decisions) == 1
    manifest = next(approved_dir.glob(".shot-decision-*.json"))
    assert json.loads(manifest.read_text(encoding="utf-8"))["state"] == "committed"


def test_candidate_pair_decision_preserves_unrelated_concurrent_final(decision_case):
    service, repo, project, run, shot, *_ = decision_case
    approved_dir = project.root / "shots" / shot.id / "approved"
    approved_dir.mkdir(parents=True)
    video = decision_case[5]
    token = sha256(video.id.encode()).hexdigest()[:24]
    unrelated = approved_dir / f"video-{token}.mp4"
    unrelated.write_bytes(b"another-writer")

    with pytest.raises(ValueError, match="different immutable hash|recovery required"):
        _commit(decision_case)

    assert unrelated.read_bytes() == b"another-writer"
    assert not [asset for asset in repo.list_assets(run.id, state="approved")
                if asset.kind in {"video", "tail"}]


@pytest.mark.parametrize("new_status", [RunStatus.PAUSED, RunStatus.CANCELLED])
def test_pause_or_cancel_immediately_before_db_commit_never_approves(
    decision_case, new_status: RunStatus,
):
    service, repo, _, run, *_ = decision_case

    def race(point: str) -> None:
        if point == "after_both_before_db":
            repo.update_run_status(run.id, new_status)

    service._shot_decision_fault = race
    with pytest.raises(ConcurrentTransitionError):
        _commit(decision_case)

    assert not [asset for asset in repo.list_assets(run.id, state="approved")
                if asset.kind in {"video", "tail"}]
    assert repo.get_shot("shot-1").status is ShotStatus.VALIDATING


def test_candidate_pair_decision_rejects_mixed_task_result_without_publication(decision_case):
    service, repo, project, run, shot, video, tail, binding, qa, task_id = decision_case
    with pytest.raises(ValueError, match="task result"):
        service.commit_shot_candidate_decision(
            shot.id, candidate_video_id=video.id, candidate_tail_id=tail.id,
            binding=binding, qa=qa, expected_lease_id=None, task_id=task_id,
            task_result={"video_asset_id": "other", "tail_asset_id": tail.id,
                         "prompt_id": "prompt-1"},
        )
    approved_dir = project.root / "shots" / shot.id / "approved"
    assert not approved_dir.exists() or not list(approved_dir.iterdir())
    assert not [asset for asset in repo.list_assets(run.id, state="approved")
                if asset.kind in {"video", "tail"}]


def test_explicit_review_uses_pair_boundary_and_never_standalone_approval(decision_case):
    service, repo, _, run, shot, video, tail, _, qa, _ = decision_case
    repo.save_run(repo.get_run(run.id).model_copy(update={
        "status": RunStatus.AWAITING_REVIEW, "review_gate": "shot_candidate",
    }))
    service.approve_asset = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("explicit review must not call approve_asset")
    )

    approved = service.review_shot_candidate(
        shot.id, approve=True, candidate_video_id=video.id,
        candidate_tail_id=tail.id, qa=qa,
    )

    assert approved.status is ShotStatus.APPROVED
    assert len([event for event in repo.list_events(run.id)
                if event.event_type == "shot_approved"]) == 1


def test_explicit_rejection_atomically_requeues_and_resumes_run_without_files(decision_case):
    service, repo, project, run, shot, video, tail, *_ = decision_case
    repo.save_run(repo.get_run(run.id).model_copy(update={
        "status": RunStatus.AWAITING_REVIEW, "review_gate": "shot_candidate",
    }))

    queued = service.review_shot_candidate(
        shot.id, approve=False, candidate_video_id=video.id,
        candidate_tail_id=tail.id, qa=None,
    )

    resumed = repo.get_run(run.id)
    assert queued.status is ShotStatus.QUEUED
    assert resumed.status is RunStatus.RENDERING
    assert resumed.review_gate is None
    approved_dir = project.root / "shots" / shot.id / "approved"
    assert not approved_dir.exists()
    assert len([event for event in repo.list_events(run.id)
                if event.event_type == "shot_candidate_rejected"]) == 1


def test_committed_database_pair_is_not_replayed_if_final_bytes_change(decision_case):
    service, repo, _, run, *_ = decision_case
    approved = _commit(decision_case)
    video = repo.get_asset(approved.approved_video_asset_id)
    video.path.write_bytes(b"tampered-after-commit")

    with pytest.raises(ValueError, match="approved file"):
        _commit(decision_case)

    assert len([event for event in repo.list_events(run.id)
                if event.event_type == "shot_approved"]) == 1


def test_candidate_is_captured_once_and_later_source_mutation_cannot_change_approval(decision_case):
    service, repo, _, _, _, video, _, _, _, _ = decision_case
    original = video.path.read_bytes()

    def mutate_after_capture(point: str) -> None:
        if point == "before_first_publish":
            video.path.write_bytes(b"mutated-after-private-capture")

    service._shot_decision_fault = mutate_after_capture
    approved = _commit(decision_case)

    frozen = repo.get_asset(approved.approved_video_asset_id)
    assert frozen.path.read_bytes() == original
    assert frozen.sha256 == sha256(original).hexdigest()
