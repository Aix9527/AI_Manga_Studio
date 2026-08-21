from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.characters import routes as character_routes
from backend.characters.service import CharacterService


@pytest.fixture
def client_and_root(tmp_path, monkeypatch):
    service = CharacterService(str(tmp_path / "characters.db"), media_roots=[tmp_path])
    monkeypatch.setattr(character_routes, "service", service)
    app = FastAPI()
    app.include_router(character_routes.router)
    return TestClient(app), tmp_path


def test_character_image_relationship_and_consistency_contract(client_and_root):
    client, _root = client_and_root
    first = client.post("/api/characters/", json={
        "name": "林默", "novel_id": "novel-a", "appearance": {}, "personality": {},
    }).json()
    second = client.post("/api/characters/", json={
        "name": "苏晚", "novel_id": "novel-a", "appearance": {}, "personality": {},
    }).json()

    image = client.post("/api/characters/images", params={
        "character_id": first["id"],
        "image_path": "refs/林默 正面.png",
        "image_type": "front_view",
        "is_primary": False,
    })
    assert image.status_code == 200
    images = client.get(f"/api/characters/{first['id']}/images").json()
    assert images[0]["file_path"] == "refs/林默 正面.png"
    assert images[0]["image_type"] == "front_view"

    relationship = client.post("/api/characters/relationships", json={
        "character_id": first["id"],
        "related_id": second["id"],
        "relation_type": "friend",
        "description": "共同守城",
    })
    assert relationship.status_code == 200
    relationships = client.get(f"/api/characters/{first['id']}/relationships").json()
    assert relationships[0]["character_id"] == first["id"]
    assert relationships[0]["related_id"] == second["id"]
    assert relationships[0]["related_name"] == "苏晚"

    consistency = client.get(
        f"/api/characters/{first['id']}/consistency",
        params={"image_path": "generated/林默.png"},
    )
    assert consistency.status_code == 200
    assert consistency.json() == {
        "character_id": first["id"],
        "consistent": True,
        "score": 1.0,
        "threshold": 0.75,
        "reason": "no_reference",
    }


def test_character_media_is_served_by_image_id_and_rejects_unsafe_recorded_paths(client_and_root):
    client, media_root = client_and_root
    character = client.post("/api/characters/", json={"name": "林默"}).json()
    image_bytes = b"\x89PNG\r\n\x1a\ncanonical-reference"
    image_path = media_root / "refs" / "front.png"
    image_path.parent.mkdir()
    image_path.write_bytes(image_bytes)
    image = client.post("/api/characters/images", params={
        "character_id": character["id"], "image_path": str(image_path), "image_type": "front_view",
    }).json()

    response = client.get(f"/api/characters/media/{image['id']}")
    assert response.status_code == 200
    assert response.content == image_bytes
    assert response.headers["content-type"] == "image/png"
    assert "content-disposition" not in response.headers

    outside_path = media_root.parent / "outside.png"
    outside_path.write_bytes(image_bytes)
    unsafe = client.post("/api/characters/images", params={
        "character_id": character["id"], "image_path": str(outside_path), "image_type": "front_view",
    }).json()
    assert client.get(f"/api/characters/media/{unsafe['id']}").status_code == 403
    assert client.get("/api/characters/media/missing-image").status_code == 404
