from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.pipeline import routes as pipeline_routes


def test_compile_shot_accepts_repeated_character_query_and_flat_json(monkeypatch):
    context_calls = []
    compile_calls = []

    class FakeCharacterAgent:
        def get_context(self, character_id, shot_id, emotion):
            context_calls.append((character_id, shot_id, emotion))
            return {"character_id": character_id}

    class FakePromptCompiler:
        def compile_shot(self, brief, contexts):
            compile_calls.append((brief, contexts))
            return SimpleNamespace(
                positive_prompt="cinematic storm coast",
                negative_prompt="text, watermark",
                parameters={"seed": 17},
            )

    monkeypatch.setattr(
        pipeline_routes,
        "orchestrator",
        SimpleNamespace(
            character_agent=FakeCharacterAgent(),
            prompt_compiler=FakePromptCompiler(),
        ),
    )
    app = FastAPI()
    app.include_router(pipeline_routes.router)
    client = TestClient(app)

    response = client.post(
        "/api/pipeline/compile/shot?character_ids=char-a&character_ids=char-b",
        json={
            "id": "shot-1",
            "scene_id": "scene-1",
            "index": 0,
            "shot_type": "wide",
            "camera_angle": "eye-level",
            "description": "风暴中的海堤",
            "action": "守塔人扶住栏杆",
            "emotion": "紧张",
            "character_ids": ["char-a", "char-b"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "positive_prompt": "cinematic storm coast",
        "negative_prompt": "text, watermark",
        "parameters": {"seed": 17},
    }
    assert context_calls == [
        ("char-a", "shot-1", "紧张"),
        ("char-b", "shot-1", "紧张"),
    ]
    assert set(compile_calls[0][1]) == {"char-a", "char-b"}
