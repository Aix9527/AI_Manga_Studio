"""GPT Round-1 新模块测试：VideoContract / ActionPrompt / MotionBucket / Handoff。

运行: python -m pytest tests/video/test_round1_gpt.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.production.video_contract import (
    VIDEO_CONTRACT,
    VideoProbe,
    validate_video,
)
from backend.video.action_prompts import (
    ANATOMY_GUARD_NEGATIVES,
    ActionBeat,
    build_negative_prompt,
    split_shot_prompt,
)
from backend.video.duration_strategy import resolve_motion_bucket


class TestVideoContract:
    def test_good_probe_passes(self):
        probe = VideoProbe(
            width=480, height=832, fps=16.0, duration=5.06,
            frame_count=81, size_bytes=1_200_000,
        )
        assert validate_video(probe) == []

    def test_bad_probe_catches_2s_576(self):
        # 复现 EP001-S01 的 2.08s/576x576/12fps 问题
        probe = VideoProbe(
            width=576, height=576, fps=12.0, duration=2.08,
            frame_count=25, size_bytes=159_627,
        )
        errors = validate_video(probe)
        assert "duration_too_short:2.08" in errors
        assert "wrong_aspect_ratio:576x576" in errors
        assert "fps_too_low:12.0" in errors
        assert "suspiciously_small_file:159627" in errors
        assert "too_few_frames:25" in errors

    def test_allow_cuts_relaxes_frames(self):
        probe = VideoProbe(
            width=1080, height=1920, fps=24.0, duration=15.1,
            frame_count=100, size_bytes=5_000_000,
        )
        assert validate_video(probe, allow_cuts=True) == []

    def test_contract_has_quality_threshold(self):
        assert VIDEO_CONTRACT["min_visual_quality"] >= 0.70


class TestActionPrompts:
    def test_anatomy_guard_contains_key_terms(self):
        joined = ", ".join(ANATOMY_GUARD_NEGATIVES).lower()
        for term in ("extra fingers", "deformed face", "bad anatomy", "duplicate limbs"):
            assert term in joined

    def test_build_negative_prompt_merges_base(self):
        neg = build_negative_prompt("low quality")
        assert neg.startswith("low quality, ")
        assert "extra fingers" in neg

    def test_split_shot_prompt_with_explicit_fields(self):
        out = split_shot_prompt({
            "image_prompt": "Su Wan grips sword",
            "motion_prompt": "ONE clean slash",
        })
        assert out["image_prompt"] == "Su Wan grips sword"
        assert out["motion_prompt"] == "ONE clean slash"

    def test_split_shot_prompt_single_action_guard(self):
        out = split_shot_prompt({
            "positive_prompt": "Su Wan 蓄力",
            "description": "Su Wan 蓄力，然后向前冲刺挥剑。",
        })
        # 无显式 motion_prompt 时，附加单动作约束
        assert "No additional actions" in out["motion_prompt"]

    def test_action_beat_enum(self):
        assert ActionBeat.ATTACK.value == "attack"
        assert ActionBeat.IMPACT.value == "impact"


class TestMotionBucket:
    def test_explicit_wins(self):
        assert resolve_motion_bucket({"motion_bucket_id": 200}) == 200

    def test_shot_type_maps_to_fight_bucket(self):
        assert resolve_motion_bucket({"shot_type": "sword_punch"}) == 160

    def test_motion_level_4_maps_to_action(self):
        assert resolve_motion_bucket({"motion_level": 4}) == 175

    def test_default_balanced(self):
        assert resolve_motion_bucket({}) == 60
