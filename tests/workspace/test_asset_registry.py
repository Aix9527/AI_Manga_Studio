from __future__ import annotations

from pathlib import Path

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.asset_registry import AssetRegistry


def _setup(tmp_path: Path):
    db = OrchestrationDatabase(str(tmp_path / "ws.db"))
    repo = WorkspaceRepository(db, projects_root=tmp_path / "projects")
    jobs = JobRepository(db)
    job_id = jobs.create_job(JobCreate(project_id="test_gx", input_path="story.txt"), JobSettings())
    jobs.create_steps(job_id, [{"stage_key": "keyframe", "shot_id": "gx_001"}])
    return db, repo, jobs, job_id


def test_register_dedup_by_hash(tmp_path):
    db, repo, jobs, job_id = _setup(tmp_path)
    reg = AssetRegistry(repo)
    asset_file = tmp_path / "asset.png"
    asset_file.write_bytes(b"imagedata")

    first, created1 = reg.register(job_id, "keyframe", asset_file, stage_key="keyframe", shot_id="gx_001")
    second, created2 = reg.register(job_id, "keyframe", asset_file, stage_key="keyframe", shot_id="gx_001")
    assert created1 is True
    assert created2 is False
    assert first.id == second.id


def test_recovery_manifest_groups_by_stage(tmp_path):
    db, repo, jobs, job_id = _setup(tmp_path)
    reg = AssetRegistry(repo)
    a1 = tmp_path / "k.png"; a1.write_bytes(b"k1")
    a2 = tmp_path / "v.mp4"; a2.write_bytes(b"v1")
    reg.register(job_id, "keyframe", a1, stage_key="keyframe", shot_id="gx_001")
    reg.register(job_id, "video", a2, stage_key="video", shot_id="gx_001")
    manifest = reg.recovery_manifest("test_gx")
    assert manifest["total_assets"] == 2
    assert "keyframe" in manifest["by_stage"]
    assert "video" in manifest["by_stage"]
