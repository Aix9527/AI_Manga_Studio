"""Motion profile tests — GPT P0: scene/motion-level → reference_strength/frames mapping.

GPT Round-4 更新：
  - 六档 profile（新增 extreme_action level=5）
  - denoise 改名 reference_strength（denoise 为兼容属性）
  - dialogue 0.78 / action 0.86 / extreme_action 0.88
"""
from backend.video.duration_strategy import (
    MOTION_PROFILES,
    get_motion_profile,
    get_shot_motion_level,
)


def test_all_motion_levels_have_profiles():
    assert set(MOTION_PROFILES.keys()) == {0, 1, 2, 3, 4, 5}
    for level, profile in MOTION_PROFILES.items():
        assert profile.level == level
        assert 0.50 <= profile.reference_strength <= 0.95
        assert profile.denoise == profile.reference_strength  # 兼容别名
        assert profile.frames >= 33


def test_dialogue_shot_maps_to_dialogue_motion():
    shot = {"id": "shot_01", "description": "两人深夜对话", "dialogue": ["你真的要去吗"]}
    profile = get_motion_profile(shot)
    assert profile.level == 1
    assert profile.reference_strength == 0.78


def test_action_shot_maps_to_extreme_action_when_explosion():
    shot = {"id": "shot_02", "description": "追逐打斗，爆炸四起", "camera": "handheld tracking"}
    # 爆炸/特效关键词 -> extreme_action (level 5)
    assert get_shot_motion_level(shot) == 5
    assert get_motion_profile(shot).reference_strength == 0.88


def test_plain_action_shot_stays_action():
    shot = {"description": "两人持剑打斗", "camera": "handheld"}
    assert get_shot_motion_level(shot) == 4
    assert get_motion_profile(shot).reference_strength == 0.86


def test_camera_keywords_promote_dialogue_to_camera_motion():
    shot = {"description": "主角对话", "camera": "slow dolly in"}
    assert get_shot_motion_level(shot) == 3


def test_explicit_motion_level_wins():
    shot = {"description": "静态对白", "motion_level": 4}
    assert get_shot_motion_level(shot) == 4


def test_motion_profile_name_direct():
    shot = {"motion_profile": "extreme_action"}
    assert get_shot_motion_level(shot) == 5
    assert get_motion_profile(shot).reference_strength == 0.88


def test_establishing_shot_uses_camera_motion():
    shot = {"description": "城市全景鸟瞰", "camera": "aerial establishing shot"}
    assert get_shot_motion_level(shot) == 3


def test_invalid_explicit_level_falls_back_to_classification():
    shot = {"description": "安静的对话", "motion_level": 99}
    assert get_shot_motion_level(shot) == 1
