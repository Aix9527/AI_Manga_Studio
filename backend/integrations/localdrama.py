"""LocalDrama integration — storyboard enhancement, character consistency, and video merge.

This module ports the core patterns from LocalMiniDrama (Node.js/Express) into the
AI Manga Studio Python backend, making them available as self-contained classes:

- :class:`StoryboardEnhancer` — professional shot-type / camera-angle / movement
  enhancement and prompt generation, supporting both ``classic`` and ``universal``
  (multi-reference) creation modes.

- :class:`CharacterConsistency` — 6-layer visual identity anchors, color palette
  extraction, polished cross-shot prompt generation, and tail-frame linking
  (尾帧衔接) between consecutive shots.

- :class:`VideoMergeService` — FFmpeg concat merging, resolution normalization,
  subtitle burning, audio overlay, and watermark support across aspect ratios.

The angle / movement / shot-type enumerations and their bilingual (中文/English)
prompt fragments are encoded as module-level data structures so they can be
imported and reused independently.

References (LocalMiniDrama source):
- ``backend-node/src/services/angleService.js`` — 96 angle combinations
- ``backend-node/src/services/episodeStoryboardService.js`` — storyboard prompts
- ``backend-node/src/services/characterGenerationService.js`` — identity anchors
- ``backend-node/src/services/videoMergeService.js`` — FFmpeg concat merge
- ``backend-node/src/services/videoService.js`` — normalizeVideoFileToTargetPixels
- ``backend-node/src/services/tailFrameLinkService.js`` — tail-frame linking
- ``backend-node/src/services/mergedEpisodePostProcess.js`` — subtitle/audio/watermark
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Shot Types (景别)
# ═══════════════════════════════════════════════════════════════════════════════

#: Professional shot sizes mapped to bilingual labels and English prompt fragments.
#:
#: Each entry: ``enum_key -> (中文, english_prompt_fragment)``
SHOT_TYPES: dict[str, tuple[str, str]] = {
    "extreme_wide": (
        "大远景",
        "extreme wide shot, subject very small in vast landscape, "
        "establishing environment, deep depth of field",
    ),
    "wide": (
        "远景",
        "wide shot, full body with environment visible, subject small relative "
        "to scene, deep depth of field",
    ),
    "full": (
        "全景",
        "full shot, entire subject visible head-to-toe, moderate environmental context",
    ),
    "medium": (
        "中景",
        "medium shot, waist-up framing, character and immediate surroundings visible, "
        "moderate depth of field",
    ),
    "medium_close": (
        "中近景",
        "medium close-up shot, chest-up framing, facial expression prominent, "
        "shallow depth of field",
    ),
    "close_up": (
        "近景",
        "close-up shot, face/bust framing, subject fills most of frame, "
        "shallow depth of field, background softly blurred",
    ),
    "extreme_close": (
        "大特写",
        "extreme close-up shot, tight framing on eyes/mouth/detail, "
        "very shallow depth of field, intense intimacy",
    ),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Camera Angles — Horizontal (水平方向)
# ═══════════════════════════════════════════════════════════════════════════════

#: 8-direction horizontal angles (水平方向).
HORIZONTAL_ANGLES: dict[str, tuple[str, str]] = {
    "front": ("正面", "shooting from the front"),
    "front_left": ("前左", "shooting from front-left at 45-degree angle"),
    "left": ("左侧", "shooting from the left side, profile view"),
    "back_left": ("后左", "shooting from back-left at 135-degree angle"),
    "back": ("背面", "shooting from behind, character's back to camera"),
    "back_right": ("后右", "shooting from back-right at 135-degree angle"),
    "right": ("右侧", "shooting from the right side, profile view"),
    "front_right": ("前右", "shooting from front-right at 45-degree angle"),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Camera Angles — Vertical (垂直角度)
# ═══════════════════════════════════════════════════════════════════════════════

#: Vertical elevation angles (垂直角度).
VERTICAL_ANGLES: dict[str, tuple[str, str]] = {
    "worm": (
        "虫眼仰",
        "extreme low-angle worm's eye view, camera near ground pointing sharply "
        "upward, strong upward perspective distortion",
    ),
    "low": (
        "仰拍",
        "low-angle upward shot, camera below eye-line, slight upward tilt, "
        "empowering perspective",
    ),
    "eye_level": (
        "平视",
        "eye-level shot, neutral perspective, natural horizontal framing",
    ),
    "high": (
        "俯拍",
        "high-angle bird's eye view, camera above looking down, "
        "downward perspective distortion",
    ),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Camera Angles — Special (特殊角度)
# ═══════════════════════════════════════════════════════════════════════════════

#: Special angles beyond the standard 8x4 grid (特殊角度).
SPECIAL_ANGLES: dict[str, tuple[str, str]] = {
    "dutch": (
        "荷兰角",
        "Dutch angle, canted framing with tilted horizon line, "
        "creating tension and disorientation",
    ),
    "over_shoulder": (
        "过肩",
        "over-the-shoulder shot, camera positioned behind one character "
        "looking toward another, partial back of foreground character visible",
    ),
    "pov": (
        "主观视角",
        "point-of-view shot, camera represents character's perspective, "
        "immersive first-person framing",
    ),
    "top_down": (
        "俯瞰",
        "top-down flat lay shot, camera directly overhead pointing straight down, "
        "graphic composition",
    ),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Camera Movements (运镜)
# ═══════════════════════════════════════════════════════════════════════════════

#: Camera movement types (运镜) mapped to bilingual labels and English fragments.
CAMERA_MOVEMENTS: dict[str, tuple[str, str]] = {
    "static": ("固定", "static locked shot, no camera movement, tripod-mounted"),
    "push": ("推", "slow push-in dolly shot, camera gradually moves closer to subject"),
    "pull": ("拉", "pull-back dolly shot, camera gradually moves away from subject"),
    "pan": ("摇", "horizontal pan shot, camera sweeps laterally from side to side"),
    "tilt": ("纵摇", "vertical tilt shot, camera pivots up or down"),
    "tracking": ("跟", "tracking shot, camera follows subject movement, smooth motion"),
    "crane_up": ("升", "crane up shot, camera rises vertically, revealing wider scene"),
    "crane_down": ("降", "crane down shot, camera descends vertically"),
    "handheld": ("手持", "handheld shot, subtle natural camera shake, documentary feel"),
    "orbit": ("环绕", "orbiting arc shot, camera circles around subject"),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Lighting Styles (灯光)
# ═══════════════════════════════════════════════════════════════════════════════

#: Lighting style enums (灯光风格) mapped to bilingual labels and English fragments.
LIGHTING_STYLES: dict[str, tuple[str, str]] = {
    "natural": ("自然光", "natural ambient lighting, soft and even illumination"),
    "front": ("顺光", "flat front lighting, even illumination, minimal shadows"),
    "side": ("侧光", "dramatic side lighting, strong contrast between light and shadow"),
    "backlit": ("逆光", "backlit, rim lighting, subject silhouetted with halo edge light"),
    "top": ("顶光", "harsh overhead top lighting, strong downward shadows"),
    "under": ("底光", "unsettling underlighting, upward low-key light source"),
    "soft": ("柔光", "soft diffused lighting, gentle shadows, flattering luminosity"),
    "dramatic": ("戏剧光", "high contrast chiaroscuro lighting, deep shadows, cinematic noir"),
    "golden_hour": ("黄金时段", "warm golden hour sunlight, long low shadows, amber glow"),
    "blue_hour": ("蓝调时刻", "cool blue hour twilight, moody atmospheric dusk light"),
    "night": ("夜景", "low key night lighting, isolated artificial light sources, deep shadows"),
    "neon": ("霓虹", "vivid neon lighting, colored artificial lights, cyberpunk atmosphere"),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Depth of Field (景深)
# ═══════════════════════════════════════════════════════════════════════════════

#: Depth of field enums (景深).
DEPTH_OF_FIELD: dict[str, tuple[str, str]] = {
    "extreme_shallow": (
        "极浅景深",
        "extreme shallow depth of field, razor-thin focus plane, heavy creamy bokeh",
    ),
    "shallow": ("浅景深", "shallow depth of field, subject in sharp focus, background blurred"),
    "medium": ("中景深", "moderate depth of field, subject and near surroundings in focus"),
    "deep": ("深景深", "deep focus, everything sharp from foreground to background"),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Aspect Ratio to Target Pixels (画面比例像素映射)
# ═══════════════════════════════════════════════════════════════════════════════

#: Maps aspect ratio strings to ``(width, height)`` target pixel dimensions.
#: Used by :meth:`VideoMergeService.normalize_video_file_to_target_pixels`.
ASPECT_RATIO_PIXELS: dict[str, tuple[int, int]] = {
    "16:9": (2560, 1440),
    "9:16": (1440, 2560),
    "1:1": (1920, 1920),
    "4:3": (1920, 1440),
    "3:4": (1440, 1920),
    "3:2": (2560, 1708),
    "2:3": (1708, 2560),
    "21:9": (2560, 1080),
}

#: Default aspect ratio when none is specified.
DEFAULT_ASPECT_RATIO = "16:9"

#: Common color names (Chinese + English) mapped to Hex codes,
#: used by :meth:`CharacterConsistency._extract_color_anchors` and
#: :meth:`CharacterConsistency._build_color_palette` when no explicit Hex
#: code is present in the description.
COLOR_NAME_TO_HEX: dict[str, str] = {
    "黑色": "#1A1A1A", "黑": "#1A1A1A", "black": "#1A1A1A",
    "白色": "#FFFFFF", "白": "#FFFFFF", "white": "#FFFFFF",
    "红色": "#CC0000", "红": "#CC0000", "red": "#CC0000",
    "蓝色": "#1E50A2", "蓝": "#1E50A2", "blue": "#1E50A2",
    "绿色": "#008000", "绿": "#008000", "green": "#008000",
    "黄色": "#FFD700", "黄": "#FFD700", "yellow": "#FFD700",
    "金色": "#C8A96E", "金": "#C8A96E", "golden": "#C8A96E", "blonde": "#C8A96E",
    "棕色": "#8B4513", "棕": "#8B4513", "褐色": "#8B4513", "brown": "#8B4513",
    "灰色": "#808080", "灰": "#808080", "gray": "#808080", "grey": "#808080",
    "紫色": "#800080", "紫": "#800080", "purple": "#800080",
    "粉色": "#FFC0CB", "粉": "#FFC0CB", "pink": "#FFC0CB",
    "银色": "#C0C0C0", "银": "#C0C0C0", "silver": "#C0C0C0",
    "白皙": "#F5DEB3", "白皙皮肤": "#F5DEB3", "fair": "#F5DEB3", "pale": "#F5DEB3",
    "小麦色": "#D2B48C", "小麦": "#D2B48C", "tanned": "#D2B48C", "wheat": "#D2B48C",
    "古铜色": "#8D6E63", "bronze": "#8D6E63",
    "深色皮肤": "#6D4C41", "dark skin": "#6D4C41",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Chinese keyword → enum mappings (for backward-compatible parsing)
# ═══════════════════════════════════════════════════════════════════════════════

#: Chinese keyword groups for horizontal angle inference.
_ZH_HORIZONTAL_MAP: list[tuple[list[str], str]] = [
    (["背后", "背面", "从背", "back"], "back"),
    (["前左", "左前", "front-left", "front_left"], "front_left"),
    (["前右", "右前", "front-right", "front_right"], "front_right"),
    (["左侧", "正侧", "侧面", "side", "left"], "left"),
    (["右侧", "right"], "right"),
    (["后左", "左后", "back-left", "back_left"], "back_left"),
    (["后右", "右后", "back-right", "back_right"], "back_right"),
    (["正面", "前方", "面向", "front"], "front"),
]

#: Chinese keyword groups for vertical angle inference.
_ZH_VERTICAL_MAP: list[tuple[list[str], str]] = [
    (["虫眼", "极低", "worm"], "worm"),
    (["仰", "low angle", "low-angle"], "low"),
    (["俯", "high angle", "bird"], "high"),
    (["平视", "eye-level", "eye level"], "eye_level"),
]

#: Chinese keyword groups for shot size inference.
_ZH_SHOT_SIZE_MAP: list[tuple[list[str], str]] = [
    (["大特写", "extreme close", "macro"], "extreme_close"),
    (["特写", "近景", "close"], "close_up"),
    (["中近景", "medium close"], "medium_close"),
    (["中景", "半身", "medium"], "medium"),
    (["全景", "full shot", "full"], "full"),
    (["远景", "大全", "wide", "long shot", "establishing"], "wide"),
    (["大远景", "extreme wide", "extreme long"], "extreme_wide"),
]

#: Chinese keyword groups for camera movement inference.
_ZH_MOVEMENT_MAP: list[tuple[list[str], str]] = [
    (["固定", "不动", "static", "locked"], "static"),
    (["推镜", "推进", "推", "push in", "dolly in", "push"], "push"),
    (["拉镜", "拉出", "拉", "pull back", "dolly out", "pull"], "pull"),
    (["横移", "横摇", "摇镜", "摇", "pan"], "pan"),
    (["纵摇", "上摇", "下摇", "tilt"], "tilt"),
    (["跟镜", "跟拍", "跟随", "track"], "tracking"),
    (["升镜", "向上", "crane up"], "crane_up"),
    (["降镜", "向下", "crane down"], "crane_down"),
    (["手持", "handheld"], "handheld"),
    (["环绕", "绕", "orbit", "arc"], "orbit"),
]

#: Chinese keyword groups for lighting inference, ordered by priority
#: (mirrors the if/else-if chain in ``angleService.inferPhotographyParams``).
_ZH_LIGHTING_MAP: list[tuple[list[str], str]] = [
    (["霓虹", "赛博", "neon", "cyberpunk"], "neon"),
    (["逆光", "背光", "backlit", "back light", "轮廓光", "rim light"], "backlit"),
    (["戏剧", "明暗", "强对比", "dramatic", "chiaroscuro", "noir"], "dramatic"),
    (["黄金时段", "黄昏", "金色光", "夕阳", "落日", "golden hour"], "golden_hour"),
    (["蓝调", "蓝光", "暮色", "blue hour", "twilight"], "blue_hour"),
    (["夜景", "夜晚", "深夜", "午夜", "night"], "night"),
    (["顶光", "头顶", "top light"], "top"),
    (["底光", "脚灯", "underlight"], "under"),
    (["侧光", "side light", "侧面光"], "side"),
    (["柔光", "散射", "soft light", "soft"], "soft"),
    (["顺光", "正面光", "front light"], "front"),
    (["自然光", "日光", "阳光", "natural light", "sunlight"], "natural"),
    (["白天", "清晨", "午后", "daytime", "morning", "afternoon"], "natural"),
]

#: Chinese keyword groups for depth-of-field inference.
_ZH_DOF_MAP: list[tuple[list[str], str]] = [
    (["极浅", "大光圈", "extreme shallow", "razor thin"], "extreme_shallow"),
    (["浅景深", "浅", "shallow", "bokeh"], "shallow"),
    (["中景深", "适中", "medium dof"], "medium"),
    (["深景深", "全焦", "超焦", "deep focus", "deep dof"], "deep"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

def _match_zh(text: str, mapping: list[tuple[list[str], str]]) -> str | None:
    """Match a Chinese/English keyword group against *text*, returning the enum value."""
    lower = text.lower()
    for keys, val in mapping:
        for k in keys:
            if k.lower() in lower:
                return val
    return None


def _get_ffmpeg_binary() -> str:
    """Return the FFmpeg binary path, preferring imageio-ffmpeg's bundled binary."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _get_ffprobe_binary() -> str:
    """Return the FFprobe binary path."""
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        # imageio-ffmpeg ships ffmpeg; ffprobe is typically alongside it
        ffprobe = str(Path(ff).parent / "ffprobe")
        if Path(ffprobe).exists():
            return ffprobe
    except Exception:
        pass
    return "ffprobe"


