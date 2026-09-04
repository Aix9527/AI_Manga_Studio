from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.routes import router
from backend.workspace.service import WorkspaceService
from backend.video.duration_strategy import get_motion_profile, resolve_motion_bucket


def _client_with_plan(tmp_path: Path):
    projects_root = tmp_path / "projects"
    project_root = projects_root / "project-a"
    project_root.mkdir(parents=True)
    plan_path = project_root / "production_plan.json"
    plan_path.write_text(json.dumps({
        "project_id": "project-a",
        "shots": [
            {
                "id": "shot-01",
                "positive_prompt": "雨夜城市，主角站在街口",
                "negative_prompt": "low quality",
                "motion_level": 1,
                "shot_type": "custom",
                "description": "主角观察远处异象",
            },
            {
                "id": "shot-02",
                "positive_prompt": "另一个镜头保持不变",
                "motion_level": 2,
            },
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    db = OrchestrationDatabase(str(tmp_path / "runtime.db"))
    jobs = JobRepository(db, projects_root=projects_root)
    workspace = WorkspaceRepository(db, projects_root=projects_root)
    job_id = jobs.create_job(
        JobCreate(project_id="project-a", input_path="story.txt"),
        JobSettings(),
    )
    jobs.create_steps(job_id, [{"stage_key": "visual_generate", "shot_id": "shot-01"}])
    visual_step = jobs.get_job_steps(job_id)[0]
    jobs.add_artifact(job_id, visual_step["id"], "image", "frame.png", "sha", {})
    asset = workspace.list_project_assets("project-a", shot_id="shot-01", active=True)[0]

    app = FastAPI()
    app.state.workspace_service = WorkspaceService(db, workspace, projects_root=projects_root)
    app.include_router(router)
    return TestClient(app), asset.id, plan_path


def test_director_save_updates_runtime_production_plan_without_clobbering_other_shots(tmp_path: Path):
    client, asset_id, plan_path = _client_with_plan(tmp_path)
    payload = {
        "composition": "三分构图",
        "shot_size": "中近景",
        "camera_movement": "跟拍",
        "movement_strength": 72,
        "focal_length": "50mm",
        "lighting": "电影逆光",
        "emotion": ["紧张", "压迫"],
        "prompt": "主角保持身份一致，低机位连续跟拍。",
    }

    response = client.put(
        f"/api/workspace/project-a/assets/{asset_id}/director",
        json=payload,
    )

    assert response.status_code == 200
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shot = plan["shots"][0]
    untouched = plan["shots"][1]

    assert shot["director"] == payload
    assert shot["camera_movement"] == "跟拍"
    assert shot["camera"] == "跟拍"
    assert shot["motion_level"] == 4
    assert shot["motion_bucket_id"] == 175
    assert shot["director_composition"] == "三分构图"
    assert shot["director_shot_size"] == "中近景"
    assert shot["director_focal_length"] == "50mm"
    assert shot["director_lighting"] == "电影逆光"
    assert shot["director_emotion"] == ["紧张", "压迫"]
    assert shot["director_base_positive_prompt"] == "雨夜城市，主角站在街口"
    assert "雨夜城市，主角站在街口" in shot["positive_prompt"]
    assert "三分构图" in shot["positive_prompt"]
    assert "中近景" in shot["positive_prompt"]
    assert "跟拍" in shot["positive_prompt"]
    assert "50mm" in shot["positive_prompt"]
    assert "电影逆光" in shot["positive_prompt"]
    assert "紧张、压迫" in shot["positive_prompt"]
    assert "主角保持身份一致，低机位连续跟拍。" in shot["positive_prompt"]
    assert untouched == {
        "id": "shot-02",
        "positive_prompt": "另一个镜头保持不变",
        "motion_level": 2,
    }

    assert get_motion_profile(shot).level == 4
    assert resolve_motion_bucket(shot) == 175


def test_repeated_director_save_rebuilds_prompt_instead_of_duplicating_previous_director_clause(tmp_path: Path):
    client, asset_id, plan_path = _client_with_plan(tmp_path)
    first = {
        "composition": "三分构图",
        "shot_size": "中近景",
        "camera_movement": "跟拍",
        "movement_strength": 72,
        "focal_length": "50mm",
        "lighting": "电影逆光",
        "emotion": ["紧张"],
        "prompt": "第一次导演说明",
    }
    second = {
        **first,
        "camera_movement": "推镜",
        "movement_strength": 35,
        "focal_length": "85mm",
        "emotion": ["危机"],
        "prompt": "第二次导演说明",
    }

    assert client.put(f"/api/workspace/project-a/assets/{asset_id}/director", json=first).status_code == 200
    assert client.put(f"/api/workspace/project-a/assets/{asset_id}/director", json=second).status_code == 200

    shot = json.loads(plan_path.read_text(encoding="utf-8"))["shots"][0]
    assert shot["director_base_positive_prompt"] == "雨夜城市，主角站在街口"
    assert shot["positive_prompt"].count("雨夜城市，主角站在街口") == 1
    assert "第一次导演说明" not in shot["positive_prompt"]
    assert "第二次导演说明" in shot["positive_prompt"]
    assert shot["camera_movement"] == "推镜"
    assert shot["motion_level"] == 2
    assert shot["motion_bucket_id"] == 105
