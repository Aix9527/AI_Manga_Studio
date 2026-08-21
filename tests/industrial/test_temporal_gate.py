"""Phase 15.3-D: Vision Critic Temporal Gate tests. """

from __future__ import annotations

from pathlib import Path

from backend.video.temporal_gate import check_temporal_stability


def test_temporal_gate_structural():
    """对已有 MiniMaxH3 15s 产物运行 Temporal 门禁（结构验证，非断言阈值）。"""
    candidates = sorted(Path("outputs/minimax_h3").glob("MMH3-*.mp4"))
    if not candidates:
        return  # 无产物时跳过（CI 环境）
    for p in candidates:
        r = check_temporal_stability(p)
        assert "score" in r and "ssim_mean" in r and "passed" in r
        assert r["frames_sampled"] >= 3
        assert 0.0 <= r["score"] <= 100.0


def test_temporal_gate_consistent_synthetic():
    """合成静态序列应得高分（验证指标方向正确）。"""
    import numpy as np
    from backend.video.temporal_gate import _ssim
    a = np.full((100, 100), 128.0)
    b = a.copy()
    assert _ssim(a, b) == 1.0
    c = a.copy() + 40.0
    assert _ssim(a, c) < 1.0
