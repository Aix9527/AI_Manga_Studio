# -*- coding: utf-8 -*-
"""双引擎调度 — 镜头级引擎选择（GPT Round-5 批准版：H3-first）。

用户指令：视频模型使用 MiniMax H3（优先级高于 Round-4 的"Wan 普通镜 + H3 高光镜"）。

策略（Round-5 批准）：
  - H3-first 模式：默认 engine = minimax_h3，Wan 仅作为失败恢复/成本保护通道
  - ``video_engine_policy.primary_engine == "minimax_h3"`` 时所有镜头默认走 H3，
    除非镜头显式指定 ``engine: wan22_native``（fallback / 低风险镜）
  - 兼容旧模式：无 primary_engine 设置时保留 Round-4 的 premium 关键词路由
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

ENGINE_WAN = "wan22_native"
ENGINE_MINIMAX = "minimax_h3"

# Premium 镜头信号词（H3-first 关闭时命中任一即用 MiniMax H3）
_PREMIUM_KEYWORDS = (
    "opening", "first appearance", "awaken", "awakening", "climax",
    "cliffhanger", "emotional outburst", "transformation", "explosion",
    "opening shot", "title sequence", "开场", "首次登场", "觉醒",
    "高潮", "悬念", "结尾", "爆发", "变身", "爆炸", "片尾",
)

# H3 显存护栏（GPT Round-5 批准版，16GB 显存环境）
#   max_default_duration: H3 普通镜时长上限（10s 稳定）
#   premium_duration:    高潮/爆点镜允许时长（12-15s，OOM 风险需配合 lifecycle）
#   max_parallel_jobs:   并发数（H3 单任务，避免显存叠加）
#   vram_guard_mb:       切换引擎前要求的显存余量
DEFAULT_H3_POLICY: dict[str, Any] = {
    "max_default_duration": 10.0,
    "premium_duration": 15.0,
    "max_parallel_jobs": 1,
    "vram_guard_mb": 2000,
}

# 镜头类型 -> H3 时长上限（GPT Round-5 Duration Policy v1）
DURATION_POLICY_V1: dict[str, tuple[float, float]] = {
    "establishing": (5.0, 5.0),       # 开场/环境：5s
    "dialogue": (5.0, 8.0),           # 对白：5-8s
    "emotion_closeup": (8.0, 10.0),   # 情绪特写：8-10s
    "character_motion": (8.0, 10.0),  # 人物动作：8-10s
    "action": (10.0, 10.0),           # 动作：10s
    "climax": (12.0, 15.0),           # 高潮：12-15s
    "transition": (3.0, 5.0),         # 转场：3-5s
}


@dataclass(frozen=True)
class EngineDecision:
    engine: str                  # wan22_native / minimax_h3
    premium: bool
    reason: str

    def to_dict(self) -> dict:
        return {"engine": self.engine, "premium": self.premium, "reason": self.reason}


def _is_h3_first(settings: dict | None) -> bool:
    """H3-first 模式开关：video_engine_policy.primary_engine == minimax_h3。"""
    settings = settings or {}
    policy = settings.get("video_engine_policy") or {}
    if isinstance(policy, str):
        return "minimax" in policy.lower() or "h3" in policy.lower()
    if isinstance(policy, dict):
        primary = str(policy.get("primary_engine", "")).lower()
        return primary in (ENGINE_MINIMAX, "minimax_h3", "h3")
    return str(policy).lower() in (ENGINE_MINIMAX, "minimax_h3", "h3")


def decide_engine(shot: dict[str, Any], settings: dict | None = None) -> EngineDecision:
    """Decide which video engine a shot should use.

    Round-5（用户指令：视频模型使用 MiniMax H3）:
      H3-first 模式下默认 minimax_h3；显式 ``engine: wan22_native`` 才用 Wan。
      兼容旧模式（无 primary_engine 设置）时保留 Round-4 的 premium 关键词路由。

    Priority:
      1. explicit ``engine`` / ``video_engine`` on the shot
      2. H3-first 模式 -> 默认 minimax_h3
      3. explicit ``premium_shot`` bool（旧模式）
      4. premium keyword match（旧模式）
      5. default -> wan22_native（旧模式兜底）
    """
    shot = shot or {}
    settings = settings or {}

    explicit = str(shot.get("engine") or shot.get("video_engine") or "").lower()
    if explicit in (ENGINE_MINIMAX, "minimax_h3", "h3"):
        return EngineDecision(ENGINE_MINIMAX, True, "explicit engine")
    if explicit in (ENGINE_WAN, "wan22", "wan"):
        return EngineDecision(ENGINE_WAN, False, "explicit engine")

    # Round-5: H3-first —— 用户指定 H3 为主模型，默认所有镜头走 H3
    if _is_h3_first(settings):
        return EngineDecision(ENGINE_MINIMAX, True, "h3-first default")

    if shot.get("premium_shot") is True:
        return EngineDecision(ENGINE_MINIMAX, True, "premium_shot flag")

    text = " ".join(
        str(shot.get(k, "")) for k in (
            "description", "narration", "shot_type", "camera", "scene",
        )
    ).lower()
    if any(kw in text for kw in _PREMIUM_KEYWORDS):
        return EngineDecision(ENGINE_MINIMAX, True, "premium keyword")

    # 显式设置层兜底
    engine_setting = str(settings.get("video_engine", "")).lower()
    if engine_setting in (ENGINE_MINIMAX, "minimax_h3"):
        return EngineDecision(ENGINE_MINIMAX, True, "settings engine")

    return EngineDecision(ENGINE_WAN, False, "default wan22")


def h3_duration_for(shot: dict[str, Any], settings: dict | None = None) -> float:
    """按镜头类型解析 H3 目标时长（GPT Round-5 Duration Policy v1）。

    - climax / extreme_action / premium_shot -> premium 上限（15s，护栏内）
    - 其余镜头按 DURATION_POLICY_V1 区间取中值，并封顶 max_default_duration
    """
    shot = shot or {}
    settings = settings or {}
    h3_policy = dict(DEFAULT_H3_POLICY)
    user_policy = settings.get("h3_policy") or {}
    if isinstance(user_policy, dict):
        h3_policy.update({k: v for k, v in user_policy.items() if v is not None})
    max_default = float(h3_policy.get("max_default_duration", 10.0))
    premium_max = float(h3_policy.get("premium_duration", 15.0))

    explicit = shot.get("target_duration_s")
    if explicit:
        return max(3.0, min(premium_max, float(explicit)))

    shot_class = str(shot.get("shot_class") or shot.get("scene_type") or "").lower()
    # 高潮/极限动作：允许 premium 时长
    if shot.get("premium_shot") is True or shot_class in ("climax", "extreme_action"):
        lo, hi = DURATION_POLICY_V1.get("climax", (12.0, 15.0))
        return max(lo, min(premium_max, hi))

    lo, hi = DURATION_POLICY_V1.get(shot_class, (5.0, 10.0))
    # 区间中值，先满足镜头类型下限，再受全局默认时长上限封顶
    return max(3.0, min(max_default, max(lo, (lo + hi) / 2.0)))


def engine_for_duration(engine: str, duration_target_s: float) -> tuple[int, int]:
    """按引擎返回 (frames, fps) 生成规格。

    - Wan2.2 native: 5s @ 16fps = 81 帧（短镜高吞吐）
    - MiniMax H3: 10-15s @ 24fps（长镜质量优先）
    """
    if engine == ENGINE_MINIMAX:
        fps = 24
        frames = max(5, int(round(min(15.0, max(10.0, duration_target_s)) * fps)))
        return frames, fps
    fps = 16
    frames = max(33, int(round(min(6.0, max(4.0, duration_target_s)) * fps)))
    return frames, fps
