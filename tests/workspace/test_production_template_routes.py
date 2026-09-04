from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.routes import router
from backend.workspace.service import WorkspaceService


def _client(tmp_path):
    app = FastAPI()
    db = OrchestrationDatabase(str(tmp_path / "workspace.db"))
    repo = WorkspaceRepository(db)
    app.state.workspace_service = WorkspaceService(db, repo)
    app.include_router(router)
    return TestClient(app)


def _payload():
    return {
        "name": "默认制作模板",
        "schema_version": 1,
        "canvas": {
            "nodes": [
                {"id": "novel", "data": {"stageKey": "load_input"}},
                {"id": "scene", "data": {"stageKey": "planning"}},
                {"id": "character", "data": {"stageKey": "character_design"}},
                {"id": "storyboard", "data": {"stageKey": "planning"}},
                {"id": "keyframe", "data": {"stageKey": "visual_generate"}},
                {"id": "video", "data": {"stageKey": "video_generate"}},
                {"id": "audio", "data": {"stageKey": "audio_tts"}},
                {"id": "export", "data": {"stageKey": "composition_compose"}},
            ],
            "edges": [
                {"source": "novel", "target": "scene"},
                {"source": "scene", "target": "character"},
                {"source": "character", "target": "storyboard"},
                {"source": "storyboard", "target": "keyframe"},
                {"source": "keyframe", "target": "video"},
                {"source": "video", "target": "audio"},
                {"source": "audio", "target": "export"},
            ],
        },
        "production": {
            "shot_duration": 6,
            "width": 1080,
            "height": 1920,
            "fps": 24,
            "options": {"style": "anime", "local_first": True},
        },
        "stage_policy": {"stages": []},
    }


def test_save_list_read_publish_and_rollback(tmp_path):
    client = _client(tmp_path)

    first = client.post("/api/workspace/project-a/production-templates", json=_payload())
    second_payload = _payload()
    second_payload["name"] = "第二版"
    second = client.post("/api/workspace/project-a/production-templates", json=second_payload)

    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert second.status_code == 200
    assert second.json()["version"] == 2

    listing = client.get("/api/workspace/project-a/production-templates")
    assert listing.status_code == 200
    assert listing.json()["latest_version"] == 2
    assert listing.json()["published_version"] is None

    read = client.get("/api/workspace/project-a/production-templates/1")
    assert read.status_code == 200
    assert read.json()["name"] == "默认制作模板"

    publish_v2 = client.post("/api/workspace/project-a/production-templates/2/publish")
    assert publish_v2.status_code == 200
    assert publish_v2.json()["version"] == 2

    rollback = client.post("/api/workspace/project-a/production-templates/1/publish")
    assert rollback.status_code == 200
    assert rollback.json()["version"] == 1

    published = client.get("/api/workspace/project-a/production-template/published")
    assert published.status_code == 200
    assert published.json()["published"] is True
    assert published.json()["template"]["version"] == 1


def test_no_published_template_is_explicit_success(tmp_path):
    client = _client(tmp_path)

    response = client.get("/api/workspace/project-a/production-template/published")

    assert response.status_code == 200
    assert response.json() == {
        "project_id": "project-a",
        "published": False,
        "template": None,
    }


def test_missing_or_cross_project_version_returns_404(tmp_path):
    client = _client(tmp_path)
    client.post("/api/workspace/project-a/production-templates", json=_payload())

    missing = client.get("/api/workspace/project-a/production-templates/99")
    cross_project = client.get("/api/workspace/project-b/production-templates/1")

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "TEMPLATE_VERSION_NOT_FOUND"
    assert cross_project.status_code == 404
    assert cross_project.json()["detail"]["code"] == "TEMPLATE_VERSION_NOT_FOUND"


def test_invalid_template_fails_closed_with_machine_readable_code(tmp_path):
    client = _client(tmp_path)
    payload = _payload()
    payload["production"]["options"]["skip_qc"] = True

    response = client.post("/api/workspace/project-a/production-templates", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TEMPLATE_VALIDATION_FAILED"
    assert "forbidden" in response.json()["detail"]["message"]


def test_unsupported_required_provider_returns_422(tmp_path):
    client = _client(tmp_path)
    payload = _payload()
    payload["stage_policy"] = {
        "stages": [
            {
                "stage_key": "video_generate",
                "provider_policy": {"mode": "required", "provider": "unknown_provider"},
            }
        ]
    }

    response = client.post("/api/workspace/project-a/production-templates", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "TEMPLATE_PROVIDER_POLICY_UNSUPPORTED"
