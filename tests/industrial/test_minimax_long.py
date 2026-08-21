"""Phase 15.3-E: MiniMaxH3 长视频（3-5 分钟）多段生成 tests. """

from __future__ import annotations

from backend.video.providers.minimax_h3_provider import SHOT_MAX_SECONDS


def test_shot_splitting_math():
    """3 分钟 = 180s / 15s 每段 = 12 段；5 分钟 = 20 段。"""
    total = 3 * 60
    n3 = -(-total // int(SHOT_MAX_SECONDS))
    assert n3 == 12
    total5 = 5 * 60
    n5 = -(-total5 // int(SHOT_MAX_SECONDS))
    assert n5 == 20
    # 最后段时长
    rem = total5 - (n5 - 1) * int(SHOT_MAX_SECONDS)
    assert rem == 15


def test_extract_last_frame(tmp_path):
    """用已有 MiniMaxH3 视频验证尾帧提取（存在则跑）。"""
    from pathlib import Path
    from backend.video.providers.minimax_long import _extract_last_frame
    candidates = sorted(Path("outputs/minimax_h3").glob("MMH3-*.mp4"))
    if not candidates:
        return
    out = tmp_path / "last.png"
    _extract_last_frame(candidates[0], out)
    assert out.exists() and out.stat().st_size > 0
