from __future__ import annotations

from pathlib import Path

import pytest

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JobStatus
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.orchestration.worker import SSEBroadcaster, StageExecutor


class _Composer:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)

    def export_final(self, composite_path: Path, final_path: Path, format: str = "mp4") -> Path:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"final-video")
        return final_path


def _timeline_export_system(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "timeline-export.db"))
    repo = JobRepository(db, projects_root=tmp_path / "projects")
    config = OrchestrationConfig(
        database_path=str(tmp_path / "unused.db"),
        checkpoint_dir=str(tmp_path / "checkpoints"),
        project_root=str(tmp_path / "projects"),
    )
    executor = StageExecutor(repo, SSEBroadcaster(), config)
    timeline = {
        "source": "timeline_snapshot",
        "timeline_id": "timeline-a",
        "timeline_snapshot_id": "snapshot-a",
        "timeline_snapshot_sha256": "s" * 64,
        "composition_spec_id": "spec-a",
        "composition_spec_sha256": "c" * 64,
    }
    job_id = repo.create_job(
        JobCreate(
            project_id="project-a",
            input_path="",
            input_type="timeline_snapshot",
            idempotency_key="timeline-export-test",
        ),
        JobSettings(timeline=timeline),
    )
    repo.create_steps(
        job_id,
        [
            {"stage_key": "composition_compose", "shot_id": ""},
            {"stage_key": "export", "shot_id": ""},
        ],
    )
    with db.transaction(immediate=True) as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (JobStatus.RUNNING.value, job_id))
        conn.execute(
            """INSERT INTO timelines
               (id,project_id,name,timebase_hz,fps_num,fps_den,active_draft_id,latest_snapshot_no,created_at,updated_at)
               VALUES ('timeline-a','project-a','Timeline',1000000,24,1,NULL,1,'now','now')"""
        )
        conn.execute(
            """INSERT INTO timeline_snapshots
               (id,timeline_id,snapshot_no,source_draft_revision,state_json,state_sha256,duration_tick,created_at)
               VALUES ('snapshot-a','timeline-a',1,0,'{}',?,1000000,'now')""",
            ("s" * 64,),
        )
        conn.execute(
            """INSERT INTO timeline_composition_specs
               (id,snapshot_id,output_profile_json,compiler_version,spec_json,spec_sha256,created_at)
               VALUES ('spec-a','snapshot-a','{}','timeline-compose/v1','{}',?,'now')""",
            ("c" * 64,),
        )
        conn.execute(
            """INSERT INTO timeline_export_bindings
               (id,composition_spec_id,job_id,artifact_id,status,created_at,updated_at)
               VALUES ('binding-a','spec-a',?,NULL,'queued','now','now')""",
            (job_id,),
        )
    output_dir = tmp_path / "projects" / "project-a" / "outputs"
    composite = output_dir / "composition" / "composite.mp4"
    composite.parent.mkdir(parents=True, exist_ok=True)
    composite.write_bytes(b"composite")
    return db, repo, executor, job_id, output_dir


@pytest.mark.asyncio
async def test_timeline_export_records_actual_final_artifact_on_binding(tmp_path, monkeypatch):
    db, repo, executor, job_id, output_dir = _timeline_export_system(tmp_path)
    import backend.video.composer as composer_module
    monkeypatch.setattr(composer_module, "VideoComposer", _Composer)

    await executor._run_export(job_id, output_dir, 24, "project-a")

    with db.connect() as conn:
        binding = conn.execute(
            "SELECT artifact_id,status FROM timeline_export_bindings WHERE job_id=?",
            (job_id,),
        ).fetchone()
        artifact = conn.execute(
            """SELECT id,path,kind FROM artifacts
               WHERE job_id=? AND kind='video' AND active=1
               ORDER BY id DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
    assert artifact is not None
    assert binding is not None
    assert binding["artifact_id"] == artifact["id"]
    assert binding["status"] == "completed"
    assert str(artifact["path"]).endswith("export/final.mp4")


@pytest.mark.asyncio
async def test_legacy_export_does_not_require_or_create_timeline_binding(tmp_path, monkeypatch):
    db = OrchestrationDatabase(str(tmp_path / "legacy-export.db"))
    repo = JobRepository(db, projects_root=tmp_path / "projects")
    config = OrchestrationConfig(
        database_path=str(tmp_path / "unused.db"),
        checkpoint_dir=str(tmp_path / "checkpoints"),
        project_root=str(tmp_path / "projects"),
    )
    executor = StageExecutor(repo, SSEBroadcaster(), config)
    job_id = repo.create_job(
        JobCreate(project_id="project-a", input_path="chapter.txt"),
        JobSettings(),
    )
    repo.create_steps(job_id, [{"stage_key": "export", "shot_id": ""}])
    with db.transaction(immediate=True) as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (JobStatus.RUNNING.value, job_id))
    output_dir = tmp_path / "projects" / "project-a" / "outputs"
    composite = output_dir / "composition" / "composite.mp4"
    composite.parent.mkdir(parents=True, exist_ok=True)
    composite.write_bytes(b"composite")
    import backend.video.composer as composer_module
    monkeypatch.setattr(composer_module, "VideoComposer", _Composer)

    await executor._run_export(job_id, output_dir, 24, "project-a")

    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM timeline_export_bindings").fetchone()["n"]
    assert count == 0
