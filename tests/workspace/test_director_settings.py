from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.routes import router
from backend.workspace.service import WorkspaceService


def test_director_settings_are_persisted_on_the_exact_project_asset(tmp_path: Path):
    projects_root = tmp_path / "projects"
    db = OrchestrationDatabase(str(tmp_path / "workspace.db"))
    jobs = JobRepository(db)
    workspace = WorkspaceRepository(db, projects_root=projects_root)

    job_id = jobs.create_job(
        JobCreate(project_id="project-a", input_path="story.txt"),
        JobSettings(),
    )
    jobs.create_steps(job_id, [{"stage_key": "keyframe", "shot_id": "shot-01"}])
    asset = workspace.add_project_asset(
        job_id,
        "image/keyframe",
        "frames/shot-01.png",
        stage_key="keyframe",
        scene_id="scene-01",
        shot_id="shot-01",
        metadata={"title": "建立镜头", "duration": 6},
    )

    app = FastAPI()
    app.state.workspace_service = WorkspaceService(db, workspace, projects_root=projects_root)
    app.include_router(router)
    client = TestClient(app)

    payload = {
        "composition": "三分构图",
        "shot_size": "中近景",
        "camera_movement": "跟拍",
        "movement_strength": 72,
        "focal_length": "50mm",
        "lighting": "电影逆光",
        "emotion": ["紧张", "压迫"],
        "prompt": "角色保持一致，低机位跟拍，电影逆光。",
    }
    response = client.put(
        f"/api/workspace/project-a/assets/{asset.id}/director",
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["title"] == "建立镜头"
    assert body["metadata"]["duration"] == 6
    assert body["metadata"]["director"] == payload

    restored = workspace.get_project_asset("project-a", asset.id)
    assert restored is not None
    assert restored.metadata["director"] == payload


def test_director_settings_cannot_cross_project_boundary(tmp_path: Path):
    projects_root = tmp_path / "projects"
    db = OrchestrationDatabase(str(tmp_path / "workspace.db"))
    jobs = JobRepository(db)
    workspace = WorkspaceRepository(db, projects_root=projects_root)

    job_id = jobs.create_job(
        JobCreate(project_id="project-a", input_path="story.txt"),
        JobSettings(),
    )
    jobs.create_steps(job_id, [{"stage_key": "keyframe", "shot_id": "shot-01"}])
    asset = workspace.add_project_asset(job_id, "image", "frame.png", shot_id="shot-01")

    app = FastAPI()
    app.state.workspace_service = WorkspaceService(db, workspace, projects_root=projects_root)
    app.include_router(router)
    client = TestClient(app)

    response = client.put(
        f"/api/workspace/project-b/assets/{asset.id}/director",
        json={
            "composition": "中心构图",
            "shot_size": "特写",
            "camera_movement": "推镜",
            "movement_strength": 50,
            "focal_length": "85mm",
            "lighting": "柔光",
            "emotion": ["危机"],
            "prompt": "test",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "素材不存在"}