def aspect_ratio_to_pixels(ratio: str) -> tuple[int, int]:
    """Return ``(width, height)`` target pixels for an aspect ratio string.

    Falls back to parsing ``W:H`` and computing proportional dimensions.
    """
    ratio = ratio.strip()
    if ratio in ASPECT_RATIO_PIXELS:
        return ASPECT_RATIO_PIXELS[ratio]
    m = re.match(r"^(\d+)\s*:\s*(\d+)$", ratio)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        # Keep the longer side at 2560 px
        if a >= b:
            w = 2560
            h = round(2560 * b / a)
        else:
            h = 2560
            w = round(2560 * a / b)
        return (w, h)
    return ASPECT_RATIO_PIXELS[DEFAULT_ASPECT_RATIO]


def shot_type_to_chinese(enum_key: str) -> str:
    """Return the Chinese label for a shot type enum."""
    entry = SHOT_TYPES.get(enum_key)
    return entry[0] if entry else enum_key


def shot_type_to_english(enum_key: str) -> str:
    """Return the English prompt fragment for a shot type enum."""
    entry = SHOT_TYPES.get(enum_key)
    return entry[1] if entry else enum_key


def horizontal_to_chinese(enum_key: str) -> str:
    """Return the Chinese label for a horizontal angle enum."""
    entry = HORIZONTAL_ANGLES.get(enum_key)
    return entry[0] if entry else enum_key


def vertical_to_chinese(enum_key: str) -> str:
    """Return the Chinese label for a vertical angle enum."""
    entry = VERTICAL_ANGLES.get(enum_key)
    return entry[0] if entry else enum_key


def movement_to_chinese(enum_key: str) -> str:
    """Return the Chinese label for a camera movement enum."""
    entry = CAMERA_MOVEMENTS.get(enum_key)
    return entry[0] if entry else enum_key


def movement_to_english(enum_key: str) -> str:
    """Return the English prompt fragment for a camera movement enum."""
    entry = CAMERA_MOVEMENTS.get(enum_key)
    return entry[1] if entry else enum_key


