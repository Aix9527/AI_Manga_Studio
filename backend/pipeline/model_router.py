"""
V3.0 Layer 7 — Model Router

Automatically selects the best model for each pipeline stage
based on shot/scene context, character count, and action intensity.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


# ── Route Tables ─────────────────────────────────────────────

MODEL_ROUTES = {
    "character": "Flux Kontext",       # Character generation (best face/anatomy)
    "background": "Flux Dev",          # Background generation (fast, quality)
    "gufeng": "NoobAI XL",             # Ancient Chinese / gufeng scenes
    "modern": "SDXL",                  # Modern scenes
    "restoration": "SUPIR",            # Super-resolution
    "face_restore": "CodeFormer",      # Face restoration
    "video_dialogue": "Wan2.2",        # Dialogue / static shots
    "video_battle": "Hunyuan",         # Action / battle scenes
    "video_scenery": "LTX",            # Landscape / drone / panning
}

# Model to port mapping for multi-GPU deployment
MODEL_PORTS: Dict[str, int] = {
    "Flux Kontext": 8188,
    "Flux Dev": 8188,
    "SDXL": 8188,
    "NoobAI XL": 8188,
    "Wan2.2": 8189,
    "Hunyuan": 8189,
    "LTX": 8189,
    "SUPIR": 8190,
    "CodeFormer": 8190,
    "MuseTalk": 8191,
    "CosyVoice": 8191,
}

# Scene type detection keywords
_SCENE_GUFENG_KEYWORDS = [
    "古", "仙", "侠", "武侠", "宫廷", "江湖", "剑", "道", "魔",
    "修仙", "修真", "古代", "古城", "古装", "汉服", "宫殿",
]

_SCENE_MODERN_KEYWORDS = [
    "现代", "都市", "公司", "学校", "医院", "机场", "地铁", "商场",
    "办公室", "公寓", "街道", "咖啡", "餐厅",
]


class ModelRouter:
    """Automatic model selection for image and video generation.

    Usage:
        router = ModelRouter()
        model = router.route_image(shot, scene_context, character_count)
        video_model = router.route_video(shot, beat)
    """

    @staticmethod
    def route_image(
        shot: Any,
        scene_context: Any,
        character_count: int = 1,
    ) -> str:
        """Select the best image generation model.

        Decision tree:
          1. Is this a character close-up? → Flux Kontext
          2. Is this a background-only shot? → Flux Dev
          3. Is the scene "gufeng" themed? → NoobAI XL
          4. Modern scene? → SDXL
          5. Default → Flux Dev

        Returns:
            Model name string (e.g., "Flux Kontext").
        """
        # Character close-up detection
        if character_count >= 1 and ModelRouter._is_close_up(shot):
            return "Flux Kontext"

        # Background-only shot
        if character_count == 0:
            return "Flux Dev"

        # Scene theme detection
        scene_text = ""
        if scene_context:
            if hasattr(scene_context, "location"):
                scene_text = scene_context.location
            elif isinstance(scene_context, dict):
                scene_text = scene_context.get("location", "")

        if ModelRouter._is_gufeng(scene_text):
            return "NoobAI XL"

        if ModelRouter._is_modern(scene_text):
            return "SDXL"

        # Default: Flux Dev (best general-purpose)
        return "Flux Dev"

    @staticmethod
    def route_video(shot: Any, beat: Any) -> str:
        """Select the best video generation model.

        Decision tree:
          1. High action intensity → Hunyuan
          2. Scenic / slow panning → LTX
          3. Dialogue / static → Wan2.2

        Returns:
            Model name string.
        """
        # Action intensity detection
        action_text = ModelRouter._get_action_text(shot, beat)
        intensity = ModelRouter._action_intensity(action_text)

        if intensity >= 0.7:
            return "Hunyuan"

        if intensity <= 0.2:
            return "LTX"

        return "Wan2.2"

    @staticmethod
    def route_restore(image_type: str = "") -> str:
        """Select the best restoration model.

        Args:
            image_type: "face" | "general"

        Returns:
            Model name string.
        """
        return "CodeFormer" if image_type == "face" else "SUPIR"

    @staticmethod
    def get_port(model: str) -> int:
        """Get the ComfyUI port for a given model."""
        return MODEL_PORTS.get(model, 8188)

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _is_close_up(shot: Any) -> bool:
        """Detect if shot is a character close-up from camera field."""
        if not shot:
            return False
        camera = getattr(shot, "camera", "") if hasattr(shot, "camera") else ""
        return any(kw in str(camera).lower() for kw in ["close-up", "closeup", "特写", "近景"])

    @staticmethod
    def _is_gufeng(text: str) -> bool:
        """Detect ancient Chinese / gufeng theme."""
        t = text.lower()
        return any(kw in t for kw in _SCENE_GUFENG_KEYWORDS)

    @staticmethod
    def _is_modern(text: str) -> bool:
        """Detect modern theme."""
        t = text.lower()
        return any(kw in t for kw in _SCENE_MODERN_KEYWORDS)

    @staticmethod
    def _get_action_text(shot: Any, beat: Any) -> str:
        """Extract action description text from shot/beat."""
        parts = []
        if beat:
            if hasattr(beat, "description"):
                parts.append(str(beat.description))
            elif isinstance(beat, dict):
                parts.append(str(beat.get("description", "")))
        if shot:
            if hasattr(shot, "action"):
                parts.append(str(shot.action))
            elif isinstance(shot, dict):
                parts.append(str(shot.get("action", "")))
        return " ".join(parts).lower()

    @staticmethod
    def _action_intensity(text: str) -> float:
        """Estimate action intensity from text keywords.

        Returns:
            Float 0.0 (static) ~ 1.0 (intense battle).
        """
        high_keywords = [
            "fight", "battle", "attack", "explosion", "chase", "run", "jump",
            "打斗", "战斗", "攻击", "爆炸", "追击", "奔跑", "跳跃",
            "碰撞", "厮杀", "挥剑", "出拳", "飞踢",
        ]
        medium_keywords = [
            "walk", "turn", "sit", "stand", "move", "gesture",
            "行走", "转身", "坐下", "站起", "移动", "手势",
        ]

        high_count = sum(1 for kw in high_keywords if kw in text)
        medium_count = sum(1 for kw in medium_keywords if kw in text)

        if high_count >= 2:
            return 0.9
        if high_count == 1:
            return 0.7
        if medium_count >= 2:
            return 0.4
        if medium_count == 1:
            return 0.2
        return 0.0
