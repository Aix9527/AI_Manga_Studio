"""
AI Manga Studio Pro V4 鈥?Enhanced Image Prompt Builder

Fixes the "too messy" image generation problem by:
1. Strict composition directives (prevents body fragmentation)
2. Character-first anchoring (consistent character across shots)
3. Scene-as-backdrop weighting (environment doesn't compete with subject)
4. Professional lighting hierarchy (key/fill/rim light structure)
5. Style lock system (consistent visual style across all shots)
6. Negative prompt hardening (blocks common failure modes)
7. Shot-table integration (professional cinematography structure)

All prompts are built from structured shot data 鈥?no LLM randomness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ============================================================
# Constants
# ============================================================

# Hardened negative prompt 鈥?blocks ALL common failure modes
NEGATIVE_PROMPT_HARDENED = (
    "worst quality, low quality, blurry, jpeg artifacts, compression artifacts, "
    "deformed, distorted, disfigured, bad anatomy, extra limbs, missing limbs, "
    "fused fingers, too many fingers, long neck, extra arms, extra legs, "
    "ugly, duplicate, morbid, mutilated, poorly drawn face, mutation, blurry, "
    "watermark, text, logo, signature, banner, "
    "cropped, out of frame, cut off, partial view, "
    "wrong size, wrong scale, inconsistent proportions, "
    "multiple characters in one frame, overlapping bodies, "
    "floating limbs, disconnected hands, mismatched clothing, "
    "bad hands, missing fingers, extra digits, deformed fingers, "
    "asymmetric eyes, crossed eyes, mismatched pupils, "
    "flat lighting, overexposed, underexposed, harsh shadows, "
    "cartoonish, 3d render, plastic skin, doll-like, "
    "noise, grain, banding, artifacts, pixelation"
)

# Style lock presets
STYLE_LOCKS: Dict[str, str] = {
    "anime": "anime style, cel shading, vibrant colors, clean lineart, "
             "high detail, masterpiece, best quality, 8K resolution",
    "cinematic": "cinematic film still, anamorphic lens, color graded, "
                 "film grain, dramatic lighting, 8K, photorealistic",
    "realistic": "photorealistic, detailed skin texture, subsurface scattering, "
                 "natural lighting, 8K, professional photography",
    "manga": "manga style, black and white, screentone, crosshatching, "
             "high contrast, ink lines, dramatic shadows",
    "semi_realistic": "semi-realistic, detailed rendering, soft shading, "
                      "anime-inspired realism, 8K",
}


# ============================================================
# Data Models
# ============================================================

@dataclass
class ImagePromptResult:
    """Complete image prompt result with all fields."""
    shot_id: str = ""
    
    # Positive prompt components
    composition_anchor: str = ""    # Prevents body fragmentation
    character_anchor: str = ""      # Character-first description
    scene_backdrop: str = ""        # Scene as environment (lower weight)
    lighting_setup: str = ""        # Key/fill/rim light structure
    camera_specs: str = ""          # Lens, aperture, angle
    emotion_mood: str = ""          # Emotional atmosphere
    style_lock: str = ""            # Global style tag
    
    # Full prompts
    positive_prompt: str = ""
    negative_prompt: str = ""
    
    # Quality assurance
    quality_score: float = 1.0      # 0-1, self-assessed
    has_issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "positive_prompt": self.positive_prompt,
            "negative_prompt": self.negative_prompt,
            "composition_anchor": self.composition_anchor,
            "character_anchor": self.character_anchor,
            "scene_backdrop": self.scene_backdrop,
            "lighting_setup": self.lighting_setup,
            "camera_specs": self.camera_specs,
            "emotion_mood": self.emotion_mood,
            "quality_score": self.quality_score,
            "issues": self.has_issues,
        }


# ============================================================
# Enhanced Image Prompt Builder
# ============================================================

class EnhancedImagePromptBuilder:
    """Builds consistent, high-quality image prompts.
    
    Architecture:
      1. Composition Anchor 鈫?prevents body fragmentation
      2. Character Anchor 鈫?locks character appearance
      3. Scene Backdrop 鈫?environment as supporting element
      4. Lighting Setup 鈫?professional 3-point lighting
      5. Camera Specs 鈫?lens/aperture/angle
      6. Emotion/Mood 鈫?atmospheric direction
      7. Style Lock 鈫?global visual consistency
    """

    # Shot type 鈫?composition directive (prevents fragmentation)
    COMPOSITION_DIRECTIVES: Dict[str, str] = {
        "close": "single person, close-up portrait, one complete face, head and shoulders centered, "
                 "no duplicates, no fragmented body parts, clean composition",
        "medium": "single person, waist-up portrait, one complete upper body, centered standing, "
                  "solo, no overlapping figures, no body fragments",
        "wide": "single person, full body shot, one complete figure standing centered, "
                "solo, clean simple composition, no duplicates, no fragmented limbs",
        "drone": "single person, aerial top-down view, one complete figure centered, "
                 "solo, no duplicates, clear spatial arrangement",
        "pov": "single person, first-person perspective, one complete figure centered, "
               "solo, no overlapping, immersive viewpoint",
        "tracking": "single person, dynamic action pose, one complete figure, "
                    "solo, centered motion, no fragments",
        "dutch": "single person, dramatic tilted angle, one complete figure, "
                 "solo, centered composition, no duplicates",
        "overhead": "single person, bird's-eye view, one complete figure centered, "
                    "solo, no overlapping bodies",
    }

    # Shot type 鈫?camera specification
    CAMERA_SPECS: Dict[str, str] = {
        "close": "85mm portrait lens, f/1.8, shallow depth of field, bokeh background",
        "medium": "50mm standard lens, f/2.8, moderate depth of field",
        "wide": "24mm wide lens, f/8, deep depth of field, environmental context",
        "drone": "16mm ultra-wide drone lens, f/11, maximum depth of field",
        "pov": "24mm wide-angle lens, f/2.0, slight barrel distortion for immersion",
        "tracking": "35mm lens, f/4, medium depth of field, motion blur potential",
        "dutch": "35mm lens, f/2.8, tilted 15 degrees, dramatic tension",
        "overhead": "50mm lens, f/5.6, top-down flat composition",
    }

    # Lighting setups by time of day
    LIGHTING_SETUPS: Dict[str, str] = {
        "dawn": "soft pink morning light as key, cool blue fill from opposite side, "
                "warm rim light on subject edges, volumetric god rays through mist",
        "morning": "bright directional sunlight as key from upper-left, "
                   "soft fill from ground bounce, crisp defined shadows",
        "noon": "harsh overhead sun as key, minimal fill, strong downward shadows, "
                "high contrast lighting",
        "afternoon": "warm golden angle light as key from side, "
                     "soft amber fill, long directional shadows, golden tint",
        "dusk": "orange-pink horizon as key light, deep blue fill from sky, "
                "strong cinematic rim light on subjects, dramatic color contrast",
        "night": "moonlight blue wash as key, warm practical light as fill, "
                 "deep shadow pools, soft rim from distant street lamp",
        "rainy": "diffused gray overcast as key, no direct shadows, "
                 "wet surface reflections, droplet highlights",
        "sunny": "bright clear sunlight as key, blue sky fill, "
                 "sharp defined shadows, saturated colors",
        "foggy": "soft diffused backlight as key, low contrast, "
                 "ethereal glow, desaturated midtones",
        "stormy": "dark dramatic overhead as key, lightning flash accents, "
                  "heavy shadow, turbulent atmosphere",
    }

    # Emotion 鈫?mood/atmosphere description
    EMOTION_MOODS: Dict[str, str] = {
        "angry": "tense atmosphere, high contrast shadows, aggressive composition, "
                 "sharp angular lighting",
        "sad": "melancholic mood, soft diffused light, desaturated tones, "
               "downward composition",
        "happy": "warm uplifting atmosphere, bright even lighting, "
                 "open composition, golden tones",
        "fearful": "ominous mood, deep shadows, cold color temperature, "
                   "claustrophobic framing",
        "surprised": "dramatic spotlight effect, high contrast, "
                    "centralized focus, sudden light shift",
        "tense": "chiaroscuro lighting, high contrast, "
                 "unbalanced composition, deep shadows",
        "determined": "strong directional light, confident centered composition, "
                     "sharp focus, clean lines",
        "calm": "soft even lighting, balanced composition, "
               "warm neutral tones, gentle atmosphere",
        "excited": "dynamic lighting with highlights, energetic composition, "
                   "vibrant colors, sense of motion",
        "neutral": "even balanced lighting, centered composition, "
                   "natural color temperature, clean look",
    }

    def __init__(self, style: str = "anime", style_lock_override: str = ""):
        self.default_style = style
        self.style_lock = style_lock_override or STYLE_LOCKS.get(style, STYLE_LOCKS["anime"])
        logger.info(f"EnhancedImagePromptBuilder initialized (style={style})")

    def build(self, shot_data: Dict[str, Any]) -> ImagePromptResult:
        """Build a complete image prompt from shot data.
        
        Args:
            shot_data: Dict with keys: shot_id, characters, background, 
                      emotion, camera, time_of_day, weather, action, etc.
        
        Returns:
            ImagePromptResult with positive and negative prompts.
        """
        result = ImagePromptResult(shot_id=shot_data.get("shot_id", ""))
        
        # 1. Composition anchor
        shot_type = shot_data.get("camera", "medium").lower()
        result.composition_anchor = self.COMPOSITION_DIRECTIVES.get(
            shot_type, self.COMPOSITION_DIRECTIVES["medium"]
        )
        
        # 2. Character anchor
        result.character_anchor = self._build_character_anchor(shot_data)
        
        # 3. Scene backdrop
        result.scene_backdrop = self._build_scene_backdrop(shot_data)
        
        # 4. Lighting setup
        result.lighting_setup = self._build_lighting(shot_data)
        
        # 5. Camera specs
        result.camera_specs = self.CAMERA_SPECS.get(shot_type, self.CAMERA_SPECS["medium"])
        
        # 6. Emotion/mood
        result.emotion_mood = self.EMOTION_MOODS.get(
            shot_data.get("emotion", "neutral"), self.EMOTION_MOODS["neutral"]
        )
        
        # 7. Style lock
        result.style_lock = self.style_lock
        
        # Assemble positive prompt
        result.positive_prompt = self._assemble_positive(result)
        
        # Assemble negative prompt
        result.negative_prompt = NEGATIVE_PROMPT_HARDENED
        
        # Quality check
        result.quality_score = self._assess_quality(result)
        result.has_issues = self._find_issues(result)
        
        return result

    def build_batch(self, shots: List[Dict[str, Any]]) -> List[ImagePromptResult]:
        """Build prompts for a batch of shots."""
        results = []
        for shot in shots:
            results.append(self.build(shot))
        logger.info(f"EnhancedImagePromptBuilder: built {len(results)} prompts")
        return results

    def _build_character_anchor(self, shot_data: Dict[str, Any]) -> str:
        """Build character-first anchor description."""
        characters = shot_data.get("characters", [])
        action = shot_data.get("action", "")
        expression = shot_data.get("expression", "")
        
        parts = []
        
        # Character names (must be explicit for consistency)
        if characters:
            parts.append("featuring " + " and ".join(characters))
        
        # Action description
        if action:
            parts.append(action)
        
        # Expression
        if expression:
            parts.append(f"expression: {expression}")
        
        # Body language cues
        body_cues = shot_data.get("body_language", "")
        if body_cues:
            parts.append(body_cues)
        
        return "; ".join(parts) if parts else "character subject"

    def _build_scene_backdrop(self, shot_data: Dict[str, Any]) -> str:
        """Build scene as environment backdrop (lower weight)."""
        scene = shot_data.get("background", "")
        weather = shot_data.get("weather", "")
        
        parts = []
        
        if scene:
            parts.append(f"{scene} as environmental backdrop")
        
        if weather:
            parts.append(f"{weather} atmospheric conditions")
        
        # Explicit backdrop marker
        if parts:
            return ", ".join(parts) + ", scene as supporting background element"
        
        return "simple environmental backdrop"

    def _build_lighting(self, shot_data: Dict[str, Any]) -> str:
        """Build professional lighting setup."""
        time_of_day = shot_data.get("time_of_day", "").lower()
        weather = shot_data.get("weather", "").lower()
        custom_lighting = shot_data.get("lighting", "")
        
        if custom_lighting:
            return custom_lighting
        
        # Check weather first
        for key in self.LIGHTING_SETUPS:
            if key in weather:
                return self.LIGHTING_SETUPS[key]
        
        # Fall back to time of day
        for key in self.LIGHTING_SETUPS:
            if key in time_of_day:
                return self.LIGHTING_SETUPS[key]
        
        return LIGHTING_SETUPS.get("sunny", LIGHTING_SETUPS["morning"])

    def _assemble_positive(self, result: ImagePromptResult) -> str:
        """Assemble the final positive prompt from all components."""
        parts = [
            result.composition_anchor,
            result.character_anchor,
            result.scene_backdrop,
            result.lighting_setup,
            result.camera_specs,
            result.emotion_mood,
            result.style_lock,
        ]
        return ", ".join(p for p in parts if p)

    def _assess_quality(self, result: ImagePromptResult) -> float:
        """Self-assess prompt quality (0-1)."""
        score = 1.0
        
        # Penalize empty critical fields
        if not result.character_anchor:
            score -= 0.3
        if not result.composition_anchor:
            score -= 0.2
        if not result.lighting_setup:
            score -= 0.1
        
        # Penalize very short prompts
        if len(result.positive_prompt) < 50:
            score -= 0.2
        
        return max(0.0, round(score, 2))

    def _find_issues(self, result: ImagePromptResult) -> List[str]:
        """Find potential issues with the prompt."""
        issues = []
        
        if result.quality_score < 0.7:
            issues.append("LOW_QUALITY_SCORE")
        if not result.character_anchor:
            issues.append("MISSING_CHARACTER_ANCHOR")
        if len(result.positive_prompt) < 100:
            issues.append("PROMPT_TOO_SHORT")
        
        return issues


