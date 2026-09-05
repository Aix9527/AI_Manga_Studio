import json

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.models import TimelineOperationRequest
from backend.timeline.repository import TimelineRepository
from backend.timeline.service import TimelineService, TimelineValidationError


def _seed_artifact(
    db: OrchestrationDatabase,
    *,
    artifact_id: int,
    shot_id: str,
    version: int,
    duration_tick: int,
    active: int = 1,
) -> None:
    project_id = "project-a"
    job_id = f"job-{artifact_id}"
    step_id = f"step-{artifact_id}"
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO jobs
               (id, project_id, status, input_path, input_type, settings, idempotency_key)
               VALUES (?,?, 'completed', '', 'novel', '{}', ?)""",
            (job_id, project_id, f"seed-{artifact_id}"),
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
               VALUES (?,?,?,?,?,?,?,?,?,?,'video_generate','',?,'passed')""",
            (
                artifact_id,
                job_id,
                step_id,
                "video",
                f"outputs/{shot_id}-v{version}.mp4",
                f"sha-{artifact_id}",
                json.dumps({"duration_tick": duration_tick}),
                active,
                project_id,
                version,
                shot_id,
            ),
        )


@pytest.fixture
def timeline(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    _seed_artifact(db, artifact_id=1, shot_id="shot_001", version=1, duration_tick=2_000_000)
    _seed_artifact(db, artifact_id=2, shot_id="shot_002", version=1, duration_tick=2_000_000)
    repo = TimelineRepository(db, projects_root=tmp_path / "projects")
    service = TimelineService(repo)
    draft, _ = service.initialize_project("project-a")
    try:
        yield db, service, draft
    finally:
        db.close()


def _v1(draft):
    return next(track for track in draft.tracks if track.role == "video.main")


def test_crossfade_uses_explicit_source_handles_and_authorizes_exact_overlap(timeline):
    db, service, draft = timeline
    first, second = _v1(draft).clips
    first_trim = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={"type": "TRIM_CLIP", "clip_id": first.id, "edge": "right", "target_source_tick": 1_500_000},
        ),
    )
    second_after_first = _v1(first_trim.draft).clips[1]
    second_trim = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=1,
            operation={"type": "TRIM_CLIP", "clip_id": second_after_first.id, "edge": "left", "target_source_tick": 500_000},
        ),
    )

    result = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=2,
            operation={
                "type": "ADD_TRANSITION",
                "from_clip_id": _v1(second_trim.draft).clips[0].id,
                "to_clip_id": _v1(second_trim.draft).clips[1].id,
                "transition_type": "crossfade",
                "duration_tick": 500_000,
            },
        ),
    )

    clips = _v1(result.draft).clips
    assert clips[1].timeline_start_tick == clips[0].timeline_start_tick + clips[0].duration_tick - 500_000
    with db.connect() as conn:
        transition = conn.execute("SELECT * FROM timeline_transitions").fetchone()
    assert transition["transition_type"] == "crossfade"
    assert transition["duration_tick"] == 500_000


def test_transition_without_enough_handles_fails_without_overlap(timeline):
    db, service, draft = timeline
    first, second = _v1(draft).clips

    with pytest.raises(TimelineValidationError, match="transition handles"):
        service.apply_operation(
            draft.timeline_id,
            TimelineOperationRequest(
                expected_revision=0,
                operation={
                    "type": "ADD_TRANSITION",
                    "from_clip_id": first.id,
                    "to_clip_id": second.id,
                    "transition_type": "crossfade",
                    "duration_tick": 250_000,
                },
            ),
        )

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM timeline_transitions").fetchone()[0] == 0


def test_subtitle_is_first_class_and_text_update_is_persisted(timeline):
    _, service, draft = timeline
    subtitle_track = next(track for track in draft.tracks if track.role == "subtitle.primary")
    created = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={
                "type": "ADD_SUBTITLE",
                "track_id": subtitle_track.id,
                "start_tick": 100_000,
                "end_tick": 900_000,
                "text": "初始字幕",
                "speaker": "苏晚",
            },
        ),
    )
    cue = created.draft.subtitle_cues[0]
    assert cue.text == "初始字幕"

    updated = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=1,
            operation={"type": "UPDATE_SUBTITLE", "cue_id": cue.id, "text": "修改后的字幕"},
        ),
    )
    assert updated.draft.subtitle_cues[0].text == "修改后的字幕"


def test_invalid_subtitle_range_is_rejected(timeline):
    _, service, draft = timeline
    subtitle_track = next(track for track in draft.tracks if track.role == "subtitle.primary")
    with pytest.raises(TimelineValidationError, match="subtitle range"):
        service.apply_operation(
            draft.timeline_id,
            TimelineOperationRequest(
                expected_revision=0,
                operation={
                    "type": "ADD_SUBTITLE",
                    "track_id": subtitle_track.id,
                    "start_tick": 900_000,
                    "end_tick": 100_000,
                    "text": "非法",
                },
            ),
        )


def test_replace_artifact_version_preserves_edit_timing_when_compatible(timeline):
    db, service, draft = timeline
    clip = _v1(draft).clips[0]
    _seed_artifact(db, artifact_id=11, shot_id="shot_001", version=2, duration_tick=3_000_000)

    result = service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={
                "type": "REPLACE_ARTIFACT_VERSION",
                "clip_ids": [clip.id],
                "artifact_id": 11,
            },
        ),
    )

    replaced = _v1(result.draft).clips[0]
    assert replaced.artifact_id == 11
    assert replaced.artifact_version == 2
    assert replaced.timeline_start_tick == clip.timeline_start_tick
    assert replaced.duration_tick == clip.duration_tick
    assert replaced.source_in_tick == clip.source_in_tick
    assert replaced.source_out_tick == clip.source_out_tick


def test_too_short_replacement_fails_atomically(timeline):
    db, service, draft = timeline
    clip = _v1(draft).clips[0]
    _seed_artifact(db, artifact_id=12, shot_id="shot_001", version=2, duration_tick=1_000_000)

    with pytest.raises(TimelineValidationError, match="replacement_media_too_short"):
        service.apply_operation(
            draft.timeline_id,
            TimelineOperationRequest(
                expected_revision=0,
                operation={
                    "type": "REPLACE_ARTIFACT_VERSION",
                    "clip_ids": [clip.id],
                    "artifact_id": 12,
                },
            ),
        )

    current = _v1(service.get_draft(draft.timeline_id)).clips[0]
    assert current.artifact_id == clip.artifact_id


def test_replace_all_targets_rolls_back_if_any_clip_is_incompatible(timeline):
    db, service, draft = timeline
    clips = _v1(draft).clips
    _seed_artifact(db, artifact_id=13, shot_id="shot_001", version=2, duration_tick=1_500_000)

    with pytest.raises(TimelineValidationError, match="replacement_media_too_short"):
        service.apply_operation(
            draft.timeline_id,
            TimelineOperationRequest(
                expected_revision=0,
                operation={
                    "type": "REPLACE_ARTIFACT_VERSION",
                    "clip_ids": [clips[0].id, clips[1].id],
                    "artifact_id": 13,
                },
            ),
        )

    current = _v1(service.get_draft(draft.timeline_id)).clips
    assert [clip.artifact_id for clip in current] == [1, 2]
