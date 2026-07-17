"""
AI Manga Studio Pro V2.0 — Style Manager

Driven by StoryGraph.emotion_curve. Dynamically adjusts color palette,
LUT grade, and art-style intensity per Scene/Beat based on emotional context.

Architecture:
  StoryGraph → StyleManager → Per-shot style parameters
                                   ↓
                            Prompt Engine / ComfyUI workflow
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from loguru import logger


# ============================================================
# Data Classes
# ============================================================

@dataclass
class StylePreset:
    """A named visual style preset."""
    name: str = ""
    color_palette: str = ""       # warm/cool/monochrome/pastel/vivid/dark-palette
    lut: str = ""                 # simple name for the look-up-table / grade
    contrast: float = 1.0         # 0.5~2.0
    saturation: float = 1.0       # 0.0~2.0
    warmth: float = 0.0           # -1.0(cool) ~ 1.0(warm)
    brightness: float = 0.0       # -1.0(dark) ~ 1.0(bright)
    art_style_intensity: float = 1.0  # 0.0(realistic) ~ 1.0(stylized)
    prompt_fragment: str = ""     # injected into the positive prompt


@dataclass
class BeatStyle:
    """Computed style parameters for a single beat."""
    beat_id: str = ""
    preset: StylePreset = field(default_factory=StylePreset)
    custom_overrides: Dict[str, float] = field(default_factory=dict)


# ============================================================
# Emotion → Style Mapping
# ============================================================

EMOTION_STYLE_MAP: Dict[str, StylePreset] = {
    "angry": StylePreset(
        name="愤怒",
        color_palette="warm",
        lut="crimson_tension",
        contrast=1.4,
        saturation=1.3,
        warmth=0.7,
        brightness=-0.1,
        art_style_intensity=0.9,
        prompt_fragment="dramatic crimson lighting, intense atmosphere, sharp shadows, high contrast, angry mood",
    ),
    "sad": StylePreset(
        name="悲伤",
        color_palette="cool",
        lut="blue_melancholy",
        contrast=0.8,
        saturation=0.5,
        warmth=-0.5,
        brightness=-0.3,
        art_style_intensity=0.7,
        prompt_fragment="muted blue tones, soft shadows, melancholic atmosphere, gentle lighting, sad mood",
    ),
    "happy": StylePreset(
        name="喜悦",
        color_palette="vivid",
        lut="golden_warm",
        contrast=1.1,
        saturation=1.2,
        warmth=0.5,
        brightness=0.3,
        art_style_intensity=0.8,
        prompt_fragment="warm golden light, vibrant colors, cheerful atmosphere, soft bokeh, happy mood",
    ),
    "fearful": StylePreset(
        name="恐惧",
        color_palette="dark-palette",
        lut="shadow_green",
        contrast=1.5,
        saturation=0.4,
        warmth=-0.3,
        brightness=-0.5,
        art_style_intensity=1.0,
        prompt_fragment="dark oppressive atmosphere, deep shadows, cold moonlight, eerie lighting, fearful mood, desaturated",
    ),
    "surprised": StylePreset(
        name="惊讶",
        color_palette="vivid",
        lut="flash_white",
        contrast=1.3,
        saturation=1.0,
        warmth=0.2,
        brightness=0.4,
        art_style_intensity=0.9,
        prompt_fragment="bright flash lighting, high key, dramatic reveal, surprised expression, striking contrast",
    ),
    "neutral": StylePreset(
        name="中性",
        color_palette="natural",
        lut="natural_light",
        contrast=1.0,
        saturation=1.0,
        warmth=0.0,
        brightness=0.0,
        art_style_intensity=0.6,
        prompt_fragment="natural lighting, balanced colors, clean composition, neutral mood",
    ),
    "loving": StylePreset(
        name="爱意",
        color_palette="pastel",
        lut="rose_bloom",
        contrast=0.9,
        saturation=1.1,
        warmth=0.4,
        brightness=0.2,
        art_style_intensity=0.8,
        prompt_fragment="soft pink tones, romantic atmosphere, gentle bokeh, warm glow, loving mood, dreamy lighting",
    ),
    "hateful": StylePreset(
        name="憎恨",
        color_palette="dark-palette",
        lut="noir_grit",
        contrast=1.6,
        saturation=0.3,
        warmth=-0.2,
        brightness=-0.4,
        art_style_intensity=1.0,
        prompt_fragment="harsh noir lighting, deep shadows, gritty atmosphere, cold metallic tones, hostile mood, jagged composition",
    ),
    "worried": StylePreset(
        name="担忧",
        color_palette="cool",
        lut="grey_anxiety",
        contrast=0.9,
        saturation=0.6,
        warmth=-0.2,
        brightness=-0.1,
        art_style_intensity=0.7,
        prompt_fragment="overcast grey tones, soft diffused lighting, anxious atmosphere, subdued colors, worried mood",
    ),
}

# Mood-based overrides for dominant scene mood
MOOD_STYLE_OVERRIDES: Dict[str, Dict[str, float]] = {
    "majestic": {"contrast": 1.35, "saturation": 1.15, "brightness": 0.15, "warmth": 0.2},
    "mysterious": {"contrast": 1.25, "saturation": 0.7, "brightness": -0.2, "warmth": -0.15},
    "tense": {"contrast": 1.4, "saturation": 0.65, "brightness": -0.1, "warmth": -0.1},
    "peaceful": {"contrast": 0.85, "saturation": 0.9, "brightness": 0.2, "warmth": 0.25},
    "melancholic": {"contrast": 0.75, "saturation": 0.45, "brightness": -0.25, "warmth": -0.4},
    "surreal": {"contrast": 1.5, "saturation": 1.4, "brightness": 0.1, "warmth": 0.0},
    "oppressive": {"contrast": 1.55, "saturation": 0.35, "brightness": -0.45, "warmth": -0.25},
    "neutral": {},
}


# ============================================================
# Style Manager
# ============================================================

class StyleManager:
    """Dynamically resolves per-beat style parameters from StoryGraph.

    Usage:
        from backend.story_graph import StoryGraph
        from backend.pipeline.style_manager import StyleManager

        sm = StyleManager()
        beat_styles = sm.compute_beat_styles(story_graph)
    """

    def __init__(self):
        pass

    def compute_beat_styles(self, story_graph: "StoryGraph") -> List[BeatStyle]:
        """Compute per-beat style parameters from StoryGraph.

        For each beat on the timeline:
          1. Look up the emotion → base StylePreset
          2. Look up the scene mood → apply overrides
          3. Blend with adjacent beats for smooth transitions

        Args:
            story_graph: Fully populated StoryGraph.

        Returns:
            List of BeatStyle, one per beat, in timeline order.
        """
        beat_styles: List[BeatStyle] = []

        if not story_graph.timeline.beats:
            return beat_styles

        for i, beat in enumerate(story_graph.timeline.beats):
            # Base style from emotion
            emotion = beat.emotion.lower()
            preset = EMOTION_STYLE_MAP.get(
                emotion, EMOTION_STYLE_MAP["neutral"]
            )

            # Mood override from scene context
            scene_ctx = story_graph.scene_map.get(beat.scene_id)
            overrides: Dict[str, float] = {}
            if scene_ctx:
                mood_overrides = MOOD_STYLE_OVERRIDES.get(
                    scene_ctx.mood.lower(), {}
                )
                overrides.update(mood_overrides)

            # Blend with adjacent beat (smooth transition)
            if i > 0:
                prev_style = beat_styles[i - 1]
                blend_ratio = 0.2  # 20% influence from previous beat
                overrides["contrast"] = overrides.get("contrast", preset.contrast) * (1 - blend_ratio) + \
                    (prev_style.preset.contrast + prev_style.custom_overrides.get("contrast", 0)) * blend_ratio
                overrides["saturation"] = overrides.get("saturation", preset.saturation) * (1 - blend_ratio) + \
                    (prev_style.preset.saturation + prev_style.custom_overrides.get("saturation", 0)) * blend_ratio

            bs = BeatStyle(
                beat_id=beat.beat_id,
                preset=preset,
                custom_overrides=overrides,
            )
            beat_styles.append(bs)

        return beat_styles

    def get_beat_style(self, beat_id: str, beat_styles: List[BeatStyle]) -> Optional[BeatStyle]:
        """Look up a specific beat's style."""
        for bs in beat_styles:
            if bs.beat_id == beat_id:
                return bs
        return None

    def to_prompt_fragment(self, beat_style: BeatStyle) -> str:
        """Generate the prompt injection fragment for a beat style.

        Returns a string that can be appended to the positive prompt
        to influence the visual style of the generated image.
        """
        preset = beat_style.preset
        overrides = beat_style.custom_overrides

        contrast = overrides.get("contrast", preset.contrast)
        saturation = overrides.get("saturation", preset.saturation)
        warmth = overrides.get("warmth", preset.warmth)
        brightness = overrides.get("brightness", preset.brightness)

        fragments = [preset.prompt_fragment]

        # Add quantitative descriptors
        if contrast > 1.3:
            fragments.append("high contrast")
        elif contrast < 0.8:
            fragments.append("low contrast")

        if saturation > 1.3:
            fragments.append("highly saturated")
        elif saturation < 0.6:
            fragments.append("desaturated")

        if warmth > 0.5:
            fragments.append("warm color temperature")
        elif warmth < -0.5:
            fragments.append("cool color temperature")

        if brightness > 0.3:
            fragments.append("bright exposure")
        elif brightness < -0.3:
            fragments.append("dark exposure")

        return ", ".join(fragments)

    def summary(self, beat_styles: List[BeatStyle]) -> str:
        """Generate a summary of the style distribution."""
        emotion_counts: Dict[str, int] = {}
        for bs in beat_styles:
            name = bs.preset.name
            emotion_counts[name] = emotion_counts.get(name, 0) + 1

        lines = [f"StyleManager: {len(beat_styles)} beats styled"]
        for emotion, count in sorted(emotion_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {emotion}: {count} beats")
        return "\n".join(lines)
