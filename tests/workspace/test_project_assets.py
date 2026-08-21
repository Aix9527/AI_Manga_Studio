from __future__ import annotations

import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.enums import JobStatus
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.orchestration.service import JobService
from backend.orchestration.worker import SSEBroadcaster
from backend.routes import jobs as jobs_router
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.routes import router
from backend.workspace.service import WorkspaceService


def _job(repo: JobRepository, project_id: str, *, shot_id: str = "shot-1") -> str:
    job_id = repo.create_job(JobCreate(project_id=project_id, input_path="story.txt"), JobSettings())
    repo.create_steps(job_id, [{"stage_key": "keyframe", "shot_id": shot_id}])
    return job_id


def _workspace(tmp_path: Path):
    projects_root = tmp_path / "projects"
    db = OrchestrationDatabase(str(tmp_path / "workspace.db"))
    repo = WorkspaceRepository(db, projects_root=projects_root)
    jobs = JobRepository(db)
    return db, repo, jobs, projects_root


def _client(db: OrchestrationDatabase, repo: WorkspaceRepository, projects_root: Path) -> TestClient:
    app = FastAPI()
    app.state.workspace_service = WorkspaceService(db, repo, projects_root=projects_root)
    app.include_router(router)
    return TestClient(app)


def test_legacy_artifacts_migrate_and_backfill_idempotently(tmp_path):
    db_path = tmp_path / "legacy.db"
    initial = OrchestrationDatabase(str(db_path))
    with initial.transaction() as conn:
        conn.execute("DROP TABLE artifacts")
        conn.execute(
            """CREATE TABLE artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )"""
        )
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            INSERT INTO jobs (id, project_id) VALUES ('job-old', 'legacy-project');
            INSERT INTO job_steps (id, job_id, sequence, stage_key) VALUES ('step-old', 'job-old', 0, 'keyframe');
            INSERT INTO artifacts
                (job_id, step_id, kind, path, sha256, metadata, active)
            VALUES ('job-old', 'step-old', 'image', 'frames/old.png', 'abc', '{"kept":true}', 1);
            """
        )

    OrchestrationDatabase(str(db_path))
    OrchestrationDatabase(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(artifacts)")}
        row = conn.execute("SELECT * FROM artifacts WHERE job_id='job-old'").fetchone()
    assert {
        "project_id", "parent_artifact_id", "version", "stage_key", "scene_id", "shot_id",
        "quality_status", "quality_attempt", "quality_report",
    } <= columns
    assert dict(row) | {} == {
        **dict(row),
        "project_id": "legacy-project",
        "version": 1,
        "active": 1,
        "metadata": '{"kept":true}',
        "quality_attempt": 0,
        "quality_report": "{}",
    }


def test_versions_switch_active_only_inside_the_same_lineage_and_round_trip_metadata(tmp_path):
    _, repo, jobs, _ = _workspace(tmp_path)
    job_id = _job(jobs, "project-a")

    first = repo.add_project_asset(
        job_id, "image", "frames/shot-1-v1.png", stage_key="keyframe",
        scene_id="scene-1", shot_id="shot-1", metadata={"prompt": "海潮"},
    )
    other = repo.add_project_asset(
        job_id, "image", "frames/shot-2-v1.png", stage_key="keyframe",
        scene_id="scene-1", shot_id="shot-2",
    )
    second = repo.add_project_asset(
        job_id, "image", "frames/shot-1-v2.png", stage_key="keyframe",
        scene_id="scene-1", shot_id="shot-1", parent_artifact_id=first.id,
    )

    assets = repo.list_project_assets("project-a", active=None)
    by_id = {asset.id: asset for asset in assets}
    assert (first.version, by_id[first.id].active) == (1, False)
    assert (second.version, by_id[second.id].active) == (2, True)
    assert by_id[other.id].active is True
    assert by_id[first.id].metadata == {"prompt": "海潮"}

    with repo.db.transaction() as conn:
        conn.execute("UPDATE artifacts SET metadata='not-json' WHERE id=?", (other.id,))
    assert repo.get_project_asset("project-a", other.id).metadata == {}


def test_parent_must_belong_to_project_and_exact_lineage(tmp_path):
    _, repo, jobs, _ = _workspace(tmp_path)
    job_a = _job(jobs, "project-a")
    job_b = _job(jobs, "project-b")
    parent = repo.add_project_asset(
        job_a, "image", "a.png", stage_key="keyframe", scene_id="scene-1", shot_id="shot-1"
    )

    with pytest.raises(ValueError, match="同一项目"):
        repo.add_project_asset(
            job_b, "image", "b.png", stage_key="keyframe", scene_id="scene-1",
            shot_id="shot-1", parent_artifact_id=parent.id,
        )
    with pytest.raises(ValueError, match="版本链"):
        repo.add_project_asset(
            job_a, "video", "b.mp4", stage_key="keyframe", scene_id="scene-1",
            shot_id="shot-1", parent_artifact_id=parent.id,
        )


def test_filters_stable_sort_and_restart_restore_versions(tmp_path):
    db, repo, jobs, projects_root = _workspace(tmp_path)
    job_id = _job(jobs, "project-a")
    first = repo.add_project_asset(
        job_id, "image", "one.png", stage_key="keyframe", scene_id="scene-1",
        shot_id="shot-1", quality_status="passed",
    )
    repo.add_project_asset(
        job_id, "image", "two.png", stage_key="keyframe", scene_id="scene-1",
        shot_id="shot-1", parent_artifact_id=first.id, quality_status="failed",
    )
    repo.add_project_asset(
        job_id, "audio", "voice.wav", stage_key="audio", scene_id="scene-1",
        shot_id="shot-2", quality_status="passed",
    )

    filtered = repo.list_project_assets(
        "project-a", kind="image", stage_key="keyframe", scene_id="scene-1",
        shot_id="shot-1", quality_status="failed", active=True,
    )
    assert [(asset.version, asset.active) for asset in filtered] == [(2, True)]
    client = _client(db, repo, projects_root)
    response = client.get(
        "/api/workspace/project-a/assets",
        params={
            "kind": "image",
            "stage_key": "keyframe",
            "scene_id": "scene-1",
            "shot_id": "shot-1",
            "quality_status": "failed",
            "active": "true",
        },
    )
    assert response.status_code == 200
    assert [(item["version"], item["active"]) for item in response.json()] == [(2, True)]
    all_versions = client.get("/api/workspace/project-a/assets", params={"kind": "image"})
    assert all_versions.status_code == 200
    assert [(item["version"], item["active"]) for item in all_versions.json()] == [
        (2, True), (1, False)
    ]

    restored = WorkspaceRepository(
        OrchestrationDatabase(db.db_path), projects_root=projects_root
    ).list_project_assets("project-a", active=None)
    assert [(asset.active, asset.version) for asset in restored] == [
        (True, 2), (True, 1), (False, 1)
    ]


def test_concurrent_creates_have_unique_versions_and_one_current_asset(tmp_path):
    _, repo, jobs, _ = _workspace(tmp_path)
    job_id = _job(jobs, "project-a")

    def add(index: int):
        return repo.add_project_asset(
            job_id, "image", f"frames/{index}.png", stage_key="keyframe",
            scene_id="scene-1", shot_id="shot-1",
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        created = list(pool.map(add, range(6)))

    assert sorted(asset.version for asset in created) == [1, 2, 3, 4, 5, 6]
    all_assets = repo.list_project_assets("project-a", active=None)
    assert sum(asset.active for asset in all_assets) == 1
    assert next(asset.version for asset in all_assets if asset.active) == 6


def test_asset_list_and_media_route_return_safe_real_media(tmp_path):
    db, repo, jobs, projects_root = _workspace(tmp_path)
    job_id = _job(jobs, "项目 A")
    project_dir = projects_root / "项目 A" / "frames"
    project_dir.mkdir(parents=True)
    payload = b"\x89PNG\r\n\x1a\nreal-image"
    media_path = project_dir / "hero image.png"
    media_path.write_bytes(payload)
    asset = repo.add_project_asset(
        job_id, "image", str(media_path.resolve()), stage_key="keyframe", shot_id="shot-1"
    )
    client = _client(db, repo, projects_root)

    listing = client.get("/api/workspace/%E9%A1%B9%E7%9B%AE%20A/assets")
    assert listing.status_code == 200
    item = listing.json()[0]
    assert item["path"] == "frames/hero image.png"
    assert item["media_url"] == f"/api/workspace/%E9%A1%B9%E7%9B%AE%20A/assets/{asset.id}/media"
    assert str(tmp_path) not in listing.text

    response = client.get(item["media_url"])
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-type"] == "image/png"
    assert "attachment" not in response.headers.get("content-disposition", "").lower()


def test_media_route_hides_missing_traversal_symlink_and_unsupported_paths(tmp_path):
    db, repo, jobs, projects_root = _workspace(tmp_path)
    job_id = _job(jobs, "project-a")
    project_dir = projects_root / "project-a"
    project_dir.mkdir(parents=True)
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"secret")
    missing = repo.add_project_asset(job_id, "image", "missing.png")
    traversal = repo.add_project_asset(job_id, "image", "../secret.png")
    unsupported_path = project_dir / "payload.exe"
    unsupported_path.write_bytes(b"MZ")
    unsupported = repo.add_project_asset(job_id, "binary", "payload.exe")
    client = _client(db, repo, projects_root)

    for asset in (missing, traversal):
        response = client.get(f"/api/workspace/project-a/assets/{asset.id}/media")
        assert response.status_code == 404
        assert response.json() == {"detail": "素材不存在"}
        assert str(tmp_path) not in response.text
    mismatch = client.get(f"/api/workspace/project-b/assets/{missing.id}/media")
    assert mismatch.status_code == 404
    assert mismatch.json() == {"detail": "素材不存在"}
    response = client.get(f"/api/workspace/project-a/assets/{unsupported.id}/media")
    assert response.status_code == 415
    assert response.json() == {"detail": "不支持的素材类型"}

    link = project_dir / "escape.png"
    try:
        link.symlink_to(outside)
    except OSError:
        outside_dir = tmp_path / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "secret.png").write_bytes(b"secret")
        link_dir = project_dir / "escape-dir"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_dir), str(outside_dir)],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("当前环境不允许创建符号链接或目录联接")
        escaped_path = "escape-dir/secret.png"
    else:
        escaped_path = "escape.png"
    escaped = repo.add_project_asset(job_id, "image", escaped_path)
    response = client.get(f"/api/workspace/project-a/assets/{escaped.id}/media")
    assert response.status_code == 404
    assert response.json() == {"detail": "素材不存在"}


def test_production_artifact_paths_are_project_relative_and_legacy_prefixed_paths_serve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    projects_root = Path("projects")
    db = OrchestrationDatabase(str(tmp_path / "production.db"))
    jobs = JobRepository(db, projects_root=projects_root)
    workspace = WorkspaceRepository(db, projects_root=projects_root)
    job_id = jobs.create_job(
        JobCreate(project_id="project-a", input_path="story.txt"), JobSettings()
    )
    jobs.create_steps(job_id, [{"stage_key": "visual_generate", "shot_id": "shot-1"}])
    output = projects_root / "project-a" / "outputs" / "images" / "shot-1" / "frame.png"
    output.parent.mkdir(parents=True)
    payload = b"\x89PNG\r\n\x1a\nexecutor-output"
    output.write_bytes(payload)

    jobs.add_artifact(job_id, "shot-1", "image", str(output), "sha", {})
    with db.connect() as conn:
        stored = conn.execute("SELECT path FROM artifacts WHERE job_id=?", (job_id,)).fetchone()["path"]
    assert stored == "outputs/images/shot-1/frame.png"
    asset = workspace.list_project_assets("project-a")[0]
    client = _client(db, workspace, projects_root)
    response = client.get(asset.media_url)
    assert response.status_code == 200
    assert response.content == payload

    with db.transaction() as conn:
        conn.execute(
            "UPDATE artifacts SET path='projects/project-a/outputs/images/shot-1/frame.png' WHERE id=?",
            (asset.id,),
        )
    legacy_response = client.get(asset.media_url)
    assert legacy_response.status_code == 200
    assert legacy_response.content == payload


def test_production_artifacts_map_ui_stage_chain_parent_and_keep_audio_subtypes_active(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "production.db"))
    jobs = JobRepository(db, projects_root=tmp_path / "projects")
    workspace = WorkspaceRepository(db, projects_root=tmp_path / "projects")
    job_id = jobs.create_job(
        JobCreate(project_id="project-a", input_path="story.txt"), JobSettings()
    )
    jobs.create_steps(job_id, [
        {"stage_key": "visual_generate", "shot_id": "shot-1"},
        {"stage_key": "audio_tts", "shot_id": ""},
        {"stage_key": "audio_sfx", "shot_id": ""},
    ])

    jobs.add_artifact(job_id, "shot-1", "image", "one.png", "one", {})
    jobs.add_artifact(job_id, "shot-1", "image", "two.png", "two", {})
    jobs.add_artifact(job_id, "audio_tts", "audio", "tts-1.wav", "tts1", {})
    jobs.add_artifact(job_id, "audio_sfx", "audio", "sfx.wav", "sfx", {})
    jobs.add_artifact(job_id, "audio_tts", "audio", "tts-2.wav", "tts2", {})

    images = workspace.list_project_assets("project-a", stage_key="keyframe", active=None)
    assert [(item.version, item.parent_artifact_id, item.active) for item in images] == [
        (2, images[1].id, True), (1, None, False)
    ]
    audio = workspace.list_project_assets("project-a", stage_key="audio", active=None)
    by_subtype = {item.metadata.get("subtype"): item for item in audio if item.active}
    assert set(by_subtype) == {"tts", "sfx"}
    assert by_subtype["tts"].version == 2
    assert by_subtype["tts"].parent_artifact_id is not None
    assert by_subtype["sfx"].version == 1


def test_job_detail_pause_resume_normalize_broken_artifact_metadata(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "jobs.db"))
    repo = JobRepository(db, projects_root=tmp_path / "projects")
    broadcaster = SSEBroadcaster()
    service = JobService(db, repo, broadcaster, OrchestrationConfig())
    detail = service.create(JobCreate(project_id="project-a", input_path="story.txt"))
    visual_step = next(step for step in repo.get_job_steps(detail.id) if step["stage_key"] == "visual_generate")
    repo.add_artifact(detail.id, visual_step["id"], "image", "frame.png", "sha", {"prompt": "海"})
    with db.transaction() as conn:
        conn.execute("UPDATE artifacts SET metadata='broken-json' WHERE job_id=?", (detail.id,))
    repo.set_job_status(detail.id, JobStatus.RUNNING, allowed_from={JobStatus.QUEUED})

    app = FastAPI()
    app.state.job_service = service
    app.include_router(jobs_router.router)
    client = TestClient(app)
    for method, path in (
        ("get", f"/api/jobs/{detail.id}"),
        ("post", f"/api/jobs/{detail.id}/pause"),
        ("post", f"/api/jobs/{detail.id}/resume"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 200
        assert response.json()["artifacts"][0]["metadata"] == {}


def test_svg_media_is_rejected_without_returning_active_content(tmp_path):
    db, repo, jobs, projects_root = _workspace(tmp_path)
    job_id = _job(jobs, "project-a")
    project_dir = projects_root / "project-a"
    project_dir.mkdir(parents=True)
    malicious = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    (project_dir / "malicious.svg").write_bytes(malicious)
    svg = repo.add_project_asset(job_id, "image", "malicious.svg")

    response = _client(db, repo, projects_root).get(
        f"/api/workspace/project-a/assets/{svg.id}/media"
    )
    assert response.status_code == 415
    assert response.json() == {"detail": "不支持的素材类型"}
    assert malicious not in response.content
