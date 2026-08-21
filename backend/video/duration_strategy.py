"""Shot Duration Strategy module for intelligent video length planning.

Instead of using a fixed 6-second duration for every shot, this module
classifies shots by scene type and narrative importance, then dynamically
allocates duration to achieve target episode lengths (~10 minutes per
episode) without requiring an excessive number of shots.

Scene type classification rules:
  - establishing: Wide/aerial shots that set the scene (8-12s)
  - dialogue: Conversational scenes with minimal motion (6-10s)
  - action: Fast-paced action/chase scenes (4-6s, shorter but more shots)
  - emotional: Close-ups with emotional weight (8-15s, slow motion)
  - transition: Scene transitions, montages (3-5s)
  - narration: Voiceover-driven scenes (10-20s, longest)

Duration is also influenced by:
  - Has dialogue: +2s (need time for speech)
  - Has narration: +3s (need time for voiceover)
  - Multiple characters: +1s
  - Night/dark scene: +1s (more atmospheric)
  - First/last shot of episode: +2s (establishing/closing)

The strategy ensures that:
  - A 10-minute episode needs ~15-25 shots (not 100)
  - Total novel duration can reach hours with multiple episodes
  - Each shot gets enough time for meaningful content
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Motion profiles (GPT P0: real motion over anti-mosaic clamping)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MotionProfile:
    """Sampling profile that produces real motion instead of a static frame.

    ``reference_strength``（原 denoise，GPT Round-4 改名）：参考图保持程度 vs
    动作自由度。越高 = 动作越自由但身份越不稳定；越低 = 越贴近首帧（易定帧）。
    这是 Wan2.2 native 链路的甜点区间（实测 0.85 = motion 7.45 / quality 0.884）。
    """
    level: int
    name: str
    reference_strength: float
    frames: int
    steps: int
    cfg: float
    description: str

    @property
    def denoise(self) -> float:
        """Backward-compat alias (旧字段 denoise == reference_strength)."""
        return self.reference_strength


# level semantics: 0 静态 / 1 微表情 / 2 人物动作 / 3 镜头运动 / 4 复杂动作 / 5 极限动作
# reference_strength 档位（GPT Round-4 冻结版）：
#   static 0.65 / dialogue 0.78 / character_motion 0.82 / camera_move 0.85 /
#   action 0.86 / extreme_action 0.88
# 实测曲线：1.0→motion12.5 漂移；0.85→motion7.45 quality0.884 最佳；0.52→定帧。
MOTION_PROFILES: dict[int, MotionProfile] = {
    0: MotionProfile(
        level=0, name="static", reference_strength=0.65, frames=33, steps=25, cfg=3.0,
        description="静态/标题卡（尽量少用）",
    ),
    1: MotionProfile(
        level=1, name="dialogue", reference_strength=0.78, frames=49, steps=30, cfg=4.0,
        description="对白/微表情：嘴唇、眼神、呼吸级运动",
    ),
    2: MotionProfile(
        level=2, name="character_motion", reference_strength=0.82, frames=81, steps=35, cfg=4.5,
        description="人物动作：转身、起立、手势等",
    ),
    3: MotionProfile(
        level=3, name="camera_move", reference_strength=0.85, frames=81, steps=40, cfg=5.0,
        description="镜头运动：推拉摇移、跟拍、环绕",
    ),
    4: MotionProfile(
        level=4, name="action", reference_strength=0.86, frames=97, steps=40, cfg=5.5,
        description="复杂动作：奔跑、追逐、战斗",
    ),
    5: MotionProfile(
        level=5, name="extreme_action", reference_strength=0.88, frames=97, steps=40, cfg=5.5,
        description="极限动作：爆炸、变身、法术、高速追车",
    ),
}

# 老 name -> level 兼容映射（GPT Round-4：micro/character/camera/action 改名）
_NAME_TO_LEVEL: dict[str, int] = {
    "static": 0, "micro": 1, "dialogue": 1,
    "character": 2, "character_motion": 2,
    "camera": 3, "camera_move": 3,
    "action": 4, "extreme_action": 5,
}

_SCENE_TYPE_MOTION_LEVEL: dict[str, int] = {
    "dialogue": 1,
    "emotional": 2,
    "narration": 2,
    "establishing": 3,
    "transition": 3,
    "action": 4,
}

_CAMERA_MOTION_KEYWORDS = (
    "handheld", "tracking", "orbit", "crane", "dolly",
    "push", "pull", "pan", "tilt", "follow", "sweep", "move",
)


def get_shot_motion_level(shot_data: dict[str, Any] | None = None) -> int:
    """Resolve the motion level (0-5) for a shot.

    Priority: explicit ``motion_level`` on the shot > ``motion_profile`` name
    > scene-type classification > camera-motion keywords > default.
    """
    shot_data = shot_data or {}
    explicit = shot_data.get("motion_level")
    if isinstance(explicit, int) and 0 <= explicit <= 5:
        return explicit
    if isinstance(explicit, str) and explicit.strip().isdigit():
        return max(0, min(5, int(explicit.strip())))

    # GPT Round-4: 支持按 profile 名指定（dialogue/action/extreme_action 等）
    prof_name = str(shot_data.get("motion_profile", "")).strip().lower()
    if prof_name in _NAME_TO_LEVEL:
        return _NAME_TO_LEVEL[prof_name]

    scene_type = classify_scene_type(shot_data)
    level = _SCENE_TYPE_MOTION_LEVEL.get(scene_type, 2)

    # 动作强度关键词 -> 极限动作（爆炸/变身/法术/高速追车）
    desc = str(shot_data.get("description", "")).lower() + str(shot_data.get("narration", "")).lower()
    if level >= 4 and any(kw in desc for kw in ("explos", "transform", "变身", "法术", "爆炸", "高速")):
        return 5

    camera = str(shot_data.get("camera", "")).lower()
    if level < 3 and any(kw in camera for kw in _CAMERA_MOTION_KEYWORDS):
        level = 3
    return level


def get_motion_profile(shot_data: dict[str, Any] | None = None) -> MotionProfile:
    """Return the MotionProfile that produces real motion for a shot."""
    level = get_shot_motion_level(shot_data)
    return MOTION_PROFILES[level]


# ---------------------------------------------------------------------------
# Motion bucket mapping (GPT Round-1: Wan2.2 motion_bucket_id 0-255 档位表)
# ---------------------------------------------------------------------------

# 镜头类型 -> motion_bucket_id 建议区间（GPT 表）的中点
MOTION_BUCKET_BY_SHOT_TYPE: dict[str, int] = {
    "static_emotional": 40,      # 30-55 静态情绪近景
    "dialogue": 60,              # 45-75 说话/微表情
    "turn_stand": 85,            # 70-105 转身/起身
    "walking": 105,              # 85-125 正常行走
    "run_chase": 140,            # 120-155 跑步/追逐
    "sword_punch": 160,          # 140-180 挥剑/拳击
    "dash": 180,                 # 165-200 高速冲刺
    "explosion": 195,            # 180-215 强烈爆炸/被击飞
    "vfx_cut": 220,              # 210-235 极端特效插镜
}

# 现有 motion level(0-5) -> bucket（用于向后兼容）
_MOTION_LEVEL_TO_BUCKET: dict[int, int] = {
    0: 40,    # static
    1: 60,    # dialogue / micro
    2: 105,   # character_motion / walking
    3: 140,   # camera_move / run
    4: 175,   # action / fight (160-190 区间)
    5: 195,   # extreme_action / explosion
}


def resolve_motion_bucket(shot_data: dict[str, Any] | None = None) -> int:
    """Resolve Wan2.2 motion_bucket_id for a shot.

    Priority:
      1. explicit ``motion_bucket_id`` on the shot
      2. ``shot_type`` match on the GPT bucket table
      3. existing motion level (0-4) mapping
      4. default 127 (balanced)
    """
    shot_data = shot_data or {}
    explicit = shot_data.get("motion_bucket_id")
    if explicit is not None:
        try:
            return max(0, min(255, int(explicit)))
        except (TypeError, ValueError):
            pass

    shot_type = str(shot_data.get("shot_type", "")).lower()
    if shot_type in MOTION_BUCKET_BY_SHOT_TYPE:
        return MOTION_BUCKET_BY_SHOT_TYPE[shot_type]

    level = get_shot_motion_level(shot_data)
    return _MOTION_LEVEL_TO_BUCKET.get(level, 127)


# ---------------------------------------------------------------------------
# Scene type definitions with duration ranges
# ---------------------------------------------------------------------------

@dataclass
class SceneTypeSpec:
    """Specification for a scene type."""
    name: str
    min_duration: float
    max_duration: float
    default_duration: float
    description: str


SCENE_TYPES: dict[str, SceneTypeSpec] = {
    "establishing": SceneTypeSpec(
        name="establishing",
        min_duration=8.0,
        max_duration=12.0,
        default_duration=10.0,
        description="Wide/aerial shots establishing location and mood",
    ),
    "dialogue": SceneTypeSpec(
        name="dialogue",
        min_duration=10.0,
        max_duration=15.0,
        default_duration=12.0,
        description="Conversational scenes with character interaction",
    ),
    "action": SceneTypeSpec(
        name="action",
        min_duration=5.0,
        max_duration=8.0,
        default_duration=6.0,
        description="Fast-paced action, chase, or combat scenes",
    ),
    "emotional": SceneTypeSpec(
        name="emotional",
        min_duration=15.0,
        max_duration=20.0,
        default_duration=17.0,
        description="Emotional close-ups, dramatic moments with slow motion",
    ),
    "transition": SceneTypeSpec(
        name="transition",
        min_duration=3.0,
        max_duration=5.0,
        default_duration=4.0,
        description="Scene transitions, montages, time passes",
    ),
    "narration": SceneTypeSpec(
        name="narration",
        min_duration=10.0,
        max_duration=20.0,
        default_duration=15.0,
        description="Voiceover-driven scenes with extensive narration",
    ),
}


# Keywords for scene type classification
SCENE_KEYWORDS: dict[str, list[str]] = {
    "establishing": [
        "aerial", "establishing", "wide shot", "long shot", "exterior",
        "landscape", "city", "building", "panorama", "overview",
        "鸟瞰", "全景", "远景", "外景", "城市", "建筑",
    ],
    "dialogue": [
        "dialogue", "conversation", "talking", "speaking", "discussion",
        "interview", "meeting", "phone", "chat",
        "对话", "交谈", "说话", "讨论", "会议", "电话",
    ],
    "action": [
        "action", "fight", "chase", "run", "escape", "combat",
        "explosion", "crash", "speed", "race", "battle",
        "动作", "打斗", "追逐", "逃跑", "战斗", "爆炸",
    ],
    "emotional": [
        "emotional", "cry", "tears", "sad", "happy", "love",
        "close-up", "dramatic", "intense", "shock", "fear",
        "情感", "哭泣", "悲伤", "幸福", "爱情", "特写",
    ],
    "transition": [
        "transition", "montage", "time lapse", "fade", "dissolve",
        "meanwhile", "later", "next day", "time pass",
        "转场", "蒙太奇", "时间流逝", "淡入", "淡出",
    ],
    "narration": [
        "narration", "voiceover", "narrator", "story", "tale",
        "memory", "flashback", "recall", "reflect",
        "旁白", "独白", "回忆", "闪回", "叙述",
    ],
}


@dataclass
class ShotDurationPlan:
    """Result of duration planning for a single shot."""
    shot_id: str
    scene_type: str
    base_duration: float
    adjustments: list[str] = field(default_factory=list)
    final_duration: float = 0.0
    target_frames: int = 0
    interpolation_multiplier: int = 1
    reasoning: str = ""


@dataclass
class EpisodeDurationPlan:
    """Result of duration planning for an entire episode."""
    episode_id: str
    shots: list[ShotDurationPlan] = field(default_factory=list)
    total_duration: float = 0.0
    target_duration: float = 600.0  # 10 minutes default
    shot_count: int = 0
    meets_target: bool = False

    @property
    def total_duration_str(self) -> str:
        """Human-readable duration string."""
        m = int(self.total_duration // 60)
        s = int(self.total_duration % 60)
        if m >= 60:
            h = m // 60
            m = m % 60
            return f"{h}小时{m}分{s}秒"
        return f"{m}分{s}秒"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_scene_type(shot_data: dict[str, Any]) -> str:
    """Classify a shot's scene type based on its description, camera, and narration.

    Args:
        shot_data: Shot dictionary from production_plan.json.

    Returns:
        Scene type string (key in SCENE_TYPES).
    """
    description = str(shot_data.get("description", "")).lower()
    camera = str(shot_data.get("camera", "")).lower()
    narration = str(shot_data.get("narration", "")).lower()
    dialogue = str(shot_data.get("dialogue", "")).lower()

    combined = f"{description} {camera} {narration} {dialogue}"

    # Score each scene type by keyword matches
    scores: dict[str, int] = {}
    for scene_type, keywords in SCENE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[scene_type] = score

    if scores:
        best_type = max(scores, key=scores.get)
        logger.debug("Shot %s classified as '%s' (score=%d)",
                     shot_data.get("id", "?"), best_type, scores[best_type])
        return best_type

    # Default: if has narration, treat as narration type
    if narration and len(narration) > 50:
        return "narration"

    # Default: if has dialogue, treat as dialogue
    if dialogue:
        return "dialogue"

    return "dialogue"  # Safe default


# ---------------------------------------------------------------------------
# Duration calculation
# ---------------------------------------------------------------------------

def calculate_shot_duration(
    shot_data: dict[str, Any],
    scene_type: str,
    shot_index: int = 0,
    total_shots: int = 0,
    source_frames: int = 49,
    fps: int = 24,
) -> ShotDurationPlan:
    """Calculate the optimal duration for a single shot.

    Applies scene-type base duration plus contextual adjustments.

    Args:
        shot_data: Shot dictionary from production_plan.json.
        scene_type: Scene type from classify_scene_type().
        shot_index: Zero-based index of this shot in the episode.
        total_shots: Total number of shots in the episode.
        source_frames: Frames of the raw AI-generated clip (motion profile).
        fps: Frames per second of the raw clip.

    Returns:
        ShotDurationPlan with calculated duration and reasoning.
    """
    spec = SCENE_TYPES.get(scene_type, SCENE_TYPES["dialogue"])
    base_duration = spec.default_duration
    adjustments: list[str] = []

    description = str(shot_data.get("description", ""))
    narration = str(shot_data.get("narration", ""))
    dialogue = str(shot_data.get("dialogue", ""))
    characters = shot_data.get("characters", [])
    camera = str(shot_data.get("camera", "")).lower()

    # Adjustment: has dialogue (+2s)
    if dialogue and len(dialogue) > 10:
        base_duration += 2.0
        adjustments.append("+2s (有对话)")

    # Adjustment: has narration (+3s)
    if narration and len(narration) > 20:
        base_duration += 3.0
        adjustments.append("+3s (有旁白)")

    # Adjustment: multiple characters (+1s)
    if isinstance(characters, list) and len(characters) > 1:
        base_duration += 1.0
        adjustments.append("+1s (多角色)")

    # Adjustment: first shot of episode (+2s, establishing)
    if shot_index == 0:
        base_duration += 2.0
        adjustments.append("+2s (首镜建立)")

    # Adjustment: last shot of episode (+2s, closing)
    if total_shots > 0 and shot_index == total_shots - 1:
        base_duration += 2.0
        adjustments.append("+2s (末镜收尾)")

    # Clamp to scene type range
    final_duration = max(spec.min_duration, min(spec.max_duration + 5.0, base_duration))

    # Calculate target frames and interpolation multiplier.
    # The raw clip length comes from the shot's motion profile
    # (e.g. 81 frames @24fps = 3.4s), then minterpolate extends it to the
    # target duration. multiplier 1 means the raw clip already fits.
    source_seconds = max(0.5, source_frames / fps)
    needed_multiplier = final_duration / source_seconds
    interpolation_multiplier = max(1, min(15, round(needed_multiplier)))

    # Recalculate actual achievable duration
    actual_duration = source_seconds * interpolation_multiplier

    reasoning = (
        f"Scene type: {scene_type} (base {spec.default_duration}s), "
        f"adjustments: {', '.join(adjustments) if adjustments else 'none'}, "
        f"target: {final_duration:.1f}s, "
        f"interpolation: {interpolation_multiplier}x ({actual_duration:.1f}s achievable)"
    )

    return ShotDurationPlan(
        shot_id=shot_data.get("id", f"shot_{shot_index+1}"),
        scene_type=scene_type,
        base_duration=spec.default_duration,
        adjustments=adjustments,
        final_duration=actual_duration,
        target_frames=source_frames,
        interpolation_multiplier=interpolation_multiplier,
        reasoning=reasoning,
    )


def plan_episode_duration(
    shots: list[dict[str, Any]],
    target_duration_s: float = 600.0,
    episode_id: str = "ep_01",
) -> EpisodeDurationPlan:
    """Plan durations for all shots in an episode to hit the target duration.

    Args:
        shots: List of shot dictionaries from production_plan.json.
        target_duration_s: Target episode duration in seconds (default 600 = 10 min).
        episode_id: Episode identifier.

    Returns:
        EpisodeDurationPlan with per-shot duration allocations.
    """
    total_shots = len(shots)
    plan = EpisodeDurationPlan(
        episode_id=episode_id,
        target_duration=target_duration_s,
        shot_count=total_shots,
    )

    for i, shot in enumerate(shots):
        scene_type = classify_scene_type(shot)
        shot_plan = calculate_shot_duration(
            shot_data=shot,
            scene_type=scene_type,
            shot_index=i,
            total_shots=total_shots,
        )
        plan.shots.append(shot_plan)
        plan.total_duration += shot_plan.final_duration

    # Check if we meet the target
    plan.meets_target = plan.total_duration >= target_duration_s * 0.8  # 80% threshold

    if not plan.meets_target:
        logger.warning(
            "Episode %s duration %.1fs < target %.1fs (%.0f%% of target). "
            "Consider adding more shots or increasing durations.",
            episode_id,
            plan.total_duration,
            target_duration_s,
            (plan.total_duration / target_duration_s * 100) if target_duration_s > 0 else 0,
        )

    logger.info(
        "Episode %s plan: %d shots, %.1fs total (target %.1fs, %s)",
        episode_id,
        total_shots,
        plan.total_duration,
        target_duration_s,
        "OK" if plan.meets_target else "BELOW TARGET",
    )

    return plan


def estimate_novel_duration(
    episodes: list[EpisodeDurationPlan],
) -> dict[str, Any]:
    """Estimate total novel video duration from all episodes.

    Args:
        episodes: List of EpisodeDurationPlan objects.

    Returns:
        Dictionary with duration estimates and recommendations.
    """
    total_duration = sum(e.total_duration for e in episodes)
    total_shots = sum(e.shot_count for e in episodes)
    total_hours = total_duration / 3600

    # Calculate how many episodes needed for target hours
    avg_episode_duration = total_duration / len(episodes) if episodes else 0
    target_hours = 1.0  # Minimum 1 hour

    if avg_episode_duration > 0:
        episodes_needed = max(len(episodes), int((target_hours * 3600) / avg_episode_duration))
    else:
        episodes_needed = 0

    return {
        "total_episodes": len(episodes),
        "total_shots": total_shots,
        "total_duration_s": total_duration,
        "total_duration_str": EpisodeDurationPlan(
            episode_id="total", target_duration=total_duration
        ).total_duration_str,
        "total_hours": round(total_hours, 2),
        "avg_episode_duration_s": avg_episode_duration,
        "target_min_hours": target_hours,
        "episodes_needed_for_target": episodes_needed,
        "meets_minimum_duration": total_hours >= target_hours,
    }
