"""Action Prompt v2 — 镜头动作设计与畸形防护（GPT Round-1 方案）。

核心：
1. 拆分为 image_prompt（动作起始状态）与 motion_prompt（单一主动作），
   不再把所有动作塞进一个 prompt 导致 I2V 信息过载。
2. Anatomy Guard：一组畸形/伪影负向词，防止 手/脸/肢体 抽象变形。
3. ActionBeat：战斗分镜的动作节拍（蓄力→攻击→碰撞→反应→恢复）。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Anatomy Guard（畸形负向限制）
# ---------------------------------------------------------------------------

ANATOMY_GUARD_NEGATIVES = [
    # 手部
    "extra fingers", "missing fingers", "fused fingers", "duplicate hands",
    # 肢体
    "duplicate limbs", "extra arms", "missing arms", "deformed wrist",
    "broken elbows", "twisted torso", "disconnected body parts",
    # 面部
    "asymmetric eyes", "deformed face", "double face", "duplicate person",
    # 武器/道具
    "floating weapon", "weapon fused with hand",
    # 通用
    "bad anatomy", "mutated anatomy", "motion blur", "pixelation",
    "compression artifacts",
]


def build_negative_prompt(base_negative: str = "", *, include_anatomy: bool = True) -> str:
    """Compose the full negative prompt: base + anatomy guard."""
    parts = [p for p in [base_negative] if p]
    if include_anatomy:
        parts.extend(ANATOMY_GUARD_NEGATIVES)
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Action Beat（动作节拍）
# ---------------------------------------------------------------------------

class ActionBeat(str, Enum):
    SETUP = "setup"               # 对峙/起势
    ANTICIPATION = "anticipation" # 蓄力
    ATTACK = "attack"             # 攻击
    IMPACT = "impact"             # 碰撞/命中
    REACTION = "reaction"         # 敌人反应
    RECOVERY = "recovery"         # 收势/恢复


# 战斗分镜建议（GPT Round-1 动作链）
ACTION_BEAT_RHYTHM: list[tuple[ActionBeat, int]] = [
    # (beat, 建议 motion_bucket_id)
    (ActionBeat.SETUP, 95),        # 敌人逼近
    (ActionBeat.ATTACK, 175),      # 冲刺/出招
    (ActionBeat.IMPACT, 185),      # 单次挥击/碰撞
    (ActionBeat.IMPACT, 205),      # 武器碰撞/火花
    (ActionBeat.REACTION, 160),    # 敌人被击退
    (ActionBeat.RECOVERY, 65),     # 主角恢复呼吸
]


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def split_shot_prompt(shot: dict[str, Any]) -> dict[str, str]:
    """Split a shot's raw description into image_prompt + motion_prompt.

    If the shot already carries explicit ``image_prompt`` / ``motion_prompt``,
    they win. Otherwise a simple heuristic splits by action keywords.

    Returns a dict with keys ``image_prompt``, ``motion_prompt``,
    ``negative_prompt`` and ``motion_bucket_id``.
    """
    image_prompt = str(shot.get("image_prompt") or shot.get("positive_prompt") or "").strip()
    motion_prompt = str(shot.get("motion_prompt") or "").strip()
    raw = str(shot.get("description") or shot.get("prompt") or "").strip()

    if not image_prompt:
        # 描述中动作句之前的镜头信息作为 image_prompt
        parts = raw.split("。") if "。" in raw else raw.split(", ")
        image_prompt = parts[0] if parts else raw

    if not motion_prompt and raw and raw != image_prompt:
        rest = raw[len(image_prompt):].lstrip("。，, ")
        if rest:
            motion_prompt = rest

    # 动作句末提示单一主动作（减少模型自由发挥）
    if motion_prompt and "ONE" not in motion_prompt.upper():
        motion_prompt = f"{motion_prompt} No additional actions."

    return {
        "image_prompt": image_prompt,
        "motion_prompt": motion_prompt,
        "negative_prompt": build_negative_prompt(str(shot.get("negative_prompt", ""))),
    }


def motion_prompt_tail(shot: dict[str, Any]) -> str:
    """Return the shot-type motion tail (re-export from motion_profile)."""
    try:
        from backend.video.motion_profile import profile_for
        shot_type = str(shot.get("shot_type") or shot.get("scene_type") or "dialogue")
        return profile_for(shot_type).motion_tail
    except Exception:
        return ""
