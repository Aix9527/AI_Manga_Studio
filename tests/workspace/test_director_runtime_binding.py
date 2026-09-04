from __future__ import annotations

from pathlib import Path

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.orchestration.worker import StageExecutor, SSEBroadcaster
from backend.orchestration.config import OrchestrationConfig
from backend.workspace.repository import WorkspaceRepository


def _executor_with_director_asset(tmp_path: Path):
    db = OrchestrationDatabase(str(tmp_path / "runtime.db"))
    jobs = JobRepository(db, projects_root=tmp_path / "projects")
    workspace = WorkspaceRepository(db, projects_root=tmp_path / "projects")
    job_id = jobs.create_job(
        JobCreate(project_id="project-a", input_path="story.txt"),
        JobSettings(),
    )
    jobs.create_steps(job_id, [
        {"stage_key": "visual_generate", "shot_id": "shot-01"},
        {"stage_key": "video_generate", "shot_id": "shot-01"},
    ])
    visual_step = next(step for step in jobs.get_job_steps(job_id) if step["stage_key"] == "visual_generate")
    jobs.add_artifact(
        job_id,
        visual_step["id"],
        "image",
        "frame.png",
        "sha",
        {"title": "原计划镜头"},
    )
    asset = workspace.list_project_assets(
        "project-a", shot_id="shot-01", active=True,
    )[0]
    workspace.update_project_asset_director(
        "project-a",
        asset.id,
        {
            "composition": "三分构图",
            "shot_size": "中近景",
            "camera_movement": "跟拍",
            "movement_strength": 72,
            "focal_length": "50mm",
            "lighting": "电影逆光",
            "emotion": ["紧张", "压迫"],
            "prompt": "主角保持身份一致，低机位连续跟拍。",
        },
    )
    executor = StageExecutor(
        jobs,
        SSEBroadcaster(),
        OrchestrationConfig(project_root=str(tmp_path / "projects")),
    )
    return executor


def test_stage_executor_reads_active_shot_director_settings(tmp_path: Path):
    executor = _executor_with_director_asset(tmp_path)

    director = executor._director_settings_for_shot("project-a", "shot-01")

    assert director["camera_movement"] == "跟拍"
    assert director["movement_strength"] == 72
    assert director["prompt"] == "主角保持身份一致，低机位连续跟拍。"


def test_director_settings_merge_into_runtime_prompt_and_motion_profile(tmp_path: Path):
    executor = _executor_with_director_asset(tmp_path)
    shot_data = {
        "id": "shot-01",
        "positive_prompt": "雨夜城市，主角站在街口",
        "motion_level": 1,
        "description": "主角观察远处异象",
    }
    director = executor._director_settings_for_shot("project-a", "shot-01")

    merged, prompt = executor._apply_director_settings(
        shot_data,
        "雨夜城市，主角站在街口",
        director,
    )

    assert merged["motion_level"] == 4
    assert merged["camera_movement"] == "跟拍"
    assert merged["director_composition"] == "三分构图"
    assert merged["director_shot_size"] == "中近景"
    assert merged["director_focal_length"] == "50mm"
    assert merged["director_lighting"] == "电影逆光"
    assert merged["director_emotion"] == ["紧张", "压迫"]
    assert "雨夜城市，主角站在街口" in prompt
    assert "三分构图" in prompt
    assert "中近景" in prompt
    assert "跟拍" in prompt
    assert "50mm" in prompt
    assert "电影逆光" in prompt
    assert "紧张、压迫" in prompt
    assert "主角保持身份一致，低机位连续跟拍。" in prompt