def lighting_to_chinese(enum_key: str) -> str:
    """Return the Chinese label for a lighting style enum."""
    entry = LIGHTING_STYLES.get(enum_key)
    return entry[0] if entry else enum_key


def angle_to_chinese_label(h: str | None, v: str | None, s: str | None) -> str:
    """Build a short Chinese label ``景别·俯仰·方向`` from structured angle triple.

    Mirrors ``angleService.toChineseLabel``.
    """
    s_label = shot_type_to_chinese(s) if s else "中景"
    v_label = vertical_to_chinese(v) if v else "平视"
    h_label = horizontal_to_chinese(h) if h else "正面"
    return f"{s_label}·{v_label}·{h_label}"


def angle_to_english_fragment(h: str | None, v: str | None, s: str | None) -> str:
    """Build the full English camera prompt fragment from structured angle triple.

    Mirrors ``angleService.toPromptFragment``.
    """
    s_frag = shot_type_to_english(s) if s else SHOT_TYPES["medium"][1]
    v_frag = VERTICAL_ANGLES.get(v, ("", VERTICAL_ANGLES["eye_level"][1]))[1] if v else VERTICAL_ANGLES["eye_level"][1]
    h_frag = HORIZONTAL_ANGLES.get(h, ("", HORIZONTAL_ANGLES["front"][1]))[1] if h else HORIZONTAL_ANGLES["front"][1]
    return f"{s_frag}, {v_frag}, {h_frag}"


def parse_legacy_angle(angle_text: str, shot_type: str = "") -> tuple[str, str, str]:
    """Parse a free-text angle/shot_type into a structured ``(h, v, s)`` triple.

    Mirrors ``angleService.parseFromLegacyText``. Returns sensible defaults
    when no keywords match.
    """
    combined = f"{angle_text or ''} {shot_type or ''}"
    h = _match_zh(combined, _ZH_HORIZONTAL_MAP) or "front"
    v = _match_zh(combined, _ZH_VERTICAL_MAP) or "eye_level"
    s = _match_zh(combined, _ZH_SHOT_SIZE_MAP) or "medium"
    return (h, v, s)


def infer_movement(text: str) -> str | None:
    """Infer camera movement enum from Chinese/English free text."""
    if not text:
        return None
    raw = text.strip()
    if raw in CAMERA_MOVEMENTS:
        return raw
    return _match_zh(raw, _ZH_MOVEMENT_MAP)


def infer_lighting(text: str) -> str | None:
    """Infer lighting style enum from Chinese/English free text."""
    if not text:
        return None
    raw = text.strip()
    if raw in LIGHTING_STYLES:
        return raw
    return _match_zh(raw, _ZH_LIGHTING_MAP)


def infer_depth_of_field(text: str) -> str | None:
    """Infer depth-of-field enum from Chinese/English free text."""
    if not text:
        return None
    raw = text.strip()
    if raw in DEPTH_OF_FIELD:
        return raw
    return _match_zh(raw, _ZH_DOF_MAP)


def _extract_initial_pose(action: str) -> str:
    """Extract the initial pose/state from an action description.

    Splits on common temporal transition words (然后, 接着, etc.) and returns
    the first segment, trimmed of trailing punctuation.
    """
    if not action:
        return ""
    process_words = [
        "然后", "接着", "接下来", "随后", "紧接着",
        "向下", "向上", "向前", "向后", "向左", "向右",
        "开始", "继续", "逐渐", "慢慢", "快速", "突然", "猛然",
    ]
    result = action
    for word in process_words:
        idx = result.find(word)
        if idx > 0:
            result = result[:idx]
            break
    return re.sub(r"[，。,.]\s*$", "", result).strip()


def _normalize_duration(v: Any) -> int:
    """Normalize a duration value to integer seconds (min 1, max 120)."""
    if v is None or v == "":
        return 5
    if isinstance(v, (int, float)):
        n = v
    else:
        s = str(v).strip().rstrip("sS")
        try:
            n = float(s)
        except ValueError:
            return 5
    if not (isinstance(n, (int, float)) and n == n):  # NaN check
        return 5
    return max(1, min(120, round(n)))


def build_camera_motion_chain(movement: str, shot_type: str, duration_sec: int) -> str:
    """Build a cinematic camera motion chain string based on duration.

    Mirrors ``episodeStoryboardService.buildCameraMotionChain``.
    Produces at least two steps emphasizing camera motion.
    """
    dur = max(1, duration_sec)
    mv = (movement or "").strip()
    st = (shot_type or "").strip()
    parts: list[str] = []

    if dur >= 12:
        parts.append("定镜约1秒建立空间")
        if re.search(r"跟|追随|尾随", mv):
            parts.append("侧后方跟拍主体位移")
        elif re.search(r"摇", mv):
            parts.append(f"{mv}拓展画幅信息")
        else:
            parts.append("缓推轨贴近动作核心")
        parts.append("横移从前景遮挡或门框一侧滑出拓宽视野带出纵深与环境细节")
    elif dur >= 8:
        parts.append("定镜")
        if mv and not re.match(r"^固定|^定镜", mv):
            parts.append(mv)
        else:
            parts.append("缓推轨由远及近")
        parts.append("微横移或轻摇让背景纵深与环境细节可读")
    elif dur >= 5:
        parts.append("定镜起幅")
        parts.append(mv or "缓推轨或短跟拍强化动线")
    else:
        parts.append(mv or "短跟拍或微推")

    if ("远" in st or "全景" in st) and not any(re.search(r"推|移|跟|摇", p) for p in parts):
        parts.append("缓推轨向事件中心")

    chain = "，".join(dict.fromkeys(filter(None, parts)))
    return chain or "定镜，缓推轨"


# ═══════════════════════════════════════════════════════════════════════════════
# StoryboardEnhancer
# ═══════════════════════════════════════════════════════════════════════════════


