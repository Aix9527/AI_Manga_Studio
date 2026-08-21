from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.migration.scanner import ProjectScanner
from backend.orchestration.database import OrchestrationDatabase
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.routes import router
from backend.workspace.service import WorkspaceService


@pytest.fixture
def client(tmp_path):
    return _workspace_client(tmp_path)[0]


def _workspace_client(tmp_path, scanner: ProjectScanner | None = None):
    app = FastAPI()
    db = OrchestrationDatabase(str(tmp_path / "workspace.db"))
    repo = WorkspaceRepository(db)
    app.state.workspace_repo = repo
    app.state.workspace_service = WorkspaceService(db, repo, scanner)
    app.include_router(router)
    return TestClient(app), repo


def test_update_one_stage_does_not_change_other_stages(client):
    response = client.put("/api/workspace/gui-xu/automation/keyframe", json={
        "stage_key": "keyframe",
        "auto_produce": False,
        "quality_threshold": 0.82,
        "max_quality_retries": 2,
        "auto_advance": False,
        "provider_settings": {},
    })

    assert response.status_code == 200
    snapshot = client.get("/api/workspace/gui-xu").json()
    by_key = {item["stage_key"]: item["automation"] for item in snapshot["stages"]}
    assert by_key["keyframe"]["auto_produce"] is False
    assert by_key["video"]["auto_produce"] is True


def test_rejects_retry_count_above_limit(client):
    response = client.put("/api/workspace/gui-xu/automation/keyframe", json={
        "stage_key": "keyframe",
        "max_quality_retries": 3,
    })

    assert response.status_code == 422


def test_rejects_body_stage_that_differs_from_path(client):
    response = client.put("/api/workspace/gui-xu/automation/keyframe", json={
        "stage_key": "video",
    })

    assert response.status_code == 422
    assert response.json()["detail"] == "阶段标识不一致"


def test_initial_snapshot_prefers_scanned_project_name_over_id_fallback(tmp_path):
    source_root = tmp_path / "legacy-projects"
    scanned_project = source_root / "归墟"
    scanned_project.mkdir(parents=True)
    (scanned_project / "chapter.txt").write_text("第一章", encoding="utf-8")
    db = OrchestrationDatabase(str(tmp_path / "workspace.db"))
    service = WorkspaceService(
        db,
        WorkspaceRepository(db),
        ProjectScanner(str(source_root)),
    )

    snapshot = service.get_snapshot("gui-xu")

    assert snapshot.title == "归墟"
    assert snapshot.source_path == str(scanned_project)


def test_get_initial_snapshot_serializes_scanned_name_and_source_path(tmp_path):
    source_root = tmp_path / "legacy-projects"
    scanned_project = source_root / "归墟"
    scanned_project.mkdir(parents=True)
    (scanned_project / "chapter.txt").write_text("第一章", encoding="utf-8")
    client, _ = _workspace_client(tmp_path, ProjectScanner(str(source_root)))

    response = client.get("/api/workspace/gui-xu")

    assert response.status_code == 200
    assert response.json()["title"] == "归墟"
    assert response.json()["source_path"] == str(scanned_project)


def test_first_put_persists_scanned_project_metadata(tmp_path):
    source_root = tmp_path / "legacy-projects"
    scanned_project = source_root / "归墟"
    scanned_project.mkdir(parents=True)
    (scanned_project / "chapter.txt").write_text("第一章", encoding="utf-8")
    client, repo = _workspace_client(tmp_path, ProjectScanner(str(source_root)))

    response = client.put("/api/workspace/gui-xu/automation/keyframe", json={
        "stage_key": "keyframe",
    })

    assert response.status_code == 200
    assert repo.get_project("gui-xu") == {
        "project_id": "gui-xu",
        "title": "归墟",
        "source_path": str(scanned_project),
        "version": 1,
    }


def test_get_initial_snapshot_falls_back_to_project_id_without_scanned_candidate(tmp_path):
    source_root = tmp_path / "empty-projects"
    source_root.mkdir()
    client, _ = _workspace_client(tmp_path, ProjectScanner(str(source_root)))

    response = client.get("/api/workspace/gui-xu")

    assert response.status_code == 200
    assert response.json()["title"] == "gui-xu"
    assert response.json()["source_path"] == ""
