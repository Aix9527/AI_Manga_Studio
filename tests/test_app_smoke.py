"""Application startup smoke tests."""

from fastapi.testclient import TestClient

from backend.app.bootstrap import create_application
from backend.modules.platform.infrastructure.settings import AppSettings


def test_application_starts_and_health_endpoint_responds(tmp_path) -> None:
    settings = AppSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        projects_root=str(tmp_path / "projects"),
        environment="test",
    )
    app = create_application(settings)

    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