class StoryboardEnhancer:
    """Enhance basic storyboard shots with professional cinematography parameters.

    Takes a minimal shot dict (description, action, dialogue, etc.) and enriches
    it with:

    - **Shot type** (景别): 远景 / 全景 / 中景 / 近景 / 特写 / 大特写
    - **Camera angles**: horizontal (正面/侧面/背面), vertical (平视/俯拍/仰拍),
      special (荷兰角/过肩)
    - **Camera movement**: 固定 / 推 / 拉 / 摇 / 移 / 跟 / 升降 / 手持
    - **Lighting style** and **depth of field** (inferred from atmosphere)
    - Professional ``image_prompt`` and ``video_prompt`` strings

    Supports two creation modes:

    - ``classic``: single-reference image generation per shot
    - ``universal``: multi-reference mode with ``universal_segment_text`` for
      video models that accept dense single-line timeline prompts

    Usage::

        enhancer = StoryboardEnhancer(style="cinematic, film grain")
        enhanced = enhancer.enhance_shot({
            "description": "女主角在雨中奔跑",
            "action": "奔跑时回头望去",
            "dialogue": "等等我！",
            "location": "城市街道",
            "time": "夜晚",
            "duration": 6,
        })
        print(enhanced["image_prompt"])
        print(enhanced["video_prompt"])
    """

    def __init__(
        self,
        style: str = "",
        video_ratio: str = DEFAULT_ASPECT_RATIO,
        creation_mode: str = "classic",
    ):
        self.style = style.strip()
        self.video_ratio = video_ratio.strip() or DEFAULT_ASPECT_RATIO
        self.creation_mode = creation_mode if creation_mode in ("classic", "universal") else "classic"

    # ── Public API ──────────────────────────────────────────────────────────

    def enhance_shot(self, shot_data: dict) -> dict:
        """Enhance a single storyboard shot with professional parameters.

        Args:
            shot_data: A dict with any of the keys: ``description``, ``action``,
                ``dialogue``, ``narration``, ``result``, ``location``, ``time``,
                ``duration``, ``atmosphere``, ``emotion``, ``shot_type``,
                ``angle``, ``movement``, ``scene_description``, ``title``,
                ``shot_number``, ``characters``.

        Returns:
            The input dict augmented with: ``shot_type_en``, ``angle_h``,
            ``angle_v``, ``angle_s``, ``angle_special``, ``movement_en``,
            ``lighting_style``, ``depth_of_field``, ``angle_label``,
            ``angle_fragment``, ``image_prompt``, ``video_prompt``,
            ``creation_mode``, and optionally ``universal_segment_text``.
        """
        sb = dict(shot_data)  # shallow copy; we add keys to the copy

        # Parse structured angle triple from existing fields or legacy text
        h, v, s = self._resolve_angles(sb)
        sb["angle_h"] = h
        sb["angle_v"] = v
        sb["angle_s"] = s

        # Resolve special angle (荷兰角/过肩/etc.) from atmosphere/description text
        sb["angle_special"] = self._infer_special_angle(sb)

        # Resolve movement
        movement = self._resolve_movement(sb)
        sb["movement"] = movement

        # Infer lighting and depth of field from atmosphere/time/description
        sb["lighting_style"] = self._infer_lighting(sb)
        sb["depth_of_field"] = self._infer_depth_of_field(sb)

        # Build bilingual labels and fragments
        sb["angle_label"] = angle_to_chinese_label(h, v, s)
        sb["angle_fragment"] = angle_to_english_fragment(h, v, s)
        sb["shot_type_en"] = shot_type_to_english(s)
        sb["movement_en"] = movement_to_english(movement) if movement else ""

        # Normalize duration
        sb["duration"] = _normalize_duration(sb.get("duration", 5))

        # Split scene_description into location/time if needed
        if not sb.get("location") and sb.get("scene_description"):
            self._split_scene_description(sb)

        # Generate prompts
        sb["image_prompt"] = self.generate_image_prompt(
            scene=sb.get("scene_description") or self._scene_str(sb),
            angle=sb["angle_label"],
            action=sb.get("action", ""),
            mood=sb.get("emotion", "") or sb.get("atmosphere", ""),
            style=self.style,
        )
        sb["video_prompt"] = self.generate_video_prompt(
            scene=sb.get("scene_description") or self._scene_str(sb),
            action=sb.get("action", ""),
            dialogue=sb.get("dialogue", ""),
            shot_type=sb["angle_label"],
            movement=sb.get("movement", ""),
            atmosphere=sb.get("atmosphere", ""),
            duration=sb["duration"],
            style=self.style,
            ratio=self.video_ratio,
        )

        # Universal mode: generate dense single-line segment text
        sb["creation_mode"] = self.creation_mode
        if self.creation_mode == "universal":
            sb["universal_segment_text"] = self._build_universal_segment_text(sb)
        else:
            sb["universal_segment_text"] = None

        return sb

    def generate_image_prompt(
        self,
        scene: str,
        angle: str,
        action: str,
        mood: str,
        style: str = "",
    ) -> str:
        """Generate a professional image generation prompt.

        Assembles scene location/time, camera angle, initial action pose,
        emotion/mood, and style tokens into a comma-separated prompt string
        suitable for image AI models.

        Args:
            scene: Scene description or "location, time" string.
            angle: Chinese angle label (e.g. "近景·平视·正面").
            action: Action description (only the initial pose is used).
            mood: Emotion or atmosphere keyword.
            style: Additional style tokens (English, appended verbatim).

        Returns:
            A comma-joined prompt string ending with "首帧静止画面".
        """
        parts: list[str] = []

        if scene:
            parts.append(scene)

        if angle:
            parts.append(angle)

        initial_pose = _extract_initial_pose(action)
        if initial_pose:
            parts.append(initial_pose)

        if mood:
            parts.append(mood)

        style_text = (style or "").strip()
        if style_text:
            parts.append(style_text)

        parts.append("首帧静止画面")
        return "，".join(parts)

    def generate_video_prompt(
        self,
        scene: str,
        action: str,
        dialogue: str,
        shot_type: str,
        movement: str,
        atmosphere: str,
        duration: int = 5,
        style: str = "",
        ratio: str = DEFAULT_ASPECT_RATIO,
    ) -> str:
        """Generate a professional video generation prompt.

        Assembles scene, action, dialogue, shot type, camera movement,
        atmosphere, duration, style, and aspect ratio into a period-separated
        prompt string suitable for video AI models.

        Args:
            scene: Scene description or "location, time".
            action: Full action description for the shot.
            dialogue: Character dialogue text.
            shot_type: Shot type / angle label (Chinese).
            movement: Camera movement label (Chinese).
            atmosphere: Atmosphere/mood description.
            duration: Shot duration in seconds.
            style: Additional style tokens.
            ratio: Video aspect ratio (e.g. "9:16", "16:9").

        Returns:
            A period-joined prompt string, or "视频场景" if all fields are empty.
        """
        parts: list[str] = []

        if scene:
            parts.append(f"场景：{scene}")

        if action:
            parts.append(f"动作：{action}")

        if dialogue:
            parts.append(f"对话：{dialogue}")

        if shot_type:
            parts.append(f"景别：{shot_type}")

        if movement:
            parts.append(f"运镜：{movement}")

        if atmosphere:
            parts.append(f"氛围：{atmosphere}")

        dur = max(1, duration)
        parts.append(f"时长：{dur}秒")

        if style:
            parts.append(f"风格：{style}")

        if ratio:
            parts.append(f"=VideoRatio: {ratio}")

        return "。".join(parts) if parts else "视频场景"

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _scene_str(sb: dict) -> str:
        """Build a "location, time" scene string from shot fields."""
        loc = sb.get("location", "")
        time = sb.get("time", "")
        if loc and time:
            return f"{loc}，{time}"
        return loc or time or ""

    @staticmethod
    def _split_scene_description(sb: dict) -> None:
        """Split ``scene_description`` into ``location`` and ``time`` in-place."""
        desc = str(sb.get("scene_description", "")).strip()
        if not desc:
            return
        sep_idx = re.search(r"[，,、]", desc)
        if sep_idx and sep_idx.start() > 0:
            sb["location"] = desc[: sep_idx.start()].strip()
            if not sb.get("time"):
                sb["time"] = desc[sep_idx.end() :].strip()
        else:
            sb["location"] = desc

    @staticmethod
    def _resolve_angles(sb: dict) -> tuple[str, str, str]:
        """Resolve the ``(h, v, s)`` angle triple from shot fields."""
        # Prefer structured fields if already present
        h = sb.get("angle_h")
        v = sb.get("angle_v")
        s = sb.get("angle_s")
        if h and v and s:
            return (h, v, s)

        # Fall back to parsing legacy angle/shot_type text
        angle_text = sb.get("angle", "") or sb.get("camera_angle", "")
        shot_type_text = sb.get("shot_type", "") or sb.get("camera_shot_type", "")
        return parse_legacy_angle(angle_text, shot_type_text)

    @staticmethod
    def _resolve_movement(sb: dict) -> str:
        """Resolve camera movement from the shot dict."""
        raw = (sb.get("movement") or sb.get("camera_movement") or "").strip()
        if not raw:
            return ""
        if raw in CAMERA_MOVEMENTS:
            return raw
        inferred = infer_movement(raw)
        return inferred or raw

    @staticmethod
    def _infer_special_angle(sb: dict) -> str | None:
        """Infer special angle (荷兰角/过肩/主观/俯瞰) from text fields."""
        combined = " ".join([
            str(sb.get("atmosphere", "")),
            str(sb.get("description", "")),
            str(sb.get("action", "")),
            str(sb.get("angle", "")),
        ]).lower()

        if any(k in combined for k in ["荷兰", "dutch", "tilt"]):
            return "dutch"
        if any(k in combined for k in ["过肩", "over shoulder", "over-the-shoulder"]):
            return "over_shoulder"
        if any(k in combined for k in ["主观", "pov", "第一人称"]):
            return "pov"
        if any(k in combined for k in ["俯瞰", "top-down", "top down", "flat lay"]):
            return "top_down"
        return None

    @staticmethod
    def _infer_lighting(sb: dict) -> str | None:
        """Infer lighting style from atmosphere, time, and description fields."""
        combined = " ".join([
            str(sb.get("atmosphere", "")),
            str(sb.get("time", "")),
            str(sb.get("description", "")),
        ])
        return infer_lighting(combined)

    @staticmethod
    def _infer_depth_of_field(sb: dict) -> str | None:
        """Infer depth of field from shot size and atmosphere."""
        s = sb.get("angle_s", "")
        shot_type_text = str(sb.get("shot_type", "")).lower()
        combined = f"{s} {shot_type_text}"

        if s == "close_up" or re.search(r"特写|close.?up|extreme close", combined):
            return "shallow"
        if s in ("extreme_wide", "wide") or re.search(r"大远景|远景|long shot|wide shot", combined):
            return "deep"
        if s == "medium" or re.search(r"中景|medium shot", combined):
            return "medium"
        return infer_depth_of_field(combined)

    def _build_universal_segment_text(self, sb: dict) -> str:
        """Build a dense single-line universal segment text for video models.

        Mirrors ``episodeStoryboardService.buildFallbackUniversalSeedanceLine``.
        Produces a high-density prompt containing: subject, narrative dynamics,
        spatial layers (foreground/midground/background), lighting, camera
        motion chain, dialogue, sound design, and style tail.
        """
        action = re.sub(r"\s+", " ", str(sb.get("action", ""))).strip()[:220]
        result = re.sub(r"\s+", " ", str(sb.get("result", ""))).strip()[:120]
        emotion = re.sub(r"\s+", " ", str(sb.get("emotion", "") or sb.get("atmosphere", ""))).strip()[:24]
        atmosphere = re.sub(r"\s+", " ", str(sb.get("atmosphere", ""))).strip()[:100]
        shot_bits = ", ".join(filter(None, [sb.get("shot_type", ""), sb.get("angle", "")])).strip()
        loc = ", ".join(filter(None, [sb.get("location", ""), sb.get("time", "")])).strip() or "叙事空间"
        dur = max(1, _normalize_duration(sb.get("duration", 5)))

        lighting = sb.get("lighting_style", "")
        light_zh = lighting_to_chinese(lighting) if lighting else "主光方向明确侧光或窗光"

        dof = sb.get("depth_of_field", "")
        if dof == "extreme_shallow":
            dof_zh = "浅景深前景虚化明显"
        elif dof == "shallow":
            dof_zh = "浅景深背景柔化"
        elif dof == "deep":
            dof_zh = "深焦前后景均清晰"
        elif dof == "medium":
            dof_zh = "景深适中"
        else:
            dof_zh = "景深随景别可感"

        shot_num = max(1, int(sb.get("shot_number", 1) or 1))
        link = "开篇情绪奠基" if shot_num <= 1 else "延续上一镜动势与视线"

        motion_core = action or (
            "在镜内时长里完成一段可感知的动作阶段变化，"
            "含走位或身体重心的转移，避免单姿势摆拍"
        )
        emo_paren = f"（{emotion}）" if emotion else "（专注投入）"

        fg = f"{atmosphere[:42]}与主体相关的虚化层次" if atmosphere else "与动作相关的近景细节或桌面器物"
        mg = "主体动作与表情核心区" if action else "主体占据画面叙事中心"
        bg = f"{loc}的环境延展与氛围层次" if loc else "环境纵深与空间气氛"

        light_block = (
            f"[{light_zh}；结合{loc}，建议色温具象化如4500K-5600K区间择一；"
            f"明暗比约2:1至3:1；{dof_zh}]"
        )

        cam_chain = build_camera_motion_chain(
            sb.get("movement", ""),
            sb.get("shot_type", ""),
            dur,
        )

        narr_dyn = (
            f"约{dur}秒内——在{loc}，@人物1"
            f"{f'先后：{action}' if action else '持续推进戏内动作'}，"
            f"{f'阶段收束为：{result}' if result else '动作与视线随时间有阶段推进'}；"
            f"镜头以「{cam_chain}」配合人物动线，读出空间纵深与时间流逝"
        )

        lens_block = (
            f"运镜链：{cam_chain}；景别机位：{shot_bits or '中景，平视'}，"
            f"三分法或对角线择一"
            f"（结尾动势：[{result or '视线或身体动线指向下一个节拍，动势渐收可衔接下镜'}]）"
        )

        sfx = (
            f"环境层-[与{loc}一致的环境声底与远处细节] "
            f"动作层-[与动作同步的物理接触声] "
            f"情绪层-[无旋律仅以空间混响与材质细微声烘托情绪张力]"
        )

        style_tail = (self.style and self.style.strip()) or "电影感叙事光色"

        dia = str(sb.get("dialogue", "")).strip().replace('"', "'")

        line = (
            f"主体：@人物1{emo_paren}"
            f"[朝向：依轴线面向戏中对象或画左/画右择一并保持统一] "
            f"正在 {motion_core}（与上镜衔接：{link}） "
            f"叙事动态：{narr_dyn} "
            f"空间：前景-[{fg}] 中景-[{mg}] 背景-[{bg}] "
            f"光影：{light_block} "
            f"镜头：{lens_block}"
        )

        if dia:
            line += f' 台词：第1秒 @人物1："{dia[:120]}"'

        line += f" 音效：{sfx} {style_tail} [禁BGM][禁字幕]"

        return re.sub(r"[\r\n]+", " ", line)


