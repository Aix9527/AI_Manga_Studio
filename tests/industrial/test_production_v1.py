"""AI_Manga_Studio v1.0 Phase 1: Production Director tests.

GPT Phase 1 完成标准：创建项目 / 任务树 / Agent 调度 / 状态恢复 / 断点继续。
"""

from __future__ import annotations

import asyncio
import pytest

from backend.production_v1.director import ProductionDirector
from backend.production_v1.model import ProductionStore


@pytest.fixture()
def director(tmp_path):
    return ProductionDirector(store=ProductionStore(str(tmp_path / "p1")))


def test_create_project_generates_task_tree(director):
    project = director.create_project(name="归墟觉醒", duration_seconds=300)
    assert project["state"] == "init"
    assert len(project["tasks"]) >= 9   # script → final_export
    types = [t["task_type"] for t in project["tasks"]]
    assert types[0] == "script_analysis"
    assert "final_export" in types
    assert all(t["status"] == "WAITING" for t in project["tasks"])


def test_start_project_transitions_to_script(director):
    project = director.create_project(name="P", duration_seconds=300)
    status = director.start(project["id"])
    assert status["current"] == "script_analysis"
    assert status["progress"] == 8
    running = [t for t in status["tasks"] if t["status"] == "RUNNING"]
    assert any(t["task_type"] == "script_analysis" for t in running)


def test_advance_through_stages(director):
    project = director.create_project(name="P", duration_seconds=300)
    director.start(project["id"])
    current = "script_analysis"
    for _ in range(12):   # 推进到 final_export
        status = director.advance(project["id"], stage=current, result={"ok": True})
        assert status["current"] != "failed"
        if status["current"] == "final_export":
            break
        current = status["current"]
    final = director.status(project["id"])
    assert final["progress"] >= 90
    assert final["current"] == "final_export"


def test_illegal_transition_rejected(director):
    project = director.create_project(name="P", duration_seconds=300)
    # init 只允许 → script_analysis；直接到 video 非法
    from backend.production_v1.model import ProductionProject
    p = ProductionProject.from_dict(director.store.get_project(project["id"]))
    with pytest.raises(ValueError, match="illegal transition"):
        director._transition(p, "video_generation")


def test_state_recovery_and_resume(director, tmp_path):
    """状态恢复 + 断点继续：重新实例化后状态保留。"""
    project = director.create_project(name="P", duration_seconds=300)
    director.start(project["id"])
    director.advance(project["id"], stage="script_analysis", result={"script": "..."})

    # 重新实例化（模拟重启）
    director2 = ProductionDirector(store=ProductionStore(str(tmp_path / "p1")))
    status = director2.status(project["id"])
    assert status["current"] == "character_design"
    assert status["progress"] > 8
    # 断点继续
    director2.advance(project["id"], stage="character_design", result={"characters": ["陈夜"]})
    assert director2.status(project["id"])["current"] == "world_building"

# ── Phase SSE：Agent Runtime 实时推送 ──────────────────────────────

@pytest.mark.asyncio()
async def test_sse_subscribe_and_broadcast():
    import json
    from backend.production_v1.sse import ProductionSSE

    hub = ProductionSSE()
    received: list[str] = []

    async def reader():
        async for chunk in hub.subscribe():
            received.append(chunk)
            if len(received) >= 2:
                break

    task = asyncio.create_task(reader())
    await asyncio.sleep(0.05)
    await hub.broadcast({"type": "production_status", "project_id": "P1",
                         "status": {"current": "script_analysis", "progress": 8}})
    await asyncio.wait_for(task, timeout=3)

    assert "connected" in received[0]
    payload = json.loads(received[1].split("data: ", 1)[1])
    assert payload["type"] == "production_status"
    assert payload["project_id"] == "P1"
    assert payload["status"]["current"] == "script_analysis"

@pytest.mark.asyncio()
async def test_sse_subscriber_cleanup_on_close():
    from backend.production_v1.sse import ProductionSSE

    hub = ProductionSSE()
    gen = hub.subscribe()
    await gen.__anext__()   # connected
    await gen.aclose()
    assert len(hub._subscribers) == 0