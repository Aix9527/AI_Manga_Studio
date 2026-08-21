"""Phase 15.2-E（三维分析 + DT 校准）测试。"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "F:/AI_Manga_Studio")


@pytest.fixture()
def feedback():
    return {
        "director_router_performance": [
            {"key": "导演A", "usage": 100, "success_rate": 0.95, "avg_quality": 0.83},
            {"key": "导演B", "usage": 50, "success_rate": 1.0, "avg_quality": 0.85},
        ],
        "prompt_os_feedback": [
            {"key": "pv1", "usage": 120, "success_rate": 0.97, "avg_quality": 0.828},
            {"key": "cinedance-v1", "usage": 1, "success_rate": 1.0, "avg_quality": 0.88},
        ],
        "shot_dna_feedback": [
            {"key": "dna2", "usage": 102, "success_rate": 1.0, "avg_quality": 0.82},
            {"key": "dnaX", "usage": 3, "success_rate": 1.0, "avg_quality": 0.9},
        ],
    }


def test_e1_director_sorted_by_quality(feedback):
    from backend.production_pilot.phase_e import PhaseEAnalyzer

    out = PhaseEAnalyzer().director_analysis(feedback)
    assert out[0]["director"] == "导演B"
    assert out[1]["director"] == "导演A"


def test_e2_prompt_roi_sorted(feedback):
    from backend.production_pilot.phase_e import PhaseEAnalyzer

    shots = [{"prompt_version": "pv1", "gpu_cost": 0.03} for _ in range(5)]
    out = PhaseEAnalyzer().prompt_roi(feedback, shots)
    assert out[0]["prompt_version"] == "cinedance-v1"
    assert out[0]["avg_quality"] == 0.88
    assert any(r["prompt_version"] == "pv1" and r["avg_gpu_cost"] == 0.03 for r in out)


def test_e3_shot_dna_mining_filters_low_sample(feedback):
    from backend.production_pilot.phase_e import PhaseEAnalyzer

    out = PhaseEAnalyzer().shot_dna_mining(feedback, [])
    names = [d["shot_dna"] for d in out]
    assert "dna2" in names
    assert "dnaX" not in names  # 样本 <5 被过滤


def test_e4_dt_calibration_present():
    from backend.production_pilot.phase_e import PhaseEAnalyzer

    cal = PhaseEAnalyzer().dt_calibration()
    assert "status" in cal
    assert "n" in cal


def test_analyze_has_all_sections():
    from backend.production_pilot.phase_e import PhaseEAnalyzer

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PhaseEAnalyzer, "director_analysis", lambda self, f: [])
        mp.setattr(PhaseEAnalyzer, "prompt_roi", lambda self, f, s: [])
        mp.setattr(PhaseEAnalyzer, "shot_dna_mining", lambda self, f, s: [])
        mp.setattr(PhaseEAnalyzer, "dt_calibration", lambda self: {"status": "PASS"})
        mp.setattr(PhaseEAnalyzer, "_recommend", lambda self, f, s: {"next": "F"})
        r = PhaseEAnalyzer().analyze()
    for key in ("E1_director_analysis", "E2_prompt_roi", "E3_shot_dna_mining", "E4_dt_calibration", "recommendation"):
        assert key in r
    assert r["governance"]["auto_apply"] is False
