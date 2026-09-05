import hashlib
import json

import pytest

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.service import JobService
from backend.orchestration.worker import SSEBroadcaster
from backend.timeline.compiler import TimelineOutputProfile
from backend.timeline.export_service import TimelineExportService, TimelineExportBlocked
from backend.timeline.qc import TimelineQcService
from backend.timeline.repository import TimelineRepository
from backend.timeline.service import TimelineService


def _system(tmp_path, *, run_qc=True):
    projects_root = tmp_path / "projects"
    project_id = "project-a"
    media_dir = projects_root / project_id / "outputs"
    media_dir.mkdir(parents=True)
    source = media_dir / "shot_001.mp4"
    source.write_bytes(b"export-source")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    db = OrchestrationDatabase(str(tmp_path / "orchestration.db"))
    with db.transaction() as conn:
        conn.execute("INSERT INTO jobs (id,project_id,status,input_path,input_type,settings,idempotency_key) VALUES ('source-job',?,'completed','','novel','{}','export-source')", (project_id,))
        conn.execute("INSERT INTO job_steps (id,job_id,sequence,stage_key,shot_id,status) VALUES ('source-step','source-job',0,'video_generate','shot_001','completed')")
        conn.execute(
            """INSERT INTO artifacts
               (id,job_id,step_id,kind,path,sha256,metadata,active,project_id,version,
                stage_key,scene_id,shot_id,quality_status)
               VALUES (1,'source-job','source-step','video','outputs/shot_001.mp4',?,?,1,?,1,
                       'video_generate','scene-1','shot_001','passed')""",
            (digest, json.dumps({"duration_tick": 2_000_000}), project_id),
        )

    timeline_repo = TimelineRepository(db, projects_root=projects_root)
    timeline_service = TimelineService(timeline_repo)
    draft, _ = timeline_service.initialize_project(project_id)
    snapshot = timeline_service.create_snapshot(draft.timeline_id)
    if run_qc:
        assert TimelineQcService(timeline_repo).run(snapshot.id).status == "passed"

    job_repo = JobRepository(db, projects_root=projects_root)
    broadcaster = SSEBroadcaster()
    config = OrchestrationConfig(
        database_path=str(tmp_path / "unused.db"),
        checkpoint_dir=str(tmp_path / "checkpoints"),
        project_root=str(projects_root),
    )
    job_service = JobService(db, job_repo, broadcaster, config)
    export_service = TimelineExportService(timeline_repo, job_service)
    return db, job_repo, export_service, snapshot


def test_export_requires_passed_snapshot_qc(tmp_path):
    _, _, export_service, snapshot = _system(tmp_path, run_qc=False)
    with pytest.raises(TimelineExportBlocked, match="QC"):
        export_service.export(
            snapshot.id,
            TimelineOutputProfile(width=1080, height=1920, fps_num=24, fps_den=1),
        )


def test_passed_snapshot_creates_compose_export_only_job_with_provenance(tmp_path):
    db, repo, export_service, snapshot = _system(tmp_path)

    result = export_service.export(
        snapshot.id,
        TimelineOutputProfile(width=1080, height=1920, fps_num=24, fps_den=1),
    )

    steps = repo.get_job_steps(result.job_id)
    assert [(row["stage_key"], row["shot_id"]) for row in steps] == [
        ("composition_compose", ""),
        ("export", ""),
    ]
    with db.connect() as conn:
        job = conn.execute("SELECT settings,input_type FROM jobs WHERE id=?", (result.job_id,)).fetchone()
    settings = json.loads(job["settings"])
    assert job["input_type"] == "timeline_snapshot"
    assert settings["timeline"]["snapshot_id"] == snapshot.id
    assert settings["timeline"]["composition_spec_sha256"] == result.composition_spec_sha256


def test_identical_export_request_is_idempotent(tmp_path):
    _, _, export_service, snapshot = _system(tmp_path)
    profile = TimelineOutputProfile(width=1080, height=1920, fps_num=24, fps_den=1)

    first = export_service.export(snapshot.id, profile)
    second = export_service.export(snapshot.id, profile)

    assert second.job_id == first.job_id
    assert second.composition_spec_sha256 == first.composition_spec_sha256
