"""Production Snapshot（统一统计口径）测试。"""

from __future__ import annotations

import sys
import time

import pytest

sys.path.insert(0, "F:/AI_Manga_Studio")


@pytest.fixture()
def snapshot(tmp_path):
    from backend.production_pilot.snapshot import ProductionSnapshot

    out = tmp_path / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (out / f"EP001-S0{i + 1}.mp4").write_bytes(b"\x00")
    return ProductionSnapshot(root=str(tmp_path / "storage"), outputs=str(out))


def test_snapshot_has_unified_fields(snapshot):
    snap = snapshot.snapshot()
    assert snap["version"] == "1.0"
    assert snap["generated_at"]
    assert snap["production"]["generated_shots"] == 3
    assert snap["production"]["plan_shots"] == 1000
    assert snap["production"]["generation_success_rate"] == 0.3
    assert snap["production"]["batch_status"] == "NONE"
    # 统一口径键必须存在
    for section in ("production", "analytics", "knowledge_graph", "orchestration", "digital_twin", "sources"):
        assert section in snap


def test_snapshot_persists_to_json(snapshot, tmp_path):
    snapshot.snapshot()
    target = tmp_path / "storage" / "production_pilot" / "snapshot.json"
    assert target.exists()
    loaded = snapshot.load()
    assert loaded["production"]["generated_shots"] == 3


def test_batch_status_thresholds():
    from backend.production_pilot.snapshot import ProductionSnapshot

    assert ProductionSnapshot._batch_status(100) == "A"
    assert ProductionSnapshot._batch_status(300) == "A+B+C"
    assert ProductionSnapshot._batch_status(1000) == "COMPLETE"


def test_snapshot_api_endpoint():
    from fastapi.testclient import TestClient

    import backend.main as main

    client = TestClient(main.app)
    resp = client.get("/api/production-pilot/snapshot")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "generated_at" in data
    assert "production" in data