# ═══════════════════════════════════════════════════════════════════════════════
# CharacterConsistency
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class IdentityAnchor:
    """A single visual identity anchor layer for a character."""

    face_shape: str = ""
    facial_features: str = ""
    unique_marks: str = ""
    color_anchors: dict[str, str] = field(default_factory=dict)
    skin_texture: str = ""
    hair_style: str = ""
    body_build: str = ""
    clothing: str = ""
    accessories: str = ""
    pose: str = ""


class CharacterConsistency:
    """Manage character visual consistency across shots.

    Provides:

    - **6-layer identity anchors** (face, body, clothing, hair, accessories, pose)
      extracted from a character description, with Hex color codes for
      hair/eyes/skin/outfit.
    - **Color palette** generation for cross-shot color consistency.
    - **Polished prompt** generation for image AI, ensuring the same character
      looks identical across different shots.
    - **Tail-frame linking** (尾帧衔接): extract the last frame of a shot's
      video to use as the first frame of the next shot, ensuring visual
      continuity between consecutive clips.

    Usage::

        cc = CharacterConsistency(style="cinematic, film grain")
        anchors = cc.create_identity_anchors("黑发短发，身穿白色衬衫的青年男性")
        polished = cc.create_polished_prompt("黑发短发，身穿白色衬衫的青年男性", "李明")
        cc.link_tail_frame(Path("shot_01.mp4"), Path("shot_02_first_frame.png"))
    """

    #: The 6 identity anchor layers.
    ANCHOR_LAYERS = ("face", "body", "clothing", "hair", "accessories", "pose")

    #: System prompt for AI-based identity anchor extraction.
    IDENTITY_ANCHORS_SYSTEM_PROMPT = (
        "You are a character visual analyst. Extract precise visual identity "
        "anchors from character appearance descriptions.\n\n"
        "Output ONLY a valid JSON object with these exact 6 keys:\n"
        "{\n"
        '  "face_shape": "precise description of face/skull shape, jawline, '
        'cheekbones (e.g. oval face, sharp jawline, high cheekbones)",\n'
        '  "facial_features": "eye shape+color+Hex, nose bridge+tip, lip '
        'thickness+shape (e.g. almond eyes #3D2B1F, straight nose, thin lips)",\n'
        '  "unique_marks": "scars, moles, tattoos, birthmarks, distinctive '
        'features — or \'none\'",\n'
        '  "color_anchors": {\n'
        '    "hair": "#HexCode (e.g. #1A0A00 for black, #C8A96E for blonde)",\n'
        '    "eyes": "#HexCode",\n'
        '    "skin": "#HexCode (e.g. #F5DEB3 for wheat, #FDDBB4 for fair)",\n'
        '    "primary_outfit": "#HexCode of dominant clothing color"\n'
        "  },\n"
        '  "skin_texture": "skin tone description + texture (e.g. fair porcelain '
        'smooth, tanned slightly weathered)",\n'
        '  "hair_style": "length + style + texture (e.g. shoulder-length wavy '
        'black hair with loose strands, short crew cut)"\n'
        "}\n\n"
        "Rules:\n"
        "- Use Hex color codes for ALL color values — never use color names\n"
        "- Extract ONLY what is explicitly stated; infer Hex values from color "
        "descriptions\n"
        "- Keep each field concise (1-2 sentences max)\n"
        "- If information is missing for a field, write \"unspecified\"\n"
        "- Output ONLY the JSON object, no markdown, no explanation"
    )

    def __init__(self, style: str = "", style_en: str = ""):
        self.style = style.strip()
        self.style_en = style_en.strip() or self.style

    # ── Public API ──────────────────────────────────────────────────────────

    def create_identity_anchors(self, character_desc: str) -> dict:
        """Extract 6-layer visual identity anchors from a character description.

        This is a heuristic (non-AI) implementation that extracts color codes
        and key features using regex patterns. For AI-powered extraction, use
        :meth:`create_identity_anchors_with_ai`.

        Args:
            character_desc: Character appearance description (Chinese or English).

        Returns:
            A dict with keys: ``face_shape``, ``facial_features``, ``unique_marks``,
            ``color_anchors`` (hair/eyes/skin/primary_outfit as Hex codes),
            ``skin_texture``, ``hair_style``, ``body_build``, ``clothing``,
            ``accessories``, ``pose``, plus ``color_palette`` (list of Hex strings).
        """
        desc = (character_desc or "").strip()
        anchors: dict[str, Any] = {
            "face_shape": self._extract_face_shape(desc),
            "facial_features": self._extract_facial_features(desc),
            "unique_marks": self._extract_unique_marks(desc),
            "color_anchors": self._extract_color_anchors(desc),
            "skin_texture": self._extract_skin_texture(desc),
            "hair_style": self._extract_hair_style(desc),
            "body_build": self._extract_body_build(desc),
            "clothing": self._extract_clothing(desc),
            "accessories": self._extract_accessories(desc),
            "pose": "",
        }

        # Build color palette from color_anchors
        anchors["color_palette"] = self._build_color_palette(anchors["color_anchors"])
        return anchors

    def create_identity_anchors_with_ai(
        self,
        character_desc: str,
        generate_text_fn,
    ) -> dict:
        """AI-powered identity anchor extraction.

        Args:
            character_desc: Character appearance description.
            generate_text_fn: A callable ``(user_prompt, system_prompt, **opts)
                -> str`` that calls an LLM to generate text.

        Returns:
            Parsed identity anchors dict. Falls back to heuristic extraction
            if the AI response cannot be parsed.
        """
        import json

        desc = (character_desc or "").strip()
        if not desc:
            return {}

        try:
            raw = generate_text_fn(
                f"Character appearance description:\n{desc}",
                self.IDENTITY_ANCHORS_SYSTEM_PROMPT,
                max_tokens=800,
                temperature=0.1,
            )
            anchors = json.loads(raw)
            if not isinstance(anchors, dict):
                raise ValueError("not a dict")
            # Ensure color_palette is present
            if "color_anchors" in anchors and isinstance(anchors["color_anchors"], dict):
                anchors["color_palette"] = list(anchors["color_anchors"].values())
            return anchors
        except Exception as exc:
            logger.warning("AI identity anchor extraction failed: %s, falling back to heuristic", exc)
            return self.create_identity_anchors(desc)

    def generate_color_palette(self, character_desc: str) -> list[str]:
        """Generate a color palette (list of Hex codes) for a character.

        Extracts Hex color codes from the description for hair, eyes, skin,
        and primary outfit, ensuring visual consistency across shots.
        """
        anchors = self.create_identity_anchors(character_desc)
        return anchors.get("color_palette", [])

    def create_polished_prompt(
        self,
        character_desc: str,
        character_name: str = "",
        style_en: str = "",
    ) -> str:
        """Create a polished prompt for cross-shot character consistency.

        Builds a structured prompt that can be prepended to every shot's
        image prompt to ensure the character looks identical. The prompt
        includes identity anchors, color palette, and mandatory style
        constraints.

        Args:
            character_desc: Character appearance description.
            character_name: Optional character name for identification.
            style_en: Optional English style tokens (overrides ``self.style_en``).

        Returns:
            A polished prompt string suitable for image AI.
        """
        anchors = self.create_identity_anchors(character_desc)
        style = (style_en or self.style_en).strip()
        name = character_name.strip()

        parts: list[str] = []

        if name:
            parts.append(f"角色：{name}")

        # Identity anchor summary
        anchor_lines: list[str] = []
        if anchors["hair_style"]:
            anchor_lines.append(f"发型：{anchors['hair_style']}")
        if anchors["face_shape"]:
            anchor_lines.append(f"脸型：{anchors['face_shape']}")
        if anchors["facial_features"]:
            anchor_lines.append(f"五官：{anchors['facial_features']}")
        if anchors["skin_texture"]:
            anchor_lines.append(f"肤色：{anchors['skin_texture']}")
        if anchors["body_build"]:
            anchor_lines.append(f"体型：{anchors['body_build']}")
        if anchors["clothing"]:
            anchor_lines.append(f"服装：{anchors['clothing']}")
        if anchors["accessories"]:
            anchor_lines.append(f"配饰：{anchors['accessories']}")
        if anchors["unique_marks"] and anchors["unique_marks"] != "none":
            anchor_lines.append(f"标记：{anchors['unique_marks']}")

        if anchor_lines:
            parts.append("【身份锚点】" + "；".join(anchor_lines))

        # Color palette
        palette = anchors.get("color_palette", [])
        if palette:
            parts.append(f"【色彩锚点】{' '.join(palette)}")

        # Mandatory style constraint
        if style:
            parts.append(f"【画风·最高优先级】{style}")

        # Consistency enforcement
        parts.append("跨镜头角色一致性约束：保持发型、肤色、服装、配饰完全一致")

        return "。".join(parts)

    def link_tail_frame(
        self,
        video_path: Path,
        output_image_path: Path,
    ) -> bool:
        """Extract the last frame of a video for tail-frame linking (尾帧衔接).

        Uses FFmpeg's ``-sseof -1`` to seek to the last second and extract
        a single frame. The resulting image can be used as the first frame
        of the next shot's video generation, ensuring visual continuity.

        Args:
            video_path: Path to the source video file.
            output_image_path: Path for the extracted frame image (JPG/PNG).

        Returns:
            ``True`` if extraction succeeded, ``False`` otherwise.
        """
        if not video_path.exists():
            logger.warning("Tail-frame link: source video not found: %s", video_path)
            return False

        output_image_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = _get_ffmpeg_binary()

        cmd = [
            ffmpeg,
            "-sseof", "-1",
            "-i", str(video_path),
            "-update", "1",
            "-q:v", "2",
            "-frames:v", "1",
            "-y",
            str(output_image_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.warning(
                    "Tail-frame link: ffmpeg failed: %s",
                    (result.stderr or "")[-500:],
                )
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("Tail-frame link: ffmpeg error: %s", exc)
            return False

        if not output_image_path.exists():
            logger.warning("Tail-frame link: output file not created: %s", output_image_path)
            return False

        logger.info(
            "Tail-frame link: extracted last frame from %s to %s",
            video_path.name,
            output_image_path.name,
        )
        return True

    def build_tail_frame_prompt(
        self,
        current_shot: dict,
        next_shot: dict,
        tail_frame_path: Path | None = None,
    ) -> str:
        """Build a prompt suffix that references a tail-frame for continuity.

        Args:
            current_shot: The current shot dict (source of the tail frame).
            next_shot: The next shot dict (target of the tail frame).
            tail_frame_path: Optional path to the extracted tail-frame image.

        Returns:
            A prompt suffix string describing the visual continuity link.
        """
        current_num = current_shot.get("shot_number", 0)
        next_num = next_shot.get("shot_number", current_num + 1)
        current_action = str(current_shot.get("action", ""))[:80]
        next_action = str(next_shot.get("action", ""))[:80]

        parts = [
            f"尾帧衔接：从分镜#{current_num}延续至分镜#{next_num}",
            f"上镜动势：{current_action}" if current_action else "上镜动势：自然收束",
            f"本镜承接：{next_action}" if next_action else "本镜承接：延续情绪与视线",
        ]

        if tail_frame_path and tail_frame_path.exists():
            parts.append(f"参考尾帧：{tail_frame_path.name}")

        return "。".join(parts)

    # ── Internal extraction helpers ──────────────────────────────────────────

    @staticmethod
    def _find_hex_colors(text: str) -> list[str]:
        """Find all Hex color codes in text."""
        return re.findall(r"#[0-9A-Fa-f]{6}\b", text)

    def _extract_face_shape(self, desc: str) -> str:
        """Extract face shape description from text."""
        patterns = [
            r"(圆形|方形|瓜子脸|鹅蛋脸|心形脸|菱形脸|oval|round|square|heart|diamond|sharp jawline|high cheekbones)",
        ]
        for pat in patterns:
            m = re.search(pat, desc, re.IGNORECASE)
            if m:
                return m.group(0)
        return "unspecified"

    def _extract_facial_features(self, desc: str) -> str:
        """Extract facial features (eyes, nose, lips) from text."""
        features: list[str] = []
        eye_match = re.search(
            r"([\u4e00-\u9fff]+眼|almond eyes?|round eyes?|narrow eyes?|deep.?set eyes?)"
            r"(?:[，,色]?\s*(?:色|color)?)?\s*(#[0-9A-Fa-f]{6})?",
            desc, re.IGNORECASE,
        )
        if eye_match:
            features.append(eye_match.group(0))

        nose_match = re.search(
            r"(高鼻梁|塌鼻|直鼻|high nose bridge|straight nose|flat nose|button nose)",
            desc, re.IGNORECASE,
        )
        if nose_match:
            features.append(nose_match.group(0))

        lip_match = re.search(
            r"(薄唇|厚唇|樱桃小嘴|thin lips?|full lips?|plump lips?)",
            desc, re.IGNORECASE,
        )
        if lip_match:
            features.append(lip_match.group(0))

        return "；".join(features) if features else "unspecified"

    def _extract_unique_marks(self, desc: str) -> str:
        """Extract unique marks (scars, moles, tattoos) from text."""
        patterns = [
            r"(疤痕|痣|胎记|纹身|刀疤|scar|mole|tattoo|birthmark)",
        ]
        for pat in patterns:
            m = re.search(pat, desc, re.IGNORECASE)
            if m:
                # Get surrounding context (up to 30 chars)
                start = max(0, m.start() - 10)
                end = min(len(desc), m.end() + 20)
                return desc[start:end].strip()
        return "none"

    def _extract_color_anchors(self, desc: str) -> dict[str, str]:
        """Extract color anchors (hair, eyes, skin, outfit) as Hex codes."""
        anchors: dict[str, str] = {}

        # Hair color
        hair_color = self._match_color(desc, [
            r"黑发|黑色头发|#1[0-9A-Fa-f]{5}", r"金发|金色头发|#C[0-9A-Fa-f]{5}",
            r"棕发|褐色头发|brown hair", r"白发|银发|白色头发|white hair|silver hair",
            r"红发|红色头发|red hair", r"蓝发|蓝色头发|blue hair",
        ])
        anchors["hair"] = hair_color or "unspecified"

        # Eye color
        eye_color = self._match_color(desc, [
            r"黑眼|黑色眼睛|#3[0-9A-Fa-f]{5}", r"蓝眼|蓝色眼睛|blue eyes",
            r"棕眼|褐色眼睛|brown eyes", r"绿眼|绿色眼睛|green eyes",
            r"金眼|金色眼睛|golden eyes",
        ])
        anchors["eyes"] = eye_color or "unspecified"

        # Skin color
        skin_color = self._match_color(desc, [
            r"白皙|#F[0-9A-Fa-f]{5}|fair skin|pale", r"小麦色|#D[0-9A-Fa-f]{5}|tanned? skin|wheat",
            r"古铜色|bronze skin", r"深色皮肤|dark skin|#[0-9A-Fa-f]{5}",
        ])
        anchors["skin"] = skin_color or "unspecified"

        # Outfit color
        outfit_match = re.search(
            r"(白色|黑色|红色|蓝色|绿色|黄色|灰色|紫色|pink|red|blue|green|yellow|gray|black|white)\s*"
            r"(衬衫|外套|裙子|裤子|衣服| dress| shirt| jacket| coat| pants)",
            desc, re.IGNORECASE,
        )
        if outfit_match:
            anchors["primary_outfit"] = outfit_match.group(0)
        else:
            anchors["primary_outfit"] = "unspecified"

        return anchors

    def _extract_skin_texture(self, desc: str) -> str:
        """Extract skin texture description."""
        if re.search(r"光滑|白皙|smooth|porcelain", desc, re.IGNORECASE):
            return "fair porcelain smooth"
        if re.search(r"粗糙|风霜|weathered|rough", desc, re.IGNORECASE):
            return "weathered slightly rough"
        if re.search(r"小麦|tanned?", desc, re.IGNORECASE):
            return "tanned smooth"
        return "unspecified"

    def _extract_hair_style(self, desc: str) -> str:
        """Extract hair style, length, and texture."""
        m = re.search(
            r"(长发|短发|中长发|波波头|马尾|双马尾|编发|寸头|光头|卷发|直发|"
            r"long hair|short hair|medium.?length|bob|ponytail|braided|buzz cut|bald|"
            r"curly|straight|wavy)\s*"
            r"([\u4e00-\u9fff]*[发发]|hair)?",
            desc, re.IGNORECASE,
        )
        return m.group(0).strip() if m else "unspecified"

    def _extract_body_build(self, desc: str) -> str:
        """Extract body build/type."""
        m = re.search(
            r"(高挑|矮小|苗条|健壮|魁梧|瘦削|丰满|"
            r"tall|short|slim|slender|athletic|muscular|stocky|lean|curvy)",
            desc, re.IGNORECASE,
        )
        return m.group(0) if m else "unspecified"

    def _extract_clothing(self, desc: str) -> str:
        """Extract clothing description."""
        m = re.search(
            r"(白色|黑色|红色|蓝色|绿色|灰色)?\s*"
            r"(衬衫|外套|西装|裙子|连衣裙|裤子|T恤|夹克|大衣|和服|汉服|"
            r"shirt|suit|dress|skirt|pants|jacket|coat|kimono)",
            desc, re.IGNORECASE,
        )
        return m.group(0).strip() if m else "unspecified"

    def _extract_accessories(self, desc: str) -> str:
        """Extract accessories description."""
        m = re.search(
            r"(眼镜|耳环|项链|戒指|手表|帽子|围巾|领带|"
            r"glasses?|earrings?|necklace|ring|watch|hat|scarf|tie)",
            desc, re.IGNORECASE,
        )
        return m.group(0) if m else "none"

    @staticmethod
    def _match_color(desc: str, patterns: list[str]) -> str | None:
        """Match the first color pattern that hits, returning a description."""
        for pat in patterns:
            m = re.search(pat, desc, re.IGNORECASE)
            if m:
                return m.group(0)
        return None

    @staticmethod
    def _build_color_palette(color_anchors: dict[str, str]) -> list[str]:
        """Build a list of Hex color codes from color anchors.

        If an anchor value already contains a ``#RRGGBB`` code, that code is
        used directly. Otherwise, common Chinese/English color names in the
        value are resolved to Hex codes via :data:`COLOR_NAME_TO_HEX`.
        """
        palette: list[str] = []
        for key in ("hair", "eyes", "skin", "primary_outfit"):
            val = color_anchors.get(key, "")
            if not val or val == "unspecified":
                continue
            hex_match = re.search(r"#[0-9A-Fa-f]{6}\b", val)
            if hex_match:
                palette.append(hex_match.group(0))
                continue
            # Try resolving color names
            lower_val = val.lower()
            for name, hex_code in COLOR_NAME_TO_HEX.items():
                if name.lower() in lower_val:
                    palette.append(hex_code)
                    break
        return palette


# ═══════════════════════════════════════════════════════════════════════════════
# VideoMergeService
# ═══════════════════════════════════════════════════════════════════════════════


class VideoMergeService:
    """Merge multiple shot videos using FFmpeg concat.

    Provides:

    - **Concat merging**: Join multiple MP4 files into a single video using
      FFmpeg's ``concat`` demuxer (stream copy when possible).
    - **Resolution normalization**: Scale and pad each video to a uniform
      target resolution (``normalizeVideoFileToTargetPixels``) to prevent
      visual jitter when clips have different pixel dimensions.
    - **Subtitle burning**: Overlay SRT/ASS subtitles onto the merged video.
    - **Audio overlay**: Mix dialogue TTS or narration audio tracks.
    - **Watermark**: Add a text watermark (e.g. in the bottom-right corner).
    - **Aspect ratio support**: Handles 9:16, 16:9, 21:9, 1:1, and more.

    Usage::

        merger = VideoMergeService()
        success = merger.merge_videos(
            video_paths=[Path("shot1.mp4"), Path("shot2.mp4")],
            output_path=Path("merged.mp4"),
            options={
                "aspect_ratio": "9:16",
                "burn_subtitles": True,
                "subtitle_path": Path("subtitles.srt"),
                "audio_path": Path("narration.mp3"),
                "watermark_text": "AI Manga Studio",
            },
        )
    """

    def __init__(self, ffmpeg_path: str | None = None, ffprobe_path: str | None = None):
        self.ffmpeg = ffmpeg_path or _get_ffmpeg_binary()
        self.ffprobe = ffprobe_path or _get_ffprobe_binary()

    # ── Public API ──────────────────────────────────────────────────────────

    def merge_videos(
        self,
        video_paths: list[Path],
        output_path: Path,
        options: dict | None = None,
    ) -> bool:
        """Merge multiple video files into a single output video.

        The pipeline is:

        1. Validate and filter existing video files.
        2. If ``normalize_resolution`` is enabled (default), normalize each
           clip to the target pixel dimensions for the specified aspect ratio.
        3. Concat the (optionally normalized) clips using FFmpeg concat demuxer.
        4. If any post-processing options are set (subtitles, audio, watermark),
           run a second FFmpeg pass to apply them.

        Args:
            video_paths: List of paths to the input video files (in order).
            output_path: Path for the merged output video.
            options: Optional dict with keys:

                - ``aspect_ratio`` (str): Target aspect ratio (default "16:9").
                - ``normalize_resolution`` (bool): Whether to normalize each
                  clip's resolution (default ``True``).
                - ``burn_subtitles`` (bool): Burn SRT/ASS subtitles.
                - ``subtitle_path`` (Path): Path to subtitle file.
                - ``audio_path`` (Path): Path to audio file for overlay.
                - ``audio_volume`` (float): Audio volume (0.0-1.0, default 1.0).
                - ``watermark_text`` (str): Text watermark to overlay.
                - ``watermark_position`` (str): "bottom_right" (default) or
                  "top_right", "bottom_left", "top_left".
                - ``crf`` (int): Constant rate factor (default 23).
                - ``preset`` (str): Encoding preset (default "medium").

        Returns:
            ``True`` if merge succeeded, ``False`` otherwise.
        """
        opts = options or {}
        aspect_ratio = opts.get("aspect_ratio", DEFAULT_ASPECT_RATIO)
        normalize = opts.get("normalize_resolution", True)

        # Filter to existing files
        valid_paths = [p for p in video_paths if p and Path(p).exists()]
        if not valid_paths:
            logger.warning("Video merge: no valid input video files")
            return False

        if len(valid_paths) == 1:
            # Single video: just copy or post-process
            shutil.copy2(valid_paths[0], output_path)
        else:
            # Optionally normalize each clip
            if normalize:
                target_w, target_h = aspect_ratio_to_pixels(aspect_ratio)
                valid_paths = [
                    self._normalize_or_keep(p, target_w, target_h)
                    for p in valid_paths
                ]

            # Concat
            if not self._run_concat(valid_paths, output_path):
                logger.warning("Video merge: concat failed, using first clip as fallback")
                shutil.copy2(valid_paths[0], output_path)

        # Post-processing: subtitles, audio, watermark
        post_needed = (
            opts.get("burn_subtitles")
            or opts.get("audio_path")
            or (opts.get("watermark_text") and str(opts.get("watermark_text", "")).strip())
        )

        if post_needed:
            post_output = output_path.parent / f"{output_path.stem}_post{output_path.suffix}"
            if self._run_post_process(output_path, post_output, opts, aspect_ratio):
                # Replace original with post-processed
                output_path.unlink(missing_ok=True)
                shutil.move(str(post_output), str(output_path))
            else:
                logger.warning("Video merge: post-processing skipped or failed")
                if post_output.exists():
                    post_output.unlink(missing_ok=True)

        logger.info(
            "Video merge completed: %d clips -> %s (%s)",
            len(valid_paths),
            output_path.name,
            aspect_ratio,
        )
        return output_path.exists() and output_path.stat().st_size > 0

    def normalize_video_file_to_target_pixels(
        self,
        video_path: Path,
        target_width: int,
        target_height: int,
    ) -> bool:
        """Normalize a video to exact target pixel dimensions using scale + pad.

        Uses ``scale=force_original_aspect_ratio=decrease`` followed by
        ``pad`` with black bars to ensure every clip has identical dimensions,
        preventing visual jitter during concat playback.

        Mirrors ``videoService.normalizeVideoFileToTargetPixels``.

        Args:
            video_path: Path to the video file (modified in-place).
            target_width: Target width in pixels.
            target_height: Target height in pixels.

        Returns:
            ``True`` if normalization succeeded, ``False`` otherwise.
        """
        if not video_path.exists() or not target_width or not target_height:
            return False

        vf = (
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black"
        )
        tmp_out = video_path.with_suffix(
            f".norm-{uuid.uuid4().hex[:8]}{video_path.suffix or '.mp4'}"
        )

        base_args = [
            "-y", "-i", str(video_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        ]

        # First try with audio copy
        result = subprocess.run(
            [self.ffmpeg, *base_args, "-c:a", "copy", str(tmp_out)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            # Retry without audio
            result = subprocess.run(
                [self.ffmpeg, *base_args, "-an", str(tmp_out)],
                capture_output=True, text=True, timeout=300,
            )

        if result.returncode != 0:
            logger.warning(
                "Video normalize failed (keeping original): %s — %s",
                video_path.name,
                (result.stderr or "")[-500:],
            )
            if tmp_out.exists():
                tmp_out.unlink(missing_ok=True)
            return False

        try:
            video_path.unlink()
            shutil.move(str(tmp_out), str(video_path))
            logger.info(
                "Video normalized to %dx%d: %s",
                target_width, target_height, video_path.name,
            )
            return True
        except OSError as exc:
            logger.warning("Video normalize: replace failed: %s", exc)
            if tmp_out.exists():
                tmp_out.unlink(missing_ok=True)
            return False

    def probe_duration(self, video_path: Path) -> float | None:
        """Probe the duration of a video file in seconds using ffprobe."""
        if not video_path.exists():
            return None
        try:
            result = subprocess.run(
                [
                    self.ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                dur = float(result.stdout.strip())
                return dur if dur > 0 else None
        except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _normalize_or_keep(self, path: Path, w: int, h: int) -> Path:
        """Normalize a video, returning the path to the (possibly new) file."""
        try:
            if self.normalize_video_file_to_target_pixels(path, w, h):
                return path
        except Exception as exc:
            logger.warning("Video normalize error for %s: %s", path.name, exc)
        return path

    def _run_concat(self, video_paths: list[Path], output_path: Path) -> bool:
        """Run FFmpeg concat demuxer to join video files.

        Mirrors ``videoMergeService.runFfmpegConcat``.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        list_file = output_path.parent / f"concat_list_{uuid.uuid4().hex[:8]}.txt"

        try:
            lines = []
            for p in video_paths:
                normalized = str(p).replace("\\", "/")
                escaped = normalized.replace("'", "'\\''")
                lines.append(f"file '{escaped}'")
            list_file.write_text("\n".join(lines), encoding="utf-8")

            cmd = [
                self.ffmpeg,
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                "-y",
                str(output_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.warning("FFmpeg concat failed: %s", (result.stderr or "")[-500:])

                # Fallback: re-encode instead of stream copy
                logger.info("Retrying concat with re-encode...")
                cmd_reencode = [
                    self.ffmpeg,
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(list_file),
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-pix_fmt", "yuv420p",
                    "-y",
                    str(output_path),
                ]
                result = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=600)
                if result.returncode != 0:
                    logger.warning("FFmpeg concat re-encode also failed: %s", (result.stderr or "")[-500:])
                    return False

            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            logger.warning("FFmpeg concat error: %s", exc)
            return False
        finally:
            if list_file.exists():
                list_file.unlink(missing_ok=True)

    def _run_post_process(
        self,
        input_path: Path,
        output_path: Path,
        opts: dict,
        aspect_ratio: str,
    ) -> bool:
        """Apply post-processing: subtitles, audio overlay, watermark.

        Mirrors ``mergedEpisodePostProcess.runMergedEpisodePostProcess``.
        """
        cmd: list[str] = [self.ffmpeg, "-y", "-i", str(input_path)]

        # Audio input
        audio_path = opts.get("audio_path")
        has_audio = audio_path and Path(audio_path).exists()
        if has_audio:
            cmd += ["-i", str(audio_path)]

        # Subtitle input (via filter)
        burn_subs = opts.get("burn_subtitles")
        subtitle_path = opts.get("subtitle_path")
        has_subs = burn_subs and subtitle_path and Path(subtitle_path).exists()

        # Build video filter chain
        vf_parts: list[str] = []

        # Scale to target aspect ratio
        target_w, target_h = aspect_ratio_to_pixels(aspect_ratio)
        vf_parts.append(
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
        )
        vf_parts.append(f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2")

        # Subtitle burning (via subtitles filter)
        if has_subs:
            sub_path = str(subtitle_path).replace("\\", "/").replace(":", r"\:")
            vf_parts.append(f"subtitles='{sub_path}'")

        # Watermark
        watermark_text = str(opts.get("watermark_text", "")).strip()
        if watermark_text:
            pos = opts.get("watermark_position", "bottom_right")
            pos_map = {
                "bottom_right": "x=w-tw-30:y=h-th-30",
                "top_right": "x=w-tw-30:y=30",
                "bottom_left": "x=30:y=h-th-30",
                "top_left": "x=30:y=30",
            }
            pos_expr = pos_map.get(pos, pos_map["bottom_right"])
            escaped_wm = watermark_text.replace("'", "\\'").replace(":", r"\:")
            vf_parts.append(
                f"drawtext=text='{escaped_wm}':"
                f"fontcolor=white@0.7:fontsize=28:"
                f"{pos_expr}:"
                f"box=1:boxcolor=black@0.3:boxborderw=6"
            )

        vf_parts.append("format=yuv420p")
        cmd += ["-vf", ",".join(vf_parts)]

        # Audio mixing
        if has_audio:
            audio_vol = opts.get("audio_volume", 1.0)
            cmd += [
                "-filter_complex",
                f"[1:a]volume={audio_vol}[aud];[0:a][aud]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium",
                "-crf", str(opts.get("crf", 23)),
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
            ]
        else:
            cmd += [
                "-c:v", "libx264", "-preset", "medium",
                "-crf", str(opts.get("crf", 23)),
                "-c:a", "aac", "-b:a", "128k",
            ]

        cmd += ["-movflags", "+faststart", str(output_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.warning("Post-process failed: %s", (result.stderr or "")[-500:])
                return False
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            logger.warning("Post-process error: %s", exc)
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience: list all angle combinations
# ═══════════════════════════════════════════════════════════════════════════════


def list_all_angles() -> list[dict[str, str]]:
    """List all 96 angle combinations (8 horizontal x 4 vertical x 3 shot size).

    Mirrors ``angleService.listAllAngles``. Each entry contains ``h``, ``v``,
    ``s``, ``label`` (Chinese), and ``prompt_fragment`` (English).
    """
    result: list[dict[str, str]] = []
    for h_key in HORIZONTAL_ANGLES:
        for v_key in VERTICAL_ANGLES:
            for s_key in ("close_up", "medium", "wide"):
                result.append({
                    "h": h_key,
                    "v": v_key,
                    "s": s_key,
                    "label": angle_to_chinese_label(h_key, v_key, s_key),
                    "prompt_fragment": angle_to_english_fragment(h_key, v_key, s_key),
                })
    return result


def to_cinematic_fragment(
    h: str | None = None,
    v: str | None = None,
    s: str | None = None,
    movement: str | None = None,
    lighting: str | None = None,
    dof: str | None = None,
) -> str:
    """Build a complete cinematic parameter description string.

    Combines angle fragment + movement + lighting + depth of field into a
    single comma-separated English prompt fragment.

    Mirrors ``angleService.toCinematicFragment``.
    """
    parts = [angle_to_english_fragment(h, v, s)]

    if movement and movement in CAMERA_MOVEMENTS:
        parts.append(CAMERA_MOVEMENTS[movement][1])

    if lighting and lighting in LIGHTING_STYLES:
        parts.append(LIGHTING_STYLES[lighting][1])

    if dof and dof in DEPTH_OF_FIELD:
        parts.append(DEPTH_OF_FIELD[dof][1])

    return ", ".join(parts)
