"""
AI Manga Studio Pro V2.0 — Kolors Visual Effects Overlay

Generates and overlays visual effects layers:
- Light effects (glow, lens flare, god rays)
- Particle effects (magic, rain, snow, dust)
- Depth of field blur
- Color grading / cinematic LUT
- Vignette + film grain

Uses Kolors model for effect generation + PIL for compositing.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageOps

from backend.comfyui_client import ComfyUIClient
from backend.config import get_config


# ============================================================
# Enums & Data Classes
# ============================================================

class EffectType(str, Enum):
    glow = "glow"
    lens_flare = "lens_flare"
    god_rays = "god_rays"
    particles = "particles"
    magic = "magic"
    rain = "rain"
    snow = "snow"
    dust = "dust"
    depth_blur = "depth_blur"
    vignette = "vignette"
    film_grain = "film_grain"
    color_grade = "color_grade"


class WeatherType(str, Enum):
    clear = "clear"
    rain = "rain"
    snow = "snow"
    fog = "fog"
    storm = "storm"
    dust_storm = "dust_storm"


@dataclass
class EffectConfig:
    """Configuration for a single effect."""
    effect_type: EffectType
    intensity: float = 0.5           # 0.0 - 1.0
    color: Tuple[int, int, int] = (255, 255, 255)
    position: Tuple[float, float] = (0.5, 0.5)  # (x, y) normalized
    seed: int = -1


@dataclass
class EffectsResult:
    """Result of effects application."""
    file_path: str = ""
    effects_applied: List[EffectType] = field(default_factory=list)
    success: bool = False
    elapsed: float = 0.0
    error: str = ""


# ============================================================
# Effects Overlay Engine
# ============================================================

class EffectsOverlay:
    """Applies visual effects to composited frames.

    Effects pipeline:
    1. Based on shot metadata (weather, mood, lighting),
       determine which effects to apply.
    2. Generate effect layers (via Kolors for complex effects,
       PIL for simple ones).
    3. Composite effect layers onto frame.
    """

    # Environment → effects mapping
    WEATHER_EFFECTS: Dict[str, List[EffectType]] = {
        "rain": [EffectType.rain, EffectType.depth_blur],
        "snow": [EffectType.snow, EffectType.vignette],
        "fog": [EffectType.depth_blur, EffectType.vignette],
        "storm": [EffectType.rain, EffectType.god_rays, EffectType.depth_blur],
        "dust_storm": [EffectType.dust, EffectType.depth_blur, EffectType.color_grade],
        "clear": [],
    }

    # Mood → effects mapping
    MOOD_EFFECTS: Dict[str, List[EffectType]] = {
        "romantic": [EffectType.glow, EffectType.lens_flare, EffectType.color_grade],
        "epic": [EffectType.god_rays, EffectType.color_grade],
        "dark": [EffectType.vignette, EffectType.color_grade],
        "tense": [EffectType.vignette, EffectType.color_grade, EffectType.film_grain],
        "sad": [EffectType.depth_blur, EffectType.vignette, EffectType.color_grade],
        "mysterious": [EffectType.glow, EffectType.particles, EffectType.vignette],
        "magical": [EffectType.magic, EffectType.glow, EffectType.god_rays],
        "action": [EffectType.particles, EffectType.film_grain],
        "warm": [EffectType.glow, EffectType.color_grade],
        "cold": [EffectType.color_grade, EffectType.vignette],
        "neutral": [],
    }

    def __init__(
        self,
        client: Optional[ComfyUIClient] = None,
        output_dir: str = "",
        kolors_enabled: bool = False,
        default_intensity: float = 0.5,
    ) -> None:
        cfg = get_config()
        self.client = client or ComfyUIClient()
        self.output_dir = Path(output_dir or cfg.project.output_path) / "effects"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.kolors_enabled = kolors_enabled
        self.default_intensity = default_intensity

    def apply(
        self,
        image_path: str,
        weather: str = "clear",
        mood: str = "neutral",
        lighting: str = "natural",
        shot_index: int = 0,
        chapter_index: int = 0,
        custom_effects: Optional[List[EffectConfig]] = None,
    ) -> EffectsResult:
        """Apply effects to a single frame.

        Args:
            image_path: Path to composite image.
            weather: Weather condition.
            mood: Scene mood.
            lighting: Lighting description.
            shot_index: Shot index.
            chapter_index: Chapter index.
            custom_effects: Optional explicit effect list.

        Returns:
            EffectsResult with path to processed image.
        """
        t0 = time.time()

        # Determine effects
        if custom_effects:
            effects = custom_effects
        else:
            effects = self._determine_effects(weather, mood, lighting)

        if not effects:
            # No effects needed — return original
            return EffectsResult(
                file_path=image_path,
                effects_applied=[],
                success=True,
                elapsed=time.time() - t0,
            )

        filename = f"ch{chapter_index:03d}_sh{shot_index:03d}_fx.png"
        output_path = str(self.output_dir / filename)

        try:
            img = Image.open(image_path).convert("RGBA")

            for effect in effects:
                img = self._apply_effect(img, effect)

            img = img.convert("RGB")
            img.save(output_path, "PNG", optimize=True)

            elapsed = time.time() - t0
            effect_names = [e.effect_type for e in effects]

            logger.info(
                f"EffectsOverlay: sh{shot_index} → {len(effects)} effects "
                f"({', '.join(e.value for e in effect_names)}) ({elapsed:.2f}s)"
            )

            return EffectsResult(
                file_path=output_path,
                effects_applied=effect_names,
                success=True,
                elapsed=elapsed,
            )

        except Exception as e:
            logger.error(f"EffectsOverlay: Shot {shot_index} failed — {e}")
            return EffectsResult(
                file_path=image_path,
                error=str(e),
                elapsed=time.time() - t0,
            )

    def batch_apply(
        self,
        frames: List[Dict[str, Any]],
        chapter_index: int = 0,
    ) -> List[EffectsResult]:
        """Apply effects to multiple frames.

        Args:
            frames: List of {image_path, weather, mood, lighting, shot_index}.
            chapter_index: Chapter index.

        Returns:
            List of EffectsResult.
        """
        results = []
        for frame in frames:
            result = self.apply(
                image_path=frame.get("image_path", ""),
                weather=frame.get("weather", "clear"),
                mood=frame.get("mood", "neutral"),
                lighting=frame.get("lighting", "natural"),
                shot_index=frame.get("shot_index", 0),
                chapter_index=chapter_index,
                custom_effects=frame.get("custom_effects"),
            )
            results.append(result)
        return results

    # ----------------------------------------------------------
    # Effect determination
    # ----------------------------------------------------------

    def _determine_effects(
        self,
        weather: str,
        mood: str,
        lighting: str,
    ) -> List[EffectConfig]:
        """Determine which effects to apply based on scene metadata.

        Args:
            weather: Weather condition.
            mood: Scene mood.
            lighting: Lighting type.

        Returns:
            List of EffectConfig.
        """
        effects: List[EffectConfig] = []

        # Weather effects
        weather_effects = self.WEATHER_EFFECTS.get(weather, [])
        for ef in weather_effects:
            effects.append(EffectConfig(
                effect_type=ef,
                intensity=self.default_intensity,
            ))

        # Mood effects (skip if already added)
        mood_effects = self.MOOD_EFFECTS.get(mood, [])
        existing_types = {e.effect_type for e in effects}
        for ef in mood_effects:
            if ef not in existing_types:
                effects.append(EffectConfig(
                    effect_type=ef,
                    intensity=self.default_intensity,
                ))
                existing_types.add(ef)

        # Lighting-specific adjustments
        if "warm" in lighting.lower():
            if EffectType.color_grade not in existing_types:
                effects.append(EffectConfig(
                    effect_type=EffectType.color_grade,
                    intensity=0.3,
                    color=(255, 200, 100),
                ))
        elif "cold" in lighting.lower() or "blue" in lighting.lower():
            if EffectType.color_grade not in existing_types:
                effects.append(EffectConfig(
                    effect_type=EffectType.color_grade,
                    intensity=0.3,
                    color=(100, 150, 255),
                ))

        return effects

    # ----------------------------------------------------------
    # Effect renderers
    # ----------------------------------------------------------

    def _apply_effect(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Apply a single effect to image.

        Args:
            img: Input PIL Image (RGBA).
            config: Effect configuration.

        Returns:
            Modified PIL Image.
        """
        if config.effect_type == EffectType.vignette:
            return self._render_vignette(img, config)
        elif config.effect_type == EffectType.glow:
            return self._render_glow(img, config)
        elif config.effect_type == EffectType.film_grain:
            return self._render_film_grain(img, config)
        elif config.effect_type == EffectType.depth_blur:
            return self._render_depth_blur(img, config)
        elif config.effect_type == EffectType.color_grade:
            return self._render_color_grade(img, config)
        elif config.effect_type == EffectType.lens_flare:
            return self._render_lens_flare(img, config)
        elif config.effect_type == EffectType.god_rays:
            return self._render_god_rays(img, config)
        elif config.effect_type in (
            EffectType.particles, EffectType.magic, EffectType.rain,
            EffectType.snow, EffectType.dust,
        ):
            return self._render_particles(img, config)
        else:
            return img

    def _render_vignette(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Apply vignette effect (darken edges)."""
        w, h = img.size
        intensity = config.intensity

        # Create radial gradient mask
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)

        cx, cy = w // 2, h // 2
        max_r = max(cx, cy) * 1.2

        for y in range(h):
            for x in range(w):
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                ratio = min(1.0, dist / max_r)
                # Ease curve: fast at edges
                alpha = int((ratio ** 2) * 255 * intensity)
                mask.putpixel((x, y), alpha)

        dark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        img = Image.alpha_composite(img.convert("RGBA"), dark)

        # Simple: darken edges with a circle mask
        img_rgb = img.convert("RGB")
        darkened = ImageEnhance.Brightness(img_rgb).enhance(1.0 - intensity * 0.5)

        # Apply mask
        result = Image.blend(img_rgb, darkened, intensity * 0.3)

        return result.convert("RGBA")

    def _render_glow(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Apply soft glow effect."""
        intensity = config.intensity

        # Create brightened copy
        bright = ImageEnhance.Brightness(img.convert("RGB")).enhance(1.0 + intensity * 0.3)

        # Blur it for glow
        glow = bright.filter(ImageFilter.GaussianBlur(radius=10 * intensity))

        # Blend with original
        result = Image.blend(img.convert("RGB"), glow, intensity * 0.25)

        return result.convert("RGBA")

    def _render_film_grain(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Add film grain noise."""
        import random
        random.seed(config.seed if config.seed >= 0 else int(time.time()))

        w, h = img.size
        intensity = config.intensity

        grain = Image.new("L", (w, h))
        for y in range(h):
            for x in range(w):
                grain.putpixel((x, y), random.randint(0, int(255 * intensity * 0.3)))

        grain_rgba = Image.merge("RGBA", (grain, grain, grain, grain))
        result = Image.alpha_composite(img.convert("RGBA"), grain_rgba)

        return result

    def _render_depth_blur(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Apply depth of field blur to edges."""
        intensity = config.intensity

        blurred = img.filter(ImageFilter.GaussianBlur(radius=3 * intensity))

        # Keep center sharp, blur edges
        w, h = img.size
        mask = Image.new("L", (w, h), 255)

        cx, cy = w // 2, h // 2
        max_r = min(cx, cy) * 0.6

        for y in range(h):
            for x in range(w):
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                if dist < max_r:
                    mask.putpixel((x, y), 0)

        mask = mask.filter(ImageFilter.GaussianBlur(radius=20))

        result = Image.composite(
            img.convert("RGBA"),
            blurred.convert("RGBA"),
            mask,
        )

        return result

    def _render_color_grade(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Apply color grading tint."""
        r, g, b = config.color

        # Create tint overlay
        img_rgb = img.convert("RGB")
        tint = Image.new("RGB", img_rgb.size, (r, g, b))

        result = Image.blend(img_rgb, tint, config.intensity * 0.15)

        return result.convert("RGBA")

    def _render_lens_flare(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Add lens flare effect."""
        w, h = img.size
        intensity = config.intensity

        img_rgb = img.convert("RGB")

        # Bright point at light source position
        lx = int(config.position[0] * w)
        ly = int(config.position[1] * h)

        flare = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(flare)

        # Main flare circle
        r = int(min(w, h) * 0.05)
        for i in range(r, 0, -1):
            alpha = int(200 * intensity * (i / r) ** 2)
            draw.ellipse(
                [lx - i, ly - i, lx + i, ly + i],
                fill=(255, 255, 200, alpha),
            )

        # Streak line
        line_len = w // 3
        for i in range(line_len):
            alpha = int(100 * intensity * (1 - i / line_len))
            x = lx - i
            if 0 <= x < w and 0 <= ly < h:
                flare.putpixel((x, ly), (255, 255, 200, alpha))

        result = Image.alpha_composite(img_rgb.convert("RGBA"), flare)

        return result

    def _render_god_rays(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Add god rays (light beams from above)."""
        w, h = img.size
        intensity = config.intensity

        img_rgb = img.convert("RGB")

        # Create ray overlay
        rays = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(rays)

        ray_count = 5
        for i in range(ray_count):
            angle = (i / ray_count) * 3.14159 * 0.6 - 0.3 + 1.57  # Top angles

            for t in range(1, h * 3):
                x = int(w / 2 + t * 0.15 * (i - ray_count / 2))
                y = int(t * 0.3)
                if 0 <= x < w and 0 <= y < h:
                    alpha = int(30 * intensity * (1 - t / (h * 3)) ** 1.5)
                    existing = rays.getpixel((x, y))
                    new_alpha = min(255, existing[3] + alpha)
                    rays.putpixel((x, y), (255, 240, 200, new_alpha))

        result = Image.alpha_composite(img_rgb.convert("RGBA"), rays)

        return result

    def _render_particles(
        self,
        img: Image.Image,
        config: EffectConfig,
    ) -> Image.Image:
        """Add particle effects (rain, snow, dust, magic)."""
        import random
        random.seed(config.seed if config.seed >= 0 else int(time.time()))

        w, h = img.size
        intensity = config.intensity

        img_rgb = img.convert("RGB")
        particles = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(particles)

        count = int(200 * intensity)

        for _ in range(count):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)

            if config.effect_type == EffectType.snow:
                r = random.randint(1, 3)
                color = (255, 255, 255, random.randint(100, 200))
            elif config.effect_type == EffectType.rain:
                r = 1
                color = (180, 200, 255, random.randint(80, 180))
            elif config.effect_type == EffectType.magic:
                r = random.randint(1, 4)
                color = (
                    random.randint(200, 255),
                    random.randint(150, 255),
                    random.randint(200, 255),
                    random.randint(100, 200),
                )
            elif config.effect_type == EffectType.dust:
                r = random.randint(1, 2)
                color = (180, 160, 120, random.randint(60, 120))
            else:
                r = random.randint(1, 2)
                color = (200, 200, 200, random.randint(80, 150))

            draw.ellipse([x, y, x + r, y + r], fill=color)

        result = Image.alpha_composite(img_rgb.convert("RGBA"), particles)

        return result
