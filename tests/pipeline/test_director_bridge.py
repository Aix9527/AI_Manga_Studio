from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.director.director_bridge import DirectorBridge
from backend.pipeline import routes as pipeline_routes

_SNIPPET = """凌晨三点十七分，京城大学基因考古实验室。苏晚盯着屏幕上的基因序列，眉头紧锁。
她按下红色按钮，警报响起，走廊灯光开始闪烁。

地下通道。陈夜打着手电筒，脚步声在甬道中回荡。
他看见青铜门上刻着从未见过的文字，心跳加速。"""


def test_plan_text_returns_full_directives(tmp_path):
    bridge = DirectorBridge(llm_provider=None)  # deterministic rule-only
    result = bridge.plan_text(_SNIPPET, "test_novel")
    assert result["shots_total"] >= 1
    assert result["scenes"] >= 1
    for d in result["directives"]:
        assert d["shot_id"]
        assert d["camera"]["angle"]
        assert d["camera"]["movement"]
        assert d["lighting"]
        assert d["emotion_curve"]
        assert "previous_shot" in d["continuity"]
    # continuity threads shot ids in order
    ids = [d["shot_id"] for d in result["directives"]]
    for i in range(1, len(ids)):
        assert result["directives"][i]["continuity"]["previous_shot"] == ids[i - 1]


def test_plan_text_section_memory_persist(tmp_path):
    bridge = DirectorBridge(llm_provider=None, section_memory=__import__("backend.story.section_memory", fromlist=["StorySectionMemory"]).StorySectionMemory(storage_dir=str(tmp_path / "sec")))
    result = bridge.plan_text(_SNIPPET, "novel_p", persist=True)
    assert result["sections"]
    assert (tmp_path / "sec").exists()
    loaded = bridge.section_memory.list_sections("novel_p")
    assert len(loaded) == result["scenes"]


def test_director_plan_route(monkeypatch):
    monkeypatch.setattr("backend.director.director_bridge.default_llm_provider", lambda: None)
    app = FastAPI()
    app.include_router(pipeline_routes.router)
    client = TestClient(app)
    resp = client.post("/api/pipeline/director/plan", json={"text": _SNIPPET, "novel_id": "route_novel"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["shots_total"] >= 1
    assert len(body["directives"]) == body["shots_total"]
    assert body["directives"][0]["camera"]["angle"]
