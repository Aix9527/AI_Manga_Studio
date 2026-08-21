import pytest

from backend.production.h3_unified.segment_planner import (
    align_h3_frames,
    parse_segment_script,
)


def test_align_h3_frames_uses_17n_plus_5_grid_without_shortening_duration():
    assert align_h3_frames(5.0) == 124
    assert align_h3_frames(10.0) == 243
    assert align_h3_frames(15.0) == 362

    frames = align_h3_frames(7.25)
    assert frames % 17 == 5
    assert frames >= round(7.25 * 24)


def test_parse_segment_script_splits_markers_clamps_duration_and_keeps_stable_seeds():
    segments = parse_segment_script(
        """
        雨夜，苏晚推开实验楼大门。\n& 4 &
        ===
        镜头绕到她身后，走廊灯光依次亮起。\n& 10.2 &
        ===
        能量爆发，镜头快速拉远。\n& 20 &
        """,
        base_seed=9000,
    )

    assert [segment.index for segment in segments] == [0, 1, 2]
    assert [segment.duration_seconds for segment in segments] == [5.0, 10.2, 15.0]
    assert [segment.seed for segment in segments] == [9000, 9001, 9002]
    assert all(segment.frames % 17 == 5 for segment in segments)
    assert all("&" not in segment.prompt for segment in segments)
    assert segments[0].prompt == "雨夜，苏晚推开实验楼大门。"
    assert segments[2].continuity_from_index == 1


def test_parse_segment_script_defaults_to_five_seconds_when_duration_marker_is_absent():
    segments = parse_segment_script("第一段动作===第二段动作", base_seed=42)

    assert [segment.duration_seconds for segment in segments] == [5.0, 5.0]
    assert [segment.frames for segment in segments] == [124, 124]
    assert [segment.continuity_from_index for segment in segments] == [None, 0]


def test_parse_segment_script_reports_empty_segment_with_human_index():
    with pytest.raises(ValueError, match="segment 2 is empty"):
        parse_segment_script("第一段===   ===第三段", base_seed=1)


def test_parse_segment_script_rejects_non_numeric_duration_marker():
    with pytest.raises(ValueError, match="segment 1 has invalid duration marker"):
        parse_segment_script("动作描述\n& ten &", base_seed=1)
