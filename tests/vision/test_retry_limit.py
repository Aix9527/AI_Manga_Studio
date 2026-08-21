from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JobStatus, StepStatus
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.orchestration.service import JobService
from backend.orchestration.worker import SSEBroadcaster
from backend.routes import vision as vision_routes
from backend.routes import jobs as jobs_routes
from backend.routes.vision import router as vision_router
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.routes import router as workspace_router
from backend.workspace.service import WorkspaceService


def _environment(tmp_path: Path):
    db = OrchestrationDatabase(str(tmp_path / "quality.db"))
    job_repo = JobRepository(db, projects_root=tmp_path / "projects")
    workspace_repo = WorkspaceRepository(db, projects_root=tmp_path / "projects")
    broadcaster = SSEBroadcaster()
    job_service = JobService(db, job_repo, broadcaster, OrchestrationConfig())
    workspace_service = WorkspaceService(
        db,
        workspace_repo,
        broadcaster=broadcaster,
        projects_root=tmp_path / "projects",
        job_service=job_service,
    )
    app = FastAPI()
    app.state.job_service = job_service
    app.state.workspace_service = workspace_service
    app.include_router(vision_router)
    app.include_router(workspace_router)
    app.include_router(jobs_routes.router)
    return TestClient(app), db, job_repo, workspace_repo


def _job_with_asset(
    db: OrchestrationDatabase,
    job_repo: JobRepository,
    workspace_repo: WorkspaceRepository,
    *,
    project_id: str = "project-a",
    job_status: JobStatus = JobStatus.WAITING_REVIEW,
    step_status: StepStatus = StepStatus.WAITING_REVIEW,
    quality_attempt: int = 1,
):
    job_id = job_repo.create_job(
        JobCreate(project_id=project_id, input_path="story.txt"),
        JobSettings(),
    )
    job_repo.create_steps(job_id, [{"stage_key": "visual_generate", "shot_id": "shot_03"}])
    step = job_repo.get_job_steps(job_id)[0]
    with db.transaction() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (job_status.value, job_id))
        conn.execute(
            "UPDATE job_steps SET status=?, quality_attempt=? WHERE id=?",
            (step_status.value, quality_attempt, step["id"]),
        )
    job_repo.add_artifact(
        job_id,
        step["id"],
        "image",
        "outputs/shot_03-v1.png",
        "sha",
        {},
    )
    job_repo.save_quality_report(
        step["id"],
        {"overall_score": 0.58, "passed": False, "issues": ["人物偏移"]},
    )
    asset = workspace_repo.list_project_assets(project_id)[0]
    return job_id, step["id"], asset


def test_vision_health_reports_two_quality_retries_without_loading_analyzer(tmp_path, monkeypatch):
    monkeypatch.setattr(vision_routes, "_analyzer", None)
    client, _, _, _ = _environment(tmp_path)

    response = client.get("/api/vision/health")

    assert response.status_code == 200
    assert response.json()["max_retries"] == 2
    assert response.json()["analyzer_initialized"] is False
    assert response.json()["clip_available"] is None
    assert vision_routes._analyzer is None


def test_vision_lazy_singletons_are_initialized_once_under_concurrency(monkeypatch):
    analyzer_calls = 0
    scorer_calls = 0

    class FakeAnalyzer:
        _clip_available = True

    class FakeScorer:
        threshold = 0.65

    def analyzer_factory():
        nonlocal analyzer_calls
        analyzer_calls += 1
        time.sleep(0.01)
        return FakeAnalyzer()

    def scorer_factory(*, pass_threshold):
        nonlocal scorer_calls
        assert pass_threshold == 0.65
        scorer_calls += 1
        time.sleep(0.01)
        return FakeScorer()

    monkeypatch.setattr(vision_routes, "_analyzer", None)
    monkeypatch.setattr(vision_routes, "_scorer", None)
    monkeypatch.setattr(vision_routes, "ImageAnalyzer", analyzer_factory)
    monkeypatch.setattr(vision_routes, "QualityScorer", scorer_factory)

    with ThreadPoolExecutor(max_workers=8) as pool:
        analyzers = list(pool.map(lambda _: vision_routes._get_analyzer(), range(8)))
        scorers = list(pool.map(lambda _: vision_routes._get_scorer(), range(8)))

    assert analyzer_calls == 1
    assert scorer_calls == 1
    assert len({id(value) for value in analyzers}) == 1
    assert len({id(value) for value in scorers}) == 1


