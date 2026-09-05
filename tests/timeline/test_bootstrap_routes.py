import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.timeline.repository import TimelineRepository
from backend.timeline.routes import router
from backend.timeline.service import TimelineService


def _seed_video_artifact(db: OrchestrationDatabase, *, project_id: str, shot_id: str, version: int, artifact_id: int) -> None:
    job_id = f"job-{artifact_id}"
    step_id = f"step-{artifact_id}"
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO jobs
               (id, project_id, status, input_path, input_type, settings, idempotency_key)
               VALUES (?,?, 'completed', '', 'novel', '{}', ?)""",
            (job_id, project_id, f"seed-{artifact_id}"),
        )
        conn.execute(
            """INSERT INTO job_steps
               (id, job_id, sequence, stage_key, shot_id, status)
               VALUES (?,?,0,'video_generate',?,'completed')""",
            (step_id, job_id, shot_id),
        )
        conn.execute(
            """INSERT INTO artifacts
               (id, job_id, step_id, kind, path, sha256, metadata, active,
                project_id, version, stage_key, scene_id, shot_id, quality_status)
               VALUES (?,?,?,?,?,?,?,1,?,?, 'video_generate','',?,'passed')""",
            (
                artifact_id,
                job_id,
                step_id,
                'video',
                f"outputs/{shot_id}-v{version}.mp4",
                f"sha-{artifact_id}",
                json.dumps({"duration_tick": 2_000_000}),
                project_id,
                version,
                shot_id,
            ),
        )


def _client(tmp_path: Path) -> tuple[TestClient, OrchestrationDatabase, Path]:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    db = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    repo = TimelineRepository(db, projects_root=projects_root)
    service = TimelineService(repo)
    app = FastAPI()
    app.state.timeline_service = service
    app.include_router(router)
    return TestClient(app), db, projects_root


def test_initialize_orders_active_video_assets_by_production_plan(tmp_path):
    client, db, projects_root = _client(tmp_path)
    project_id = "project-a"
    project_dir = projects_root / project_id
    project_dir.mkdir()
    (project_dir / "production_plan.json").write_text(
        json.dumps({"shots": [{"id": "shot_001"}, {"id": "shot_002"}]}),
        encoding="utf-8",
    )
    _seed_video_artifact(db, project_id=project_id, shot_id="shot_002", version=1, artifact_id=2)
    _seed_video_artifact(db, project_id=project_id, shot_id="shot_001", version=1, artifact_id=1)

    response = client.post(f"/api/projects/{project_id}/timeline/initialize")

    assert response.status_code == 201
    draft = response.json()
    v1 = next(track for track in draft["tracks"] if track["role"] == "video.main")
    assert [clip["shot_id"] for clip in v1["clips"]] == ["shot_001", "shot_002"]
    assert [clip["timeline_start_tick"] for clip in v1["clips"]] == [0, 2_000_000]
    assert draft["revision"] == 0


def test_initialize_is_idempotent_and_never_overwrites_existing_draft(tmp_path):
    client, db, projects_root = _client(tmp_path)
    project_id = "project-a"
    (projects_root / project_id).mkdir()
    _seed_video_artifact(db, project_id=project_id, shot_id="shot_001", version=1, artifact_id=1)

    first = client.post(f"/api/projects/{project_id}/timeline/initialize")
    second = client.post(f"/api/projects/{project_id}/timeline/initialize")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["timeline_id"] == first.json()["timeline_id"]
    assert second.json()["draft_id"] == first.json()["draft_id"]


def test_bootstrap_pins_highest_active_version_per_shot(tmp_path):
    client, db, projects_root = _client(tmp_path)
    project_id = "project-a"
    (projects_root / project_id).mkdir()
    _seed_video_artifact(db, project_id=project_id, shot_id="shot_001", version=1, artifact_id=1)
    _seed_video_artifact(db, project_id=project_id, shot_id="shot_001", version=2, artifact_id=2)

    response = client.post(f"/api/projects/{project_id}/timeline/initialize")

    clip = next(track for track in response.json()["tracks"] if track["role"] == "video.main")["clips"][0]
    assert clip["artifact_id"] == 2
    assert clip["artifact_version"] == 2


def test_get_project_timeline_and_draft_lifecycle(tmp_path):
    client, db, projects_root = _client(tmp_path)
    project_id = "project-a"
    (projects_root / project_id).mkdir()
    _seed_video_artifact(db, project_id=project_id, shot_id="shot_001", version=1, artifact_id=1)

    missing = client.get(f"/api/projects/{project_id}/timeline")
    assert missing.status_code == 404

    created = client.post(f"/api/projects/{project_id}/timeline/initialize").json()
    summary = client.get(f"/api/projects/{project_id}/timeline")
    draft = client.get(f"/api/timelines/{created['timeline_id']}/draft")

    assert summary.status_code == 200
    assert summary.json()["timeline_id"] == created["timeline_id"]
    assert draft.status_code == 200
    assert draft.json()["draft_id"] == created["draft_id"]
