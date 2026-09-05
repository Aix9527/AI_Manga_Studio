import hashlib
import json

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.qc import TimelineQcService
from backend.timeline.repository import TimelineRepository
from backend.timeline.service import TimelineService


def _seed(tmp_path):
    projects_root = tmp_path / "projects"
    project_id = "project-a"
    media_dir = projects_root / project_id / "outputs"
    media_dir.mkdir(parents=True)
    media_path = media_dir / "shot_001.mp4"
    media_path.write_bytes(b"qc-source")
    digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO jobs (id, project_id, status, input_path, input_type, settings, idempotency_key) VALUES ('job-1',?,'completed','','novel','{}','qc-seed')",
            (project_id,),
        )
        conn.execute("INSERT INTO job_steps (id, job_id, sequence, stage_key, shot_id, status) VALUES ('step-1','job-1',0,'video_generate','shot_001','completed')")
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
    snapshot = service.create_snapshot(draft.timeline_id)
    return db, repo, snapshot, media_path


def test_formal_qc_passes_for_structurally_valid_snapshot_with_passed_sources(tmp_path):
    _, repo, snapshot, _ = _seed(tmp_path)
    qc = TimelineQcService(repo)

    run = qc.run(snapshot.id)
    status = qc.get_status(snapshot.id)

    assert run.status == "passed"
    assert status.effective_status == "passed"
    assert len(status.attempts) == 1


def test_formal_qc_fails_when_required_source_quality_failed(tmp_path):
    db, repo, snapshot, _ = _seed(tmp_path)
    with db.transaction() as conn:
        conn.execute("UPDATE artifacts SET quality_status='failed' WHERE id=1")
    qc = TimelineQcService(repo)

    run = qc.run(snapshot.id)

    assert run.status == "failed"
    assert "SOURCE_QC_FAILED" in json.dumps(run.report)


def test_formal_qc_records_stale_when_snapshot_source_bytes_changed(tmp_path):
    _, repo, snapshot, media_path = _seed(tmp_path)
    media_path.write_bytes(b"externally-replaced")
    qc = TimelineQcService(repo)

    run = qc.run(snapshot.id)

    assert run.status == "stale"
    assert "SOURCE_INTEGRITY_FAILED" in json.dumps(run.report)
