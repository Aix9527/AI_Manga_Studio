import json

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.models import TimelineOperationRequest
from backend.timeline.repository import TimelineRepository
from backend.timeline.service import TimelineRedoUnavailable, TimelineService


def _seed(db: OrchestrationDatabase, project_id: str = "project-a") -> None:
    with db.transaction() as conn:
        for index in range(1, 4):
            job_id = f"job-{index}"
            step_id = f"step-{index}"
            shot_id = f"shot_{index:03d}"
            conn.execute(
                """INSERT INTO jobs
                   (id, project_id, status, input_path, input_type, settings, idempotency_key)
                   VALUES (?,?, 'completed', '', 'novel', '{}', ?)""",
                (job_id, project_id, f"seed-{index}"),
            )
            conn.execute(
                """INSERT INTO job_steps
                   (id, job_id, sequence, stage_key, shot_id, status)
                   VALUES (?,?,0,'video_generate',?,'completed')""",
                (step_id, job_id, shot_id),
            )
            conn.execute(
                """INSERT INTO artifacts
                   (id, job_id, step_id, kind, path, sha256, metadata, active,
                    project_id, version, stage_key, scene_id, shot_id, quality_status)
                   VALUES (?,?,?,?,?,?,?,1,?,1,'video_generate','',?,'passed')""",
                (
                    index,
                    job_id,
                    step_id,
                    "video",
                    f"outputs/{shot_id}.mp4",
                    f"sha-{index}",
                    json.dumps({"duration_tick": 2_000_000}),
                    project_id,
                    shot_id,
                ),
            )


def _setup(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    _seed(db)
    repo = TimelineRepository(db, projects_root=tmp_path / "projects")
    service = TimelineService(repo)
    draft, _ = service.initialize_project("project-a")
    return db, repo, service, draft


def _v1(draft):
    return next(track for track in draft.tracks if track.role == "video.main")


def _move_request(draft, revision: int):
    clips = _v1(draft).clips
    return TimelineOperationRequest(
        expected_revision=revision,
        operation={"type": "MOVE_CLIP", "clip_id": clips[2].id, "insert_before_clip_id": clips[0].id},
    )


def test_undo_restores_state_but_revision_keeps_increasing(tmp_path):
    db, _, service, draft = _setup(tmp_path)
    try:
        moved = service.apply_operation(draft.timeline_id, _move_request(draft, 0))
        undone = service.undo(draft.timeline_id, expected_revision=moved.revision)

        assert undone.revision == 2
        assert [clip.shot_id for clip in _v1(undone.draft).clips] == ["shot_001", "shot_002", "shot_003"]
    finally:
        db.close()


def test_redo_reapplies_the_persisted_forward_operation(tmp_path):
    db, _, service, draft = _setup(tmp_path)
    try:
        moved = service.apply_operation(draft.timeline_id, _move_request(draft, 0))
        undone = service.undo(draft.timeline_id, expected_revision=moved.revision)
        redone = service.redo(draft.timeline_id, expected_revision=undone.revision)

        assert redone.revision == 3
        assert [clip.shot_id for clip in _v1(redone.draft).clips] == ["shot_003", "shot_001", "shot_002"]
    finally:
        db.close()


def test_new_edit_after_undo_abandons_old_redo_branch_without_reusing_seq(tmp_path):
    db, _, service, draft = _setup(tmp_path)
    try:
        moved = service.apply_operation(draft.timeline_id, _move_request(draft, 0))
        undone = service.undo(draft.timeline_id, expected_revision=moved.revision)
        first = _v1(undone.draft).clips[0]
        edited = service.apply_operation(
            draft.timeline_id,
            TimelineOperationRequest(
                expected_revision=undone.revision,
                operation={
                    "type": "TRIM_CLIP",
                    "clip_id": first.id,
                    "edge": "right",
                    "target_source_tick": 1_500_000,
                },
            ),
        )

        assert edited.operation_seq == 2
        with pytest.raises(TimelineRedoUnavailable):
            service.redo(draft.timeline_id, expected_revision=edited.revision)
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT seq, branch_state FROM timeline_operations ORDER BY seq"
            ).fetchall()
        assert [(row["seq"], row["branch_state"]) for row in rows] == [(1, "abandoned"), (2, "active")]
    finally:
        db.close()


def test_undo_survives_service_reconstruction_after_reload(tmp_path):
    db, repo, service, draft = _setup(tmp_path)
    try:
        moved = service.apply_operation(draft.timeline_id, _move_request(draft, 0))
        reloaded_service = TimelineService(TimelineRepository(db, projects_root=repo.projects_root))
        undone = reloaded_service.undo(draft.timeline_id, expected_revision=moved.revision)

        assert [clip.shot_id for clip in _v1(undone.draft).clips] == ["shot_001", "shot_002", "shot_003"]
    finally:
        db.close()


def test_checkpoint_is_created_after_fifty_committed_edits(tmp_path):
    db, _, service, draft = _setup(tmp_path)
    try:
        current = draft
        for _ in range(50):
            clips = _v1(current).clips
            result = service.apply_operation(
                draft.timeline_id,
                TimelineOperationRequest(
                    expected_revision=current.revision,
                    operation={
                        "type": "MOVE_CLIP",
                        "clip_id": clips[-1].id,
                        "insert_before_clip_id": clips[0].id,
                    },
                ),
            )
            current = result.draft
        with db.connect() as conn:
            checkpoints = conn.execute(
                "SELECT operation_seq, revision, state_sha256 FROM timeline_checkpoints WHERE draft_id=?",
                (draft.draft_id,),
            ).fetchall()
        assert len(checkpoints) == 1
        assert checkpoints[0]["operation_seq"] == 50
        assert checkpoints[0]["revision"] == 50
        assert len(checkpoints[0]["state_sha256"]) == 64
    finally:
        db.close()
