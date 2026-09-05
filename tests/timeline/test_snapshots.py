import hashlib
import json

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.models import TimelineOperationRequest
from backend.timeline.repository import TimelineRepository
from backend.timeline.service import TimelineService


def _seed_project(tmp_path):
    projects_root = tmp_path / "projects"
    project_id = "project-a"
    media_dir = projects_root / project_id / "outputs"
    media_dir.mkdir(parents=True)
    media_path = media_dir / "shot_001.mp4"
    media_path.write_bytes(b"immutable-source-bytes")
    digest = hashlib.sha256(media_path.read_bytes()).hexdigest()

    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO jobs (id, project_id, status, input_path, input_type, settings, idempotency_key)
               VALUES ('job-1', ?, 'completed', '', 'novel', '{}', 'snapshot-seed')""",
            (project_id,),
        )
        conn.execute(
            """INSERT INTO job_steps (id, job_id, sequence, stage_key, shot_id, status)
               VALUES ('step-1','job-1',0,'video_generate','shot_001','completed')"""
        )
        conn.execute(
            """INSERT INTO artifacts
               (id, job_id, step_id, kind, path, sha256, metadata, active,
                project_id, version, stage_key, scene_id, shot_id, quality_status)
               VALUES (1,'job-1','step-1','video','outputs/shot_001.mp4',?,?,1,?,1,
                       'video_generate','scene-1','shot_001','passed')""",
            (digest, json.dumps({"duration_tick": 2_000_000}), project_id),
        )
    repo = TimelineRepository(db, projects_root=projects_root)
    service = TimelineService(repo)
    draft, _ = service.initialize_project(project_id)
    return db, service, draft, digest


def test_snapshot_freezes_complete_artifact_identity_and_is_deterministic(tmp_path):
    db, service, draft, digest = _seed_project(tmp_path)

    first = service.create_snapshot(draft.timeline_id)
    second = service.create_snapshot(draft.timeline_id)

    assert first.state_sha256 == second.state_sha256
    with db.connect() as conn:
        row = conn.execute("SELECT state_json FROM timeline_snapshots WHERE id=?", (first.id,)).fetchone()
    state = json.loads(row["state_json"])
    assert state["timebase"] == {"ticks_per_second": 1_000_000, "fps_num": 24, "fps_den": 1}
    assert state["tracks"][0]["role"] == "video.main"
    assert state["tracks"][0]["clips"][0]["artifact_id"] == 1
    assert state["source_artifacts"] == [{
        "artifact_id": 1,
        "artifact_version": 1,
        "path": "outputs/shot_001.mp4",
        "sha256": digest,
        "duration_tick": 2_000_000,
        "kind": "video",
        "shot_id": "shot_001",
        "scene_id": "scene-1",
    }]


def test_snapshot_payload_never_changes_after_draft_edit(tmp_path):
    db, service, draft, _ = _seed_project(tmp_path)
    snapshot = service.create_snapshot(draft.timeline_id)
    with db.connect() as conn:
        before = conn.execute("SELECT state_json, state_sha256 FROM timeline_snapshots WHERE id=?", (snapshot.id,)).fetchone()

    service.apply_operation(
        draft.timeline_id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={
                "type": "TRIM_CLIP",
                "clip_id": draft.tracks[0].clips[0].id,
                "edge": "right",
                "target_source_tick": 1_000_000,
            },
        ),
    )

    with db.connect() as conn:
        after = conn.execute("SELECT state_json, state_sha256 FROM timeline_snapshots WHERE id=?", (snapshot.id,)).fetchone()
    assert dict(after) == dict(before)
