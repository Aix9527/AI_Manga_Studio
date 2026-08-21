import importlib
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.story import routes as story_routes
from backend.story.graph import StoryGraphEngine


def _engine(db_path):
    repository_module = importlib.import_module("backend.story.repository")
    repository = repository_module.StoryRepository(str(db_path))
    return StoryGraphEngine(repository)


def _client(engine, monkeypatch) -> TestClient:
    monkeypatch.setattr(story_routes, "graph_engine", engine)
    app = FastAPI()
    app.include_router(story_routes.router)
    return TestClient(app)


def test_canonical_story_survives_new_engine_and_all_routes_share_domain_ids(tmp_path, monkeypatch):
    db_path = tmp_path / "story.db"
    novel_id = f"novel-{uuid4().hex}"
    text = (
        "Chapter 1 Tide\n"
        "The lighthouse keeper watches a violent silver storm cross the distant harbor.\n\n\n"
        "A rescue boat turns toward the black rocks while warning bells ring across the town.\n"
    )
    first_client = _client(_engine(db_path), monkeypatch)

    parsed_response = first_client.post(
        "/api/story/parse", json={"text": text, "novel_id": novel_id}
    )
    assert parsed_response.status_code == 200
    parsed = parsed_response.json()
    assert parsed["novel_id"] == novel_id
    assert parsed["scenes"]
    assert all(scene["chapter_id"] for scene in parsed["scenes"])

    # A new engine and a new app must recover the canonical hierarchy from SQLite.
    second_client = _client(_engine(db_path), monkeypatch)
    graph_response = second_client.get(f"/api/story/graph/{novel_id}")
    shots_response = second_client.get(f"/api/story/graph/{novel_id}/shots")
    scenes_response = second_client.post(
        "/api/story/parse/scenes", json={"text": "不同文本也不得重解析", "novel_id": novel_id}
    )

    assert graph_response.status_code == 200
    assert shots_response.status_code == 200
    assert scenes_response.status_code == 200
    graph = graph_response.json()
    shots = shots_response.json()
    scenes = scenes_response.json()["scenes"]
    assert graph["id"] == parsed["graph_id"]
    assert scenes == parsed["scenes"]
    assert shots == [shot for scene in parsed["scenes"] for shot in scene["shots"]]

    chapter_ids = {chapter["id"] for chapter in parsed["chapters"]}
    scene_ids = {scene["id"] for scene in scenes}
    shot_ids = {shot["id"] for shot in shots}
    domain_ids = chapter_ids | scene_ids | shot_ids
    assert {node["id"] for node in graph["nodes"]} == domain_ids
    assert all(node["data"]["id"] == node["id"] for node in graph["nodes"])
    assert all(edge["source"] in domain_ids and edge["target"] in domain_ids for edge in graph["edges"])
    assert not any(
        english in node["label"]
        for node in graph["nodes"]
        for english in ("Chapter", "Scene", "Shot")
    )

    by_id = {node["id"]: node for node in graph["nodes"]}
    for scene in scenes:
        assert by_id[scene["id"]]["parent_id"] == scene["chapter_id"]
        for shot in scene["shots"]:
            assert by_id[shot["id"]]["parent_id"] == scene["id"]
            assert shot["scene_id"] == scene["id"]


def test_graph_route_returns_404_only_when_repository_has_no_record(tmp_path, monkeypatch):
    client = _client(_engine(tmp_path / "story.db"), monkeypatch)
    response = client.get(f"/api/story/graph/missing-{uuid4().hex}")

    assert response.status_code == 404
    assert response.json()["detail"] == "未找到故事结构"


def test_failed_replacement_save_keeps_old_cache_and_old_sqlite_record(tmp_path, monkeypatch):
    db_path = tmp_path / "story.db"
    novel_id = "novel-transaction"
    engine = _engine(db_path)
    client = _client(engine, monkeypatch)
    old_text = "Chapter 1 Old Tide\nThe old harbor guard watches the water rise beyond the city gate."
    new_text = "Chapter 1 New Tide\nThe new harbor wall collapses while the patrol sounds an alarm."
    assert client.post(
        "/api/story/parse", json={"text": old_text, "novel_id": novel_id}
    ).status_code == 200
    old_graph = client.get(f"/api/story/graph/{novel_id}").json()

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("disk unavailable")

    monkeypatch.setattr(engine.repository, "save_story", fail_save)
    with pytest.raises(RuntimeError, match="disk unavailable"):
        client.post("/api/story/parse", json={"text": new_text, "novel_id": novel_id})

    assert client.get(f"/api/story/graph/{novel_id}").json() == old_graph
    restarted_client = _client(_engine(db_path), monkeypatch)
    assert restarted_client.get(f"/api/story/graph/{novel_id}").json() == old_graph


def test_failed_first_save_does_not_leave_ghost_story(tmp_path, monkeypatch):
    db_path = tmp_path / "story.db"
    novel_id = "novel-first-failure"
    engine = _engine(db_path)
    client = _client(engine, monkeypatch)

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("disk unavailable")

    monkeypatch.setattr(engine.repository, "save_story", fail_save)
    with pytest.raises(RuntimeError, match="disk unavailable"):
        client.post("/api/story/parse", json={
            "text": "An untitled story begins beside the harbor as every lighthouse turns on before the storm.",
            "novel_id": novel_id,
        })

    assert engine.get_graph_for_novel(novel_id) is None
    assert client.get(f"/api/story/graph/{novel_id}").status_code == 404
    assert _engine(db_path).get_graph_for_novel(novel_id) is None


def test_untitled_story_uses_chinese_fallback_in_parse_and_graph(tmp_path, monkeypatch):
    novel_id = "novel-untitled"
    client = _client(_engine(tmp_path / "story.db"), monkeypatch)
    response = client.post("/api/story/parse", json={
        "text": "The harbor town closes its gates before the storm while a guard checks every lighthouse.",
        "novel_id": novel_id,
    })

    assert response.status_code == 200
    assert response.json()["title"] == "第 1 章"
    graph = client.get(f"/api/story/graph/{novel_id}").json()
    assert graph["title"] == "第 1 章"
    assert "Chapter" not in response.text
    assert "Chapter" not in client.get(f"/api/story/graph/{novel_id}").text
