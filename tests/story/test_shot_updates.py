import importlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.story import routes as story_routes
from backend.story.graph import StoryGraphEngine
from backend.story.models import Chapter, Scene, Shot


def _engine(db_path):
    repository_module = importlib.import_module("backend.story.repository")
    return StoryGraphEngine(repository_module.StoryRepository(str(db_path)))


def _client(engine, monkeypatch) -> TestClient:
    monkeypatch.setattr(story_routes, "graph_engine", engine)
    app = FastAPI()
    app.include_router(story_routes.router)
    return TestClient(app)


def _seed(engine: StoryGraphEngine, novel_id: str = "novel-director") -> tuple[str, str]:
    chapter = Chapter(id="chapter-1", novel_id=novel_id, number=1, title="潮汐")
    first_scene = Scene(
        id="scene-1",
        chapter_id=chapter.id,
        number=1,
        title="海堤",
        summary="风暴逼近海堤",
        shots=["shot-1", "shot-2"],
    )
    second_scene = Scene(
        id="scene-2",
        chapter_id=chapter.id,
        number=2,
        title="灯塔",
        summary="守塔人点亮灯火",
        shots=["shot-3"],
    )
    shots = [
        Shot(
            id="shot-1",
            scene_id=first_scene.id,
            index=0,
            shot_type="wide",
            camera_angle="eye-level",
            description="海浪越过防波堤",
            character_ids=["char-a"],
        ),
        Shot(
            id="shot-2",
            scene_id=first_scene.id,
            index=1,
            shot_type="medium",
            camera_angle="low-angle",
            description="守塔人抬头望向灯塔",
            character_ids=["char-a", "char-b"],
        ),
    ]
    third = Shot(
        id="shot-3",
        scene_id=second_scene.id,
        index=2,
        shot_type="close-up",
        camera_angle="high-angle",
        description="灯芯燃起",
    )
    hierarchy = [(chapter, [(first_scene, shots), (second_scene, [third])])]
    engine.build_graph(novel_id, "潮汐", hierarchy)
    return shots[0].id, shots[1].id


def test_old_sqlite_shots_gain_defaults_and_ignore_future_fields(tmp_path):
    db_path = tmp_path / "story.db"
    engine = _engine(db_path)
    _seed(engine)

    with engine.repository._conn() as connection:
        row = connection.execute(
            "SELECT hierarchy_json FROM story_records WHERE novel_id = ?",
            ("novel-director",),
        ).fetchone()
        hierarchy = json.loads(row["hierarchy_json"])
        shot = hierarchy[0]["scenes"][0]["shots"][0]
        for field in (
            "camera_movement",
            "duration",
            "narration",
            "positive_prompt",
            "negative_prompt",
            "seed",
            "image_model",
            "video_model",
            "thumbnail_url",
            "production_status",
            "quality_status",
        ):
            shot.pop(field, None)
        shot["future_director_field"] = "must not crash"
        connection.execute(
            "UPDATE story_records SET hierarchy_json = ? WHERE novel_id = ?",
            (json.dumps(hierarchy, ensure_ascii=False), "novel-director"),
        )

    recovered = _engine(db_path).get_hierarchy_for_novel("novel-director")
    restored = recovered[0][1][0][1][0]
    assert restored.camera_movement == "static"
    assert restored.duration == 5.0
    assert restored.narration == ""
    assert restored.positive_prompt == ""
    assert restored.negative_prompt == ""
    assert restored.seed == 0
    assert restored.image_model == ""
    assert restored.video_model == ""
    assert restored.thumbnail_url == ""
    assert restored.production_status == "pending"
    assert restored.quality_status == "unreviewed"


def test_get_scenes_restores_canonical_hierarchy_and_missing_is_chinese_404(tmp_path, monkeypatch):
    db_path = tmp_path / "story.db"
    _seed(_engine(db_path))
    client = _client(_engine(db_path), monkeypatch)

    response = client.get("/api/story/graph/novel-director/scenes")
    assert response.status_code == 200
    scenes = response.json()
    assert [scene["id"] for scene in scenes] == ["scene-1", "scene-2"]
    assert [[shot["id"] for shot in scene["shots"]] for scene in scenes] == [
        ["shot-1", "shot-2"],
        ["shot-3"],
    ]
    assert scenes[0]["shots"][0]["duration"] == 5.0

    missing = client.get("/api/story/graph/missing/scenes")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "故事结构不存在"


def test_get_scenes_never_returns_legacy_local_thumbnail_paths(tmp_path, monkeypatch):
    db_path = tmp_path / "story.db"
    engine = _engine(db_path)
    _seed(engine)
    with engine.repository._conn() as connection:
        row = connection.execute(
            "SELECT hierarchy_json FROM story_records WHERE novel_id = ?",
            ("novel-director",),
        ).fetchone()
        hierarchy = json.loads(row["hierarchy_json"])
        hierarchy[0]["scenes"][0]["shots"][0]["thumbnail_url"] = r"C:\shots\local.png"
        connection.execute(
            "UPDATE story_records SET hierarchy_json = ? WHERE novel_id = ?",
            (json.dumps(hierarchy, ensure_ascii=False), "novel-director"),
        )

    scenes = _client(_engine(db_path), monkeypatch).get(
        "/api/story/graph/novel-director/scenes"
    ).json()
    assert scenes[0]["shots"][0]["thumbnail_url"] == ""


