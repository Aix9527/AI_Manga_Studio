import json

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.models import TimelineOperationRequest
from backend.timeline.repository import TimelineRepository
from backend.timeline.service import TimelineRevisionConflict, TimelineService, TimelineValidationError


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


@pytest.fixture
def timeline(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    _seed(db)
    service = TimelineService(TimelineRepository(db, projects_root=tmp_path / "projects"))
    draft, _ = service.initialize_project("project-a")
    try:
        yield db, service, draft
    finally:
        db.close()


def _v1(draft):
    return next(track for track in draft.tracks if track.role == "video.main")


def test_move_v1_is_semantic_reorder_and_keeps_track_contiguous(timeline):
    _, service, draft = timeline
    clips = _v1(draft).clips

    result = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={
                "type": "MOVE_CLIP",
                "clip_id": clips[2].id,
                "insert_before_clip_id": clips[0].id,
            },
        ),
    )

    moved = _v1(result.draft).clips
    assert [clip.shot_id for clip in moved] == ["shot_003", "shot_001", "shot_002"]
    assert [clip.timeline_start_tick for clip in moved] == [0, 2_000_000, 4_000_000]
    assert result.revision == 1
    assert result.operation_seq == 1


def test_stale_revision_fails_without_partial_write(timeline):
    _, service, draft = timeline
    clips = _v1(draft).clips
    request = TimelineOperationRequest(
        expected_revision=0,
        operation={"type": "MOVE_CLIP", "clip_id": clips[2].id, "insert_before_clip_id": clips[0].id},
    )
    service.apply_operation(draft.timeline_id, request)

    with pytest.raises(TimelineRevisionConflict):
        service.apply_operation(draft.timeline_id, request)

    current = service.get_draft(draft.timeline_id)
    assert current.revision == 1
    assert [clip.shot_id for clip in _v1(current).clips] == ["shot_003", "shot_001", "shot_002"]


def test_trim_right_ripples_following_v1_clips(timeline):
    _, service, draft = timeline
    clips = _v1(draft).clips

    result = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={
                "type": "TRIM_CLIP",
                "clip_id": clips[0].id,
                "edge": "right",
                "target_source_tick": 1_500_000,
            },
        ),
    )

    trimmed = _v1(result.draft).clips
    assert trimmed[0].source_out_tick == 1_500_000
    assert trimmed[0].duration_tick == 1_500_000
    assert [clip.timeline_start_tick for clip in trimmed] == [0, 1_500_000, 3_500_000]


def test_trim_source_overflow_is_rejected_atomically(timeline):
    _, service, draft = timeline
    clip = _v1(draft).clips[0]

    with pytest.raises(TimelineValidationError, match="source range"):
        service.apply_operation(
            draft.timeline_id,
            TimelineOperationRequest(
                expected_revision=0,
                operation={
                    "type": "TRIM_CLIP",
                    "clip_id": clip.id,
                    "edge": "right",
                    "target_source_tick": 2_500_000,
                },
            ),
        )

    current = service.get_draft(draft.timeline_id)
    assert current.revision == 0
    assert _v1(current).clips[0].source_out_tick == 2_000_000


def test_split_at_frame_boundary_creates_complementary_clips(timeline):
    _, service, draft = timeline
    clip = _v1(draft).clips[0]

    result = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={"type": "SPLIT_CLIP", "clip_id": clip.id, "timeline_tick": 1_000_000},
        ),
    )

    clips = _v1(result.draft).clips
    assert len(clips) == 4
    left, right = clips[0], clips[1]
    assert left.artifact_id == right.artifact_id == clip.artifact_id
    assert (left.source_in_tick, left.source_out_tick) == (0, 1_000_000)
    assert (right.source_in_tick, right.source_out_tick) == (1_000_000, 2_000_000)
    assert [item.timeline_start_tick for item in clips] == [0, 1_000_000, 2_000_000, 4_000_000]


def test_ripple_delete_closes_v1_gap(timeline):
    _, service, draft = timeline
    clips = _v1(draft).clips

    result = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={"type": "REMOVE_CLIP", "clip_id": clips[1].id, "mode": "ripple"},
        ),
    )

    remaining = _v1(result.draft).clips
    assert [clip.shot_id for clip in remaining] == ["shot_001", "shot_003"]
    assert [clip.timeline_start_tick for clip in remaining] == [0, 2_000_000]


def test_link_and_unlink_change_relationship_without_realigning_media(timeline):
    _, service, draft = timeline
    video = _v1(draft).clips[:2]

    linked = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={"type": "LINK_CLIPS", "clip_ids": [video[0].id, video[1].id]},
        ),
    )
    linked_clips = _v1(linked.draft).clips
    assert linked_clips[0].link_group_id
    assert linked_clips[0].link_group_id == linked_clips[1].link_group_id
    starts = [clip.timeline_start_tick for clip in linked_clips[:2]]

    unlinked = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=1,
            operation={"type": "UNLINK_CLIPS", "clip_ids": [video[0].id, video[1].id]},
        ),
    )
    unlinked_clips = _v1(unlinked.draft).clips
    assert unlinked_clips[0].link_group_id is None
    assert unlinked_clips[1].link_group_id is None
    assert [clip.timeline_start_tick for clip in unlinked_clips[:2]] == starts
