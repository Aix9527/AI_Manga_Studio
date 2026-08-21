"""Shot-type motion profiles for Wan2.2 native video prompts.

GPT Phase-2 建议: 镜头级 Motion Profile（low/medium/high），避免所有镜头
统一使用 handheld + urgent motion 导致"动作过激/AI摄影感"。

profile -> (motion_level, motion_tail)，motion_tail 会被拼接到 positive
prompt 的 style 前缀之后（masterpiece 之前）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionProfile:
    level: str  # low | medium | high
    motion_tail: str


PROFILES: dict[str, MotionProfile] = {
    "close_up": MotionProfile(
        "low",
        "subtle breathing, micro facial movement, eyes moving, slight head movement, "
        "slow cinematic push-in, shallow depth of field",
    ),
    "dialogue": MotionProfile(
        "low",
        "subtle facial expression change, breathing, slight head movement, "
        "natural body language, slow cinematic push-in",
    ),
    "detail": MotionProfile(
        "low",
        "screen glow flickering slightly, subtle parallax, faint reflections moving, "
        "static camera, controlled depth of field",
    ),
    "drama_action": MotionProfile(
        "medium",
        "natural body motion, controlled action, smooth tracking shot, "
        "slow handheld, camera following movement",
    ),
    "transition": MotionProfile(
        "medium",
        "camera following movement, dynamic tracking shot, lights streaking, "
        "mist and dust swirling",
    ),
    "cinematic_action": MotionProfile(
        "high",
        "character moving fast, dynamic tracking shot, handheld camera shake, "
        "urgent motion, coat and cloth movement",
    ),
    "environment": MotionProfile(
        "high",
        "aerial drone establishing shot, slow push-in, clouds drifting, "
        "mist flowing, wind-blown atmosphere, volumetric fog",
    ),
}


def profile_for(shot_type: str) -> MotionProfile:
    """Return the motion profile for a shot type (unknown types default to dialogue)."""
    return PROFILES.get(shot_type, PROFILES["dialogue"])