def test_patch_updates_only_target_shot_and_survives_restart(tmp_path, monkeypatch):
    db_path = tmp_path / "story.db"
    engine = _engine(db_path)
    first_id, second_id = _seed(engine)
    client = _client(engine, monkeypatch)

    response = client.patch(
        f"/api/story/novel-director/shots/{first_id}",
        json={
            "shot_type": "close-up",
            "camera_movement": "dolly-in",
            "duration": 7.5,
            "narration": "潮水吞没最后一级台阶。",
            "positive_prompt": "cinematic storm",
            "negative_prompt": "text, watermark",
            "seed": 42,
            "image_model": "flux-2",
            "video_model": "ltx-2.3",
            "thumbnail_url": "https://cdn.example.test/shot-1.png",
            "production_status": "ready",
            "quality_status": "approved",
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == first_id
    assert updated["shot_type"] == "close-up"
    assert updated["duration"] == 7.5
    assert updated["seed"] == 42

    scenes = client.get("/api/story/graph/novel-director/scenes").json()
    assert [shot["id"] for shot in scenes[0]["shots"]] == [first_id, second_id]
    untouched = scenes[0]["shots"][1]
    assert untouched["description"] == "守塔人抬头望向灯塔"
    assert untouched["duration"] == 5.0

    restarted = _client(_engine(db_path), monkeypatch)
    persisted = restarted.get("/api/story/graph/novel-director/scenes").json()[0]["shots"][0]
    assert persisted == updated


def test_sequential_patch_requests_persist_the_last_confirmed_edit(tmp_path, monkeypatch):
    db_path = tmp_path / "story.db"
    engine = _engine(db_path)
    first_id, _ = _seed(engine)
    client = _client(engine, monkeypatch)

    first = client.patch(
        f"/api/story/novel-director/shots/{first_id}",
        json={"duration": 6, "narration": "第一版"},
    )
    second = client.patch(
        f"/api/story/novel-director/shots/{first_id}",
        json={"duration": 8, "narration": "第二版"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duration"] == 8
    assert second.json()["narration"] == "第二版"
    current = client.get("/api/story/graph/novel-director/scenes").json()[0]["shots"][0]
    restarted = _client(_engine(db_path), monkeypatch)
    persisted = restarted.get("/api/story/graph/novel-director/scenes").json()[0]["shots"][0]
    assert current["duration"] == 8
    assert current["narration"] == "第二版"
    assert persisted == current


@pytest.mark.parametrize(
    "payload",
    [
        {"duration": 0.9},
        {"duration": 30.1},
        {"seed": -1},
        {"seed": 4_294_967_296},
        {"future_field": "rejected"},
    ],
)
def test_patch_rejects_out_of_range_and_unknown_fields(tmp_path, monkeypatch, payload):
    engine = _engine(tmp_path / "story.db")
    first_id, _ = _seed(engine)
    response = _client(engine, monkeypatch).patch(
        f"/api/story/novel-director/shots/{first_id}", json=payload
    )
    assert response.status_code == 422


def test_patch_returns_chinese_404_for_missing_novel_or_shot(tmp_path, monkeypatch):
    engine = _engine(tmp_path / "story.db")
    _seed(engine)
    client = _client(engine, monkeypatch)

    missing_novel = client.patch(
        "/api/story/missing/shots/shot-1", json={"duration": 4}
    )
    missing_shot = client.patch(
        "/api/story/novel-director/shots/missing", json={"duration": 4}
    )

    assert missing_novel.status_code == 404
    assert missing_novel.json()["detail"] == "故事结构不存在"
    assert missing_shot.status_code == 404
    assert missing_shot.json()["detail"] == "镜头不存在"


def test_failed_patch_save_does_not_pollute_cache_or_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "story.db"
    engine = _engine(db_path)
    first_id, _ = _seed(engine)
    client = _client(engine, monkeypatch)
    before = client.get("/api/story/graph/novel-director/scenes").json()

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("disk unavailable")

    monkeypatch.setattr(engine.repository, "save_story", fail_save)
    with pytest.raises(RuntimeError, match="disk unavailable"):
        client.patch(
            f"/api/story/novel-director/shots/{first_id}",
            json={"description": "幽灵新版", "duration": 9},
        )

    assert client.get("/api/story/graph/novel-director/scenes").json() == before
    restarted = _client(_engine(db_path), monkeypatch)
    assert restarted.get("/api/story/graph/novel-director/scenes").json() == before
