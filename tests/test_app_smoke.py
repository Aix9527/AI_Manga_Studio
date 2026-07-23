"""Application startup smoke tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.bootstrap import create_application
from backend.modules.platform.infrastructure.settings import AppSettings


def build_test_settings(tmp_path: Path) -> AppSettings:
    database_path = (tmp_path / "test.db").as_posix()

    return AppSettings(
        database_url=f"sqlite+aiosqlite:///{database_path}",
        projects_root=tmp_path / "projects",
        environment="test",
        fake_provider_enabled=True,
    )


def test_application_starts_and_builds_container(tmp_path: Path) -> None:
    app = create_application(build_test_settings(tmp_path))

    with TestClient(app) as client:
        assert hasattr(client.app.state, "container")
        assert client.app.state.container is not None


def test_health_endpoint_reports_database_ok(tmp_path: Path) -> None:
    app = create_application(build_test_settings(tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["components"]["database"] == "ok"
    assert payload["environment"] == "test"


def test_openapi_schema_can_be_generated(tmp_path: Path) -> None:
    app = create_application(build_test_settings(tmp_path))

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()
    assert schema["info"]["title"] == "AI Manga Studio"
    assert "/api/v1/health" in schema["paths"]


def test_swagger_docs_are_available(tmp_path: Path) -> None:
    app = create_application(build_test_settings(tmp_path))

    with TestClient(app) as client:
        response = client.get("/docs")

    assert response.status_code == 200


def test_database_file_is_created(tmp_path: Path) -> None:
    app = create_application(build_test_settings(tmp_path))
    database_path = tmp_path / "test.db"

    with TestClient(app):
        assert database_path.exists()