def test_asset_versions_bind_step_attempt_and_normalized_quality_report(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    _, step_id, asset = _job_with_asset(db, jobs, workspace)

    response = client.get("/api/workspace/project-a/assets")

    assert response.status_code == 200
    assert response.json()[0] | {} == {
        **response.json()[0],
        "step_id": step_id,
        "quality_attempt": 1,
        "quality_report": {
            "overall_score": 0.58,
            "passed": False,
            "issues": ["人物偏移"],
        },
    }

    with db.transaction() as conn:
        conn.execute("UPDATE artifacts SET quality_report='[]' WHERE id=?", (asset.id,))
    assert client.get("/api/workspace/project-a/assets").json()[0]["quality_report"] == {}
    with db.transaction() as conn:
        conn.execute("UPDATE artifacts SET quality_report='broken-json' WHERE id=?", (asset.id,))
    assert client.get("/api/workspace/project-a/assets").json()[0]["quality_report"] == {}


def test_each_asset_version_keeps_its_own_quality_snapshot(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    _, step_id, first = _job_with_asset(db, jobs, workspace, quality_attempt=1)
    jobs.increment_quality_attempt(step_id)
    jobs.add_artifact(
        first.job_id,
        step_id,
        "image",
        "outputs/shot_03-v2.png",
        "sha-v2",
        {},
    )
    second_report = {
        "overall_score": 0.74,
        "passed": True,
        "issues": [],
    }
    jobs.save_quality_report(step_id, second_report)

    versions = client.get(
        "/api/workspace/project-a/assets", params={"active": "false"}
    )
    assert versions.status_code == 200
    first_payload = versions.json()[0]
    active_payload = client.get(
        "/api/workspace/project-a/assets", params={"active": "true"}
    ).json()[0]
    assert (first_payload["id"], first_payload["quality_attempt"]) == (first.id, 1)
    assert first_payload["quality_report"]["overall_score"] == 0.58
    assert first_payload["quality_status"] == "failed"
    assert active_payload["quality_attempt"] == 2
    assert active_payload["quality_report"] == second_report
    assert active_payload["quality_status"] == "passed"

    with db.transaction() as conn:
        conn.execute(
            "UPDATE job_steps SET quality_attempt=9, quality_report='{}' WHERE id=?",
            (step_id,),
        )
    unchanged = client.get(
        "/api/workspace/project-a/assets", params={"active": "true"}
    ).json()[0]
    assert unchanged["quality_attempt"] == 2
    assert unchanged["quality_report"] == second_report


def test_asset_bound_regeneration_reuses_review_state_machine_without_incrementing_quality_attempt(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, step_id, asset = _job_with_asset(db, jobs, workspace, quality_attempt=2)

    response = client.post(f"/api/workspace/project-a/assets/{asset.id}/regenerate")

    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == job_id
    assert detail["status"] == "queued"
    reviewed_step = next(step for step in detail["steps"] if step["id"] == step_id)
    assert reviewed_step["status"] == "queued"
    assert reviewed_step["quality_attempt"] == 2


def test_asset_bound_regeneration_hides_cross_project_assets(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, step_id, asset = _job_with_asset(db, jobs, workspace)

    response = client.post(f"/api/workspace/project-b/assets/{asset.id}/regenerate")

    assert response.status_code == 404
    assert response.json() == {"detail": "素材不存在"}
    assert jobs.get_job(job_id)["status"] == "waiting_review"
    assert jobs.get_step(step_id)["status"] == "waiting_review"


def test_asset_bound_regeneration_rejects_non_review_state_without_mutation(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, step_id, asset = _job_with_asset(
        db,
        jobs,
        workspace,
        job_status=JobStatus.RUNNING,
        step_status=StepStatus.RUNNING,
    )

    response = client.post(f"/api/workspace/project-a/assets/{asset.id}/regenerate")

    assert response.status_code == 409
    assert response.json() == {"detail": "该素材版本当前不处于待审核状态"}
    assert jobs.get_job(job_id)["status"] == "running"
    assert jobs.get_step(step_id)["status"] == "running"
    assert jobs.get_step(step_id)["quality_attempt"] == 1


def test_asset_bound_regeneration_requires_the_asset_step_to_be_the_review_step(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, asset_step_id, asset = _job_with_asset(db, jobs, workspace)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO job_steps (id, job_id, sequence, stage_key, shot_id, status) VALUES (?,?,?,?,?,?)",
            ("step-other", job_id, 1, "visual_generate", "shot_04", "waiting_review"),
        )
        conn.execute("UPDATE job_steps SET status='completed' WHERE id=?", (asset_step_id,))

    response = client.post(f"/api/workspace/project-a/assets/{asset.id}/regenerate")

    assert response.status_code == 409
    assert response.json() == {"detail": "该素材版本当前不处于待审核状态"}
    assert jobs.get_step("step-other")["status"] == "waiting_review"


def test_asset_bound_regeneration_rejects_an_inactive_version_without_mutation(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, step_id, old_asset = _job_with_asset(db, jobs, workspace)
    jobs.add_artifact(
        job_id,
        step_id,
        "image",
        "outputs/shot_03-v2.png",
        "sha-v2",
        {},
    )
    jobs.save_quality_report(
        step_id,
        {"overall_score": 0.63, "passed": False, "issues": ["构图偏移"]},
    )

    response = client.post(
        f"/api/workspace/project-a/assets/{old_asset.id}/regenerate"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "该素材版本当前不处于待审核状态"}
    assert jobs.get_job(job_id)["status"] == "waiting_review"
    assert jobs.get_step(step_id)["status"] == "waiting_review"


def test_review_expected_step_mismatch_is_atomic(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, step_id, _ = _job_with_asset(db, jobs, workspace)
    service = client.app.state.job_service

    with pytest.raises(ValueError, match="review"):
        service.review(job_id, "retry", expected_step_id="step-stale")

    assert jobs.get_job(job_id)["status"] == "waiting_review"
    assert jobs.get_step(step_id)["status"] == "waiting_review"


def test_job_review_route_returns_404_for_a_missing_job(tmp_path):
    client, _, _, _ = _environment(tmp_path)
    safe_client = TestClient(client.app, raise_server_exceptions=False)

    response = safe_client.post(
        "/api/jobs/job-missing/review",
        json={"action": "retry"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "任务不存在"}


def test_job_review_route_returns_409_for_a_non_review_job_without_mutation(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, step_id, _ = _job_with_asset(
        db,
        jobs,
        workspace,
        job_status=JobStatus.RUNNING,
        step_status=StepStatus.RUNNING,
    )
    safe_client = TestClient(client.app, raise_server_exceptions=False)

    response = safe_client.post(
        f"/api/jobs/{job_id}/review",
        json={"action": "retry"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "任务当前不处于待审核状态"}
    assert jobs.get_job(job_id)["status"] == "running"
    assert jobs.get_step(step_id)["status"] == "running"


def test_job_review_route_returns_409_to_a_losing_stale_review_request(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, step_id, _ = _job_with_asset(db, jobs, workspace)
    safe_client = TestClient(client.app, raise_server_exceptions=False)

    winner = safe_client.post(
        f"/api/jobs/{job_id}/review",
        json={"action": "retry"},
    )
    stale = safe_client.post(
        f"/api/jobs/{job_id}/review",
        json={"action": "retry"},
    )

    assert winner.status_code == 200
    assert stale.status_code == 409
    assert stale.json() == {"detail": "任务当前不处于待审核状态"}
    assert jobs.get_job(job_id)["status"] == "queued"
    assert jobs.get_step(step_id)["status"] == "queued"


def test_job_review_route_rejects_an_unknown_action_without_mutation(tmp_path):
    client, db, jobs, workspace = _environment(tmp_path)
    job_id, step_id, _ = _job_with_asset(db, jobs, workspace)
    safe_client = TestClient(client.app, raise_server_exceptions=False)

    response = safe_client.post(
        f"/api/jobs/{job_id}/review",
        json={"action": "destroy"},
    )

    assert response.status_code == 422
    assert jobs.get_job(job_id)["status"] == "waiting_review"
    assert jobs.get_step(step_id)["status"] == "waiting_review"
