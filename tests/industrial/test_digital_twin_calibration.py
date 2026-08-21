"""Phase 15.2: Digital Twin Calibration v1.1 tests. """

from __future__ import annotations

import json

import pytest

from backend.digital_twin.service import DigitalTwinService


@pytest.fixture()
def service(tmp_path):
    return DigitalTwinService(root=str(tmp_path))


def _seed_events(tmp_path, n: int = 10):
    (tmp_path / "production_intelligence").mkdir(parents=True, exist_ok=True)
    events = {}
    for i in range(n):
        events[f"EV{i}"] = {
            "id": f"EV{i}", "event_type": "generation_end",
            "project_id": "P1", "episode_id": f"EP{i % 5 + 1}", "shot_id": f"S{i}",
            "payload": {"lead_time_s": 100.0 + (i % 4) * 5, "quality": 0.85},
        }
    (tmp_path / "production_intelligence" / "events.json").write_text(
        json.dumps(events, ensure_ascii=False), encoding="utf-8")


def test_collect_baseline(service, tmp_path):
    _seed_events(tmp_path, n=10)
    result = service.calibration()
    assert result["samples"] == 10
    baseline = result["baseline"]
    assert baseline is not None
    assert baseline["mean_s"] == 106.5          # 100,105,110,115 循环均值
    assert baseline["n"] == 10
    assert 0.3 <= baseline["confidence"] <= 0.95
    assert baseline["uncertainty_range_s"] > 0


def test_apply_to_simulation(service, tmp_path):
    _seed_events(tmp_path, n=10)
    service.calibration()
    sim = service.simulate(scenario_keys=["baseline", "20_episodes"])
    assert sim["calibrated"] is True
    for row in sim["results"]:
        assert "calibration" in row
        assert row["calibration"]["mean_s"] == 106.5
        assert row["eta_s_low"] <= row["eta_s"] <= row["eta_s_high"]
        assert row["calibration"]["confidence"] > 0


def test_calibration_state_persisted(service, tmp_path):
    _seed_events(tmp_path, n=5)
    service.calibration()
    state = service.calibration_state()
    assert state["baseline"]["n"] == 5
    # 幂等：重复 collect 不重复累计样本
    service.calibration()
    state2 = service.calibration_state()
    assert state2["baseline"]["n"] == 5
