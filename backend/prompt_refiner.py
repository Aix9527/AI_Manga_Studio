"""
V3.0 Layer 6 — Decomposed Prompt Engine

Decomposes prompts into six independent components:
  - Character: FIXED from CharacterDNA (never changes)
  - Scene: FIXED from SceneDNA + StyleDNA
  - Action: DYNAMIC from Beat.action
  - Camera: DYNAMIC from Shot.camera
  - Emotion: DYNAMIC from StoryGraph.emotion_curve / Beat.emotion
  - Lighting: FIXED from StyleDNA

Components are merged at the last step before ComfyUI submission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def refine_shot_prompts(shot: Any) -> Optional[Dict[str, str]]:
    """Build decomposed prompts from a shot and return positive/negative.

    Uses DecomposedPrompt to merge the six components (character, scene,
    action, camera, emotion, lighting) from shot data into the final
    ComfyUI-ready prompt strings.

    Args:
        shot: UnifiedShot object with merged_prompt, narration, camera, emotion, etc.

    Returns:
        Dict with 'positive_prompt' and 'negative_prompt', or None if
        the positive prompt would be empty (caller should fall back).
    """
    dp = DecomposedPrompt()

    # shot_id
    sid = getattr(shot, "shot_id", "") or ""
    if not sid:
        ch = getattr(shot, "chapter", 1)
        sc = getattr(shot, "scene", 1)
        sh = getattr(shot, "shot", 1)
        sid = f"ch{ch:02d}_sc{sc:02d}_sh{sh:03d}"
    dp.shot_id = sid

    # Dynamic components from shot
    dp.action_prompt = (
        getattr(shot, "merged_prompt", "")
        or getattr(shot, "narration", "")
        or getattr(shot, "positive", "")
        or ""
    )
    dp.camera_prompt = (
        getattr(shot, "camera", "")
        or getattr(shot, "camera_angle", "")
        or ""
    )
    dp.emotion_prompt = getattr(shot, "emotion", "") or "neutral"

    # Fixed-style hints from shot metadata
    dp.style_prompt = "masterpiece, best quality, anime style"
    dp.lighting_prompt = getattr(shot, "lighting", "") or ""
    dp.negative_prompt = (
        getattr(shot, "negative", "")
        or getattr(shot, "negative_prompt", "")
        or ""
    )

    positive = dp.merge()
    if not positive.strip():
        return None

    return {"positive_prompt": positive, "negative_prompt": dp.merge_negative()}

# ── Data class ────────────────────────────────────────────────


@dataclass
class DecomposedPrompt:
    """Six independent prompt components.

    Fixed components come from DNA (Character/Scene/Style).
    Dynamic components come from Beat/Shot/StoryGraph.
    """

    shot_id: str = ""

    # Fixed components (from DNA)
    character_prompt: str = ""    # From CharacterDNA.get_prompt_context()
    scene_prompt: str = ""        # From SceneDNAManager.get_scene_prompt() + StyleDNA
    lighting_prompt: str = ""     # From StyleDNA.lighting + color_grading

    # Dynamic components (from narrative)
    action_prompt: str = ""       # From Beat.action description
    camera_prompt: str = ""       # From Shot.camera + Shot.angle
    emotion_prompt: str = ""      # From StoryGraph emotion_curve / Beat.emotion

    # Style prompt (from StyleDNA) — global, injected into every prompt
    style_prompt: str = ""

    # Negative (merged from all sources)
    negative_prompt: str = ""

    # Additional injection strings
    lora_injections: List[str] = None  # list of LoRA tags like "<lora:name:0.85>"

    def __post_init__(self):
        if self.lora_injections is None:
            self.lora_injections = []

    def merge(self) -> str:
        """Merge all components into a complete positive prompt.

        Order matters: style → character → scene → emotion → action → camera → LoRA.

        Returns:
            Complete prompt string ready for ComfyUI.
        """
        parts: List[str] = []

        # 1. Style DNA (global quality tags)
        if self.style_prompt:
            parts.append(self.style_prompt)

        # 2. Character (fixed appearance)
        if self.character_prompt:
            parts.append(self.character_prompt)

        # 3. Scene (environment)
        if self.scene_prompt:
            parts.append(f"in {self.scene_prompt}")

        # 4. Emotion (mood/atmosphere)
        if self.emotion_prompt:
            parts.append(f"{self.emotion_prompt} atmosphere")

        # 5. Action (what's happening)
        if self.action_prompt:
            parts.append(self.action_prompt)

        # 6. Camera (shot composition)
        if self.camera_prompt:
            parts.append(self.camera_prompt)

        # 7. Lighting (from StyleDNA)
        if self.lighting_prompt:
            parts.append(f"{self.lighting_prompt} lighting")

        # 8. LoRA injections
        if self.lora_injections:
            parts.extend(self.lora_injections)

        return ", ".join(parts)

    def merge_negative(self) -> str:
        """Return the merged negative prompt."""
        return self.negative_prompt or "lowres, bad quality, blurry"
