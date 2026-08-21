# -*- coding: utf-8 -*-
"""GPT Round-5: H3-first 引擎策略 + Duration Policy v1 tests."""

from __future__ import annotations

from backend.production.engine_policy import (
    ENGINE_MINIMAX,
    ENGINE_WAN,
    decide_engine,
    h3_duration_for,
)

H3_FIRST = {"video_engine_policy": {"primary_engine": "minimax_h3"}}


def test_h3_first_defaults_to_minimax():
    """H3-first 模式下默认所有镜头走 MiniMax H3（用户指令：视频模型使用 H3）。"""
    dec = decide_engine({"id": "S01", "description": "实验室开场"}, H3_FIRST)
    assert dec.engine == ENGINE_MINIMAX
    assert dec.reason == "h3-first default"


def test_h3_first_respects_explicit_wan():
    """H3-first 下显式 engine=wan22_native 的镜头仍用 Wan（fallback 通道）。"""
    dec = decide_engine({"id": "S02", "engine": "wan22_native"}, H3_FIRST)
    assert dec.engine == ENGINE_WAN
    assert dec.reason == "explicit engine"


def test_h3_first_respects_explicit_h3():
    dec = decide_engine({"id": "S03", "engine": "minimax_h3"}, H3_FIRST)
    assert dec.engine == ENGINE_MINIMAX


def test_legacy_mode_without_policy_uses_premium_keywords():
    """无 video_engine_policy 时保留 Round-4 行为：premium 关键词 -> H3。"""
    dec = decide_engine({"id": "S04", "description": "主角首次觉醒"})
    assert dec.engine == ENGINE_MINIMAX
    dec2 = decide_engine({"id": "S05", "description": "普通对白"})
    assert dec2.engine == ENGINE_WAN


def test_h3_duration_climax_is_premium():
    """高潮/极限动作镜 -> 15s（premium 上限）。"""
    assert h3_duration_for({"shot_class": "climax"}, H3_FIRST) == 15.0
    assert h3_duration_for({"shot_class": "extreme_action"}, H3_FIRST) == 15.0


def test_h3_duration_regular_capped_at_10s():
    """普通镜按 Duration Policy 区间取中值并封顶 10s。"""
    assert h3_duration_for({"shot_class": "dialogue"}, H3_FIRST) == 6.5
    assert h3_duration_for({"shot_class": "establishing"}, H3_FIRST) == 5.0
    assert h3_duration_for({"shot_class": "action"}, H3_FIRST) == 10.0


def test_h3_duration_explicit_target():
    """显式 target_duration_s 优先（在 3-15s 护栏内）。"""
    assert h3_duration_for({"target_duration_s": 12.0}, H3_FIRST) == 12.0


def test_h3_duration_respects_custom_policy():
    """用户可覆盖 h3_policy 护栏。"""
    settings = {"h3_policy": {"max_default_duration": 8.0}}
    assert h3_duration_for({"shot_class": "dialogue"}, settings) == 6.5
    assert h3_duration_for({"shot_class": "action"}, settings) == 8.0
