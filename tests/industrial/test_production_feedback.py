"""Phase 15.2: 真实生产反馈采集 tests（Director / Prompt / ShotDNA）. """

from __future__ import annotations

import json

import pytest

from backend.production_pilot.feedback_stats import ProductionFeedbackCollector


@pytest.fixture()
def collector(tmp_path):
    return ProductionFeedbackCollector(root=str(tmp_path))


def _seed_events(tmp_path):
    (tmp_path / "production_intelligence").mkdir(parents=True, exist_ok=True)
    events = {}
    for i in range(6):
        events[f"EV{i}"] = {
            "id": f"EV{i}", "event_type": "generation_end",
            "project_id": "P1", "episode_id": f"EP{i % 2 + 1}", "shot_id": f"S{i}",
            "payload": {
                "quality": 0.85 if i % 3 else 0.55,
                "director": "导演A" if i % 2 == 0 else "导演B",
                "prompt_version": "pv1",
                "shot_dna_id": "SHDNA-1",
            },
        }
    (tmp_path / "production_intelligence" / "events.json").write_text(
        json.dumps(events, ensure_ascii=False), encoding="utf-8")


def test_collect_director_prompt_dna(collector, tmp_path):
    _seed_events(tmp_path)
    stats = collector.collect()
    assert len(stats["directors"]) == 2
    assert len(stats["prompt_versions"]) == 1
    assert len(stats["shot_dna"]) == 1
    dna = stats["shot_dna"][0]
    assert dna["usage"] == 6
    assert dna["success_rate"] == 0.667         # 6 中 4 成功（quality>=0.7）
    assert dna["avg_quality"] == pytest.approx(0.75, abs=0.01)


def test_apply_shot_dna_stats(collector, tmp_path):
    _seed_events(tmp_path)
    (tmp_path / "shot_dna").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shot_dna" / "library.json").write_text(json.dumps({
        "SHDNA-1": {"id": "SHDNA-1", "name": "慢推", "usage_count": 0, "success_rate": 0.8},
    }, ensure_ascii=False), encoding="utf-8")
    result = collector.apply_shot_dna_stats()
    assert result["applied"] == 1
    lib = json.loads((tmp_path / "shot_dna" / "library.json").read_text(encoding="utf-8"))
    entry = lib["SHDNA-1"]
    assert entry["usage_count"] == 6
    assert entry["success_rate"] == pytest.approx(0.667, abs=0.001)


def test_report_note(collector, tmp_path):
    _seed_events(tmp_path)
    report = collector.report()
    assert report["director_router_performance"]
    assert "auto_apply=false" in report["note"]
