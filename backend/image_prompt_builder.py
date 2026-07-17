"""
AI Manga Studio V3.5 — Image Prompt Builder

Constructs structured Flux-compatible image prompts.
Source: sora工作室爆量(3).txt

Key rules:
- Character focus priority (角色焦点优先)
- Scene as environmental backdrop (场景作为环境衬托)
- Do NOT describe clothing — use character name
- Use Character DNA mapping (e.g., @zdh202301.xxx format)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.banned_words import contains_banned, filter_banned

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────

@dataclass
class ImagePrompt:
    """Structured Flux image prompt."""
    shot_id: str = ""

    subject_focus: str = ""          # Character focus description
    scene_context: str = ""           # Scene environment (as backdrop)
    camera_spec: str = ""             # Camera framing: 半身/全身/近景/中景/特写
    composition: str = ""             # Composition: 正面/侧面/俯视/仰视
    style_tags: str = ""              # Style tags
    negative_prompt: str = ""         # Negative prompt
    full_prompt: str = ""             # Synthesized complete prompt text

    # Character DNA mapping
    character_mappings: Dict[str, str] = field(default_factory=dict)

    # Banned word check
    has_banned_words: bool = False
    filtered_content: List[str] = field(default_factory=list)


# ── Engine ────────────────────────────────────────────────────

class ImagePromptBuilder:
    """Builds Flux-compatible image prompts from structured shot data.

    Follows the core rule from the original prompt:
    1. Character focus first
    2. Scene as backdrop (lower weight)
    3. Camera specification
    4. Composition
    5. Style tags
    6. Negative prompt
    """

    # Default style tags
    DEFAULT_STYLE_TAGS: str = (
        "动漫风格，高细节，精美插画，电影级光影，"
        "色彩鲜明，线条清晰，最佳品质"
    )

    # Default negative prompt
    DEFAULT_NEGATIVE: str = (
        "低质量，模糊，变形，丑陋，多余的肢体，"
        "水印，文字，签名，裁剪不当，比例失调"
    )

    def __init__(self) -> None:
        logger.info("ImagePromptBuilder initialized (V3.5)")

    # ── Public API ────────────────────────────────────────

    def build(
        self,
        shot_data: Dict[str, Any],
        character_dna: Optional[Dict[str, Any]] = None,
        scene_dna: Optional[Dict[str, Any]] = None,
        quality_threshold: float = 0.7,
    ) -> ImagePrompt:
        """Build a structured Flux image prompt.

        Args:
            shot_data: Shot data with at minimum: shot_id, character_action, scene_desc.
            character_dna: Character DNA for mapping (used for @zdh style references).
            scene_dna: Scene DNA for environment context.
            quality_threshold: Minimum quality score to pass.

        Returns:
            ImagePrompt with structured fields.
        """
        prompt = ImagePrompt(shot_id=shot_data.get("shot_id", ""))

        shot_type = shot_data.get("camera_angle", "中景")

        # Build subject focus (character-centric)
        prompt.subject_focus = self._build_subject_focus(shot_data, character_dna)

        # Build scene context (as backdrop)
        prompt.scene_context = self._build_scene_context(shot_data, scene_dna)

        # Camera specification
        prompt.camera_spec = self._build_camera_spec(shot_type)

        # Composition
        prompt.composition = self._build_composition(shot_data)

        # Style tags
        prompt.style_tags = self._build_style_tags(character_dna)

        # Negative prompt
        prompt.negative_prompt = self.DEFAULT_NEGATIVE

        # Build character mappings
        prompt.character_mappings = self._build_character_mappings(character_dna)

        # Synthesize full prompt
        prompt.full_prompt = self._synthesize_full(prompt)

        # Banned word check
        prompt.has_banned_words, prompt.filtered_content = (
            self._check_banned(prompt.full_prompt)
        )

        if prompt.has_banned_words:
            prompt.full_prompt = filter_banned(prompt.full_prompt)
            logger.warning(
                f"ImagePromptBuilder: filtered banned words in shot {prompt.shot_id}: "
                f"{prompt.filtered_content}"
            )

        logger.debug(
            f"ImagePromptBuilder: built prompt for shot {prompt.shot_id}, "
            f"length={len(prompt.full_prompt)}"
        )
        return prompt

    def build_batch(
        self,
        shots: List[Dict[str, Any]],
        character_dna: Optional[Dict[str, Any]] = None,
        scene_dna: Optional[Dict[str, Any]] = None,
    ) -> List[ImagePrompt]:
        """Build image prompts for a batch of shots."""
        prompts: List[ImagePrompt] = []

        for shot in shots:
            prompt = self.build(
                shot_data=shot,
                character_dna=character_dna,
                scene_dna=scene_dna,
            )
            prompts.append(prompt)

        logger.info(f"ImagePromptBuilder: built {len(prompts)} image prompts")
        return prompts

    # ── Internal builders ─────────────────────────────────

    def _build_subject_focus(
        self,
        shot_data: Dict[str, Any],
        character_dna: Optional[Dict[str, Any]],
    ) -> str:
        """Build character-centric subject focus description.

        Rule: Do NOT describe clothing — use character name only.
        """
        action = shot_data.get("character_action", "")
        dialogue = shot_data.get("dialogue", "")

        # Get character mapping if available
        char_ref = ""
        if character_dna:
            char_name = character_dna.get("name", "")
            char_mapping = character_dna.get("mapping_id", "")
            if char_mapping:
                char_ref = f"{char_mapping} "
            elif char_name:
                char_ref = f"{char_name}，"

        focus = f"角色焦点优先：{char_ref}{action}"
        if dialogue:
            focus += f"，对话状态"

        return focus

    def _build_scene_context(
        self,
        shot_data: Dict[str, Any],
        scene_dna: Optional[Dict[str, Any]],
    ) -> str:
        """Build scene environment as backdrop (lower weight)."""
        scene_desc = shot_data.get("scene_desc", "")

        context = f"场景作为环境衬托：{scene_desc}"

        if scene_dna:
            atmosphere = scene_dna.get("atmosphere", "")
            time_of_day = scene_dna.get("time_of_day", "")
            if atmosphere:
                context += f"，{atmosphere}氛围"
            if time_of_day and time_of_day != "未指定":
                context += f"，{time_of_day}"

        return context

    def _build_camera_spec(self, shot_type: str) -> str:
        """Build camera specification."""
        spec_map = {
            "特写": "镜头特写，焦点强化于面部/手部细节",
            "大特写": "极端特写镜头，焦点集中于微观细节",
            "近景": "近景景别，焦点强化于上半身动作",
            "中景": "中景景别，焦点强化于角色互动",
            "全景": "全景景别，角色在环境中完整呈现",
            "双人中景": "双人中景，两人互动，焦点在关系动态",
        }
        return spec_map.get(shot_type, f"镜头景别：{shot_type}")

    def _build_composition(self, shot_data: Dict[str, Any]) -> str:
        """Build composition description."""
        camera_angle = shot_data.get("camera_angle", "中景")
        if "俯" in camera_angle:
            return "俯视构图"
        if "仰" in camera_angle:
            return "仰视构图"
        return "正面构图"

    def _build_style_tags(
        self,
        character_dna: Optional[Dict[str, Any]],
    ) -> str:
        """Build style tags, incorporating character DNA quality tags."""
        tags = self.DEFAULT_STYLE_TAGS

        if character_dna:
            quality_tags = character_dna.get("quality_tags", [])
            if quality_tags:
                tags += "，" + "，".join(quality_tags)

        return tags

    def _build_character_mappings(
        self,
        character_dna: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        """Build character → mapping ID dictionary for @zdh references."""
        if not character_dna:
            return {}

        mappings: Dict[str, str] = {}
        char_name = character_dna.get("name", "")
        mapping_id = character_dna.get("mapping_id", "")

        if char_name and mapping_id:
            mappings[char_name] = mapping_id

        return mappings

    def _synthesize_full(self, prompt: ImagePrompt) -> str:
        """Combine all fields into a single Flux prompt string."""
        parts: List[str] = []

        if prompt.subject_focus:
            parts.append(prompt.subject_focus)
        if prompt.scene_context:
            parts.append(prompt.scene_context)
        if prompt.camera_spec:
            parts.append(prompt.camera_spec)
        if prompt.composition:
            parts.append(prompt.composition)
        if prompt.style_tags:
            parts.append(prompt.style_tags)

        positive = "，".join(parts)
        full = f"{positive}"

        if prompt.negative_prompt:
            full += f"\nNegative prompt: {prompt.negative_prompt}"

        return full

    def _check_banned(self, text: str) -> tuple:
        """Check for banned words and return (has_banned, filtered_list)."""
        if not text:
            return False, []

        from backend.banned_words import list_banned_found
        found = list_banned_found(text)
        return len(found) > 0, found
