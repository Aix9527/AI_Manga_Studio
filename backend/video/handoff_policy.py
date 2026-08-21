# -*- coding: utf-8 -*-
"""Handoff Policy — 镜间衔接策略（GPT Round-4 批准版）。

Round-3 已证明：下一镜输入 = 上一镜 handoff 帧可把 continuity 从 0.47 提升到 0.99。
但**不是所有镜头都该继承上一镜尾帧**：

  - 新场景（实验室 -> 城市）硬继承会污染色调/构图/空间；
  - 同场景换角度是弱继承；
  - 连续动作（拔剑 -> 挥剑）才是强继承。

本模块定义三种 Handoff Mode，由镜头元数据（transition / shot_type / scene）决定：
  Mode A  continuous_action  连续动作    use_handoff=True  strength=0.95
  Mode B  same_scene_reangle 同场换角    use_handoff=True  strength=0.70
  Mode C  scene_change       新场景      use_handoff=False（不继承，用独立关键帧）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# 场景切换信号词（命中任一 -> Mode C，禁用 handoff）
_SCENE_CHANGE_KEYWORDS = (
    "new scene", "scene change", "cut to", "meanwhile", "later", "next day",
    "elsewhere", "flashback", "新场景", "转场", "切换", "与此同时", "第二天",
    "另一边", "回忆", "闪回", "时间流逝", "城市", "实验室", "沙漠", "天空",
    "外景", "远景 establishing", "establishing shot",
)

# 连续动作信号词（命中 -> Mode A，强继承）
_CONTINUOUS_ACTION_KEYWORDS = (
    "continue", "continuous", "same action", "follow through", "subsequent",
    "衔接", "连续", "同一动作", "顺势", "紧接着", "继续",
)

# 动作链信号词（拔剑->挥剑->击退 这类，仍属 Mode A）
_ACTION_CHAIN_KEYWORDS = (
    "sword", "punch", "kick", "strike", "attack", "dash", "lunge",
    "挥剑", "出拳", "踢", "冲刺", "蓄力", "击退", "拔剑",
)


@dataclass(frozen=True)
class HandoffDecision:
    mode: str                 # continuous_action / same_scene_reangle / scene_change
    use_handoff: bool
    strength: float           # 0-1：继承强度（Mode C 为 0）
    reason: str

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "use_handoff": self.use_handoff,
            "strength": self.strength,
            "reason": self.reason,
        }


def decide_handoff(
    prev_shot: dict[str, Any] | None,
    next_shot: dict[str, Any],
) -> HandoffDecision:
    """Decide whether/how the next shot should inherit the previous tail frame.

    Args:
        prev_shot: 上一镜元数据（可为 None——首镜无 handoff）。
        next_shot: 下一镜元数据（transition / shot_type / scene / description）。

    Returns:
        HandoffDecision 决定使用哪种衔接模式。
    """
    next_shot = next_shot or {}

    # 显式指定优先
    explicit = next_shot.get("handoff_mode")
    if explicit in ("continuous_action", "same_scene_reangle", "scene_change"):
        return _from_mode(explicit, next_shot)

    if prev_shot is None:
        return HandoffDecision(
            mode="scene_change", use_handoff=False, strength=0.0,
            reason="first shot: no previous frame",
        )

    text = _flatten(next_shot)
    scene = str(next_shot.get("scene", "")).lower()
    shot_type = str(next_shot.get("shot_type", "")).lower()
    description = str(next_shot.get("description", "")).lower()

    # 1. 场景切换 -> Mode C（禁用 handoff）
    if any(kw in text for kw in _SCENE_CHANGE_KEYWORDS) or "establishing" in shot_type:
        return HandoffDecision(
            mode="scene_change", use_handoff=False, strength=0.0,
            reason="scene change detected",
        )

    # 2. 连续动作 / 动作链 -> Mode A（强继承）
    if any(kw in text for kw in _CONTINUOUS_ACTION_KEYWORDS) or \
       any(kw in description for kw in _ACTION_CHAIN_KEYWORDS):
        return HandoffDecision(
            mode="continuous_action", use_handoff=True, strength=0.95,
            reason="continuous action / action chain",
        )

    # 3. 同场景人物动作 -> Mode B（弱继承）
    same_scene = (
        not scene
        or (prev_shot.get("scene", "") or "").lower() == scene
    )
    if same_scene and shot_type in ("medium", "closeup", "medium_shot", "close_up", "中景", "近景"):
        return HandoffDecision(
            mode="same_scene_reangle", use_handoff=True, strength=0.70,
            reason="same scene re-angle",
        )

    # 4. 默认：同场景对话/情绪继承，场景差异不继承
    if same_scene:
        return HandoffDecision(
            mode="same_scene_reangle", use_handoff=True, strength=0.60,
            reason="same scene default",
        )
    return HandoffDecision(
        mode="scene_change", use_handoff=False, strength=0.0,
        reason="different scene, no handoff",
    )


def _from_mode(mode: str, shot: dict[str, Any]) -> HandoffDecision:
    if mode == "continuous_action":
        return HandoffDecision(mode, True, 0.95, "explicit continuous_action")
    if mode == "same_scene_reangle":
        return HandoffDecision(mode, True, 0.70, "explicit same_scene_reangle")
    return HandoffDecision("scene_change", False, 0.0, "explicit scene_change")


def _flatten(shot: dict[str, Any]) -> str:
    parts = [
        str(shot.get(k, "")) for k in (
            "description", "camera", "scene", "shot_type",
            "narration", "dialogue", "transition",
        )
    ]
    return " ".join(parts).lower()
