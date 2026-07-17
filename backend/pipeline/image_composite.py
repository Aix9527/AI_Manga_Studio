"""
AI Manga Studio Pro V2.0 — Image Composite Engine

Composites character (RGBA with alpha) onto background with
pose-aware positioning, lighting integration, and blend modes.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from backend.config import get_config


# ============================================================
# Data Classes
# ============================================================

@dataclass
class CompositeConfig:
    """Configuration for image compositing."""
    blend_mode: str = "overlay"       # overlay | screen | multiply | normal
    shadow_enabled: bool = True
    shadow_opacity: float = 0.3
    shadow_offset: Tuple[int, int] = (8, 8)
    depth_of_field: bool = False
    color_grading: bool = True
    target_temperature: float = 6500.0  # Kelvin
    output_width: int = 1344
    output_height: int = 768


@dataclass
class CompositeResult:
    """Result from image compositing."""
    file_path: str = ""
    success: bool = False
    elapsed: float = 0.0
    error: str = ""


# ============================================================
# Image Composite Engine
# ============================================================

class ImageComposite:
    """Composite character onto background with professional layering.

    Steps:
    1. Load background as base layer
    2. Remove background from character (if not already RGBA)
    3. Position character based on pose reference
    4. Apply lighting integration (screen/overlay blend)
    5. Apply depth of field, color grading
    6. Export final composite
    """

    def __init__(
        self,
        output_dir: str = "",
        config: Optional[CompositeConfig] = None,
    ) -> None:
        cfg = get_config()
        self.output_dir = Path(output_dir or cfg.project.output_path) / "composites"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or CompositeConfig()

    def composite(
        self,
        character_path: str,
        background_path: str,
        pose_data: Optional[Dict[str, Any]] = None,
        shot_index: int = 0,
        chapter_index: int = 0,
        character_position: str = "center",  # center | left | right
        character_scale: float = 1.0,
    ) -> CompositeResult:
        """Composite character onto background.

        Args:
            character_path: Path to character PNG (preferably RGBA).
            background_path: Path to background image.
            pose_data: Optional pose keypoints for positioning.
            shot_index: Shot index for naming.
            chapter_index: Chapter index for naming.
            character_position: Positioning hint.
            character_scale: Character scale factor.

        Returns:
            CompositeResult with path to final composite.
        """
        t0 = time.time()
        filename = f"ch{chapter_index:03d}_sh{shot_index:03d}_composite.png"
        output_path = str(self.output_dir / filename)

        try:
            # Load images
            if not os.path.isfile(character_path):
                return CompositeResult(error=f"Character not found: {character_path}")
            if not os.path.isfile(background_path):
                return CompositeResult(error=f"Background not found: {background_path}")

            bg = Image.open(background_path).convert("RGBA")
            char = Image.open(character_path).convert("RGBA")

            # Resize background to target resolution
            bg = bg.resize(
                (self.config.output_width, self.config.output_height),
                Image.LANCZOS,
            )

            # Resize character proportionally
            char = self._resize_character(char, bg, character_scale)

            # Position character
            x, y = self._calculate_position(
                char, bg, character_position, pose_data
            )

            # Paste character onto background
            canvas = bg.copy()
            canvas.paste(char, (x, y), char)

            # Apply shadow
            if self.config.shadow_enabled:
                canvas = self._apply_shadow(canvas, char, x, y)

            # Lighting integration
            if self.config.blend_mode != "normal":
                canvas = self._apply_lighting_blend(canvas, char, x, y)

            # Color grading
            if self.config.color_grading:
                canvas = self._apply_color_grading(canvas)

            # Depth of field
            if self.config.depth_of_field:
                canvas = self._apply_depth_of_field(canvas, char, x, y)

            # Save
            canvas = canvas.convert("RGB")
            canvas.save(output_path, "PNG", optimize=True)

            elapsed = time.time() - t0
            logger.info(
                f"ImageComposite: ch{chapter_index:03d}_sh{shot_index:03d} "
                f"→ {output_path} ({elapsed:.2f}s)"
            )

            return CompositeResult(
                file_path=output_path,
                success=True,
                elapsed=elapsed,
            )

        except Exception as e:
            logger.error(f"ImageComposite failed: {e}")
            return CompositeResult(error=str(e), elapsed=time.time() - t0)

    def batch_composite(
        self,
        pairs: List[Dict[str, Any]],
        chapter_index: int = 0,
    ) -> List[CompositeResult]:
        """Composite multiple character+background pairs.

        Args:
            pairs: List of {character_path, background_path, pose_data, shot_index, ...}
            chapter_index: Chapter index.

        Returns:
            List of CompositeResult for each pair.
        """
        results = []
        for pair in pairs:
            result = self.composite(
                character_path=pair.get("character_path", ""),
                background_path=pair.get("background_path", ""),
                pose_data=pair.get("pose_data"),
                shot_index=pair.get("shot_index", 0),
                chapter_index=chapter_index,
                character_position=pair.get("character_position", "center"),
                character_scale=pair.get("character_scale", 1.0),
            )
            results.append(result)
            if not result.success:
                logger.warning(f"ImageComposite batch: shot {pair.get('shot_index')} failed")
        return results

    # ----------------------------------------------------------
    # Internal Helpers
    # ----------------------------------------------------------

    def _resize_character(
        self,
        char: Image.Image,
        bg: Image.Image,
        scale: float,
    ) -> Image.Image:
        """Resize character while maintaining aspect ratio."""
        bg_w, bg_h = bg.size
        char_w, char_h = char.size

        # Target character height: 50% of background height by default
        target_height = int(bg_h * 0.5 * scale)
        ratio = target_height / max(char_h, 1)
        new_w = int(char_w * ratio)
        new_h = target_height

        return char.resize((new_w, new_h), Image.LANCZOS)

    def _calculate_position(
        self,
        char: Image.Image,
        bg: Image.Image,
        position: str,
        pose_data: Optional[Dict[str, Any]],
    ) -> Tuple[int, int]:
        """Calculate character position on background."""
        bg_w, bg_h = bg.size
        char_w, char_h = char.size

        # Vertical: center character vertically, slightly lower
        y = (bg_h - char_h) // 2 + int(bg_h * 0.05)

        if position == "left":
            x = int(bg_w * 0.1)
        elif position == "right":
            x = bg_w - char_w - int(bg_w * 0.1)
        else:  # center
            x = (bg_w - char_w) // 2

        # Adjust based on pose data if available
        if pose_data and "keypoints" in pose_data:
            kp = pose_data["keypoints"]
            if "nose" in kp:
                nose_x, nose_y = kp["nose"]
                # Shift character so nose aligns roughly with center
                offset_x = int((nose_x - 0.5) * bg_w * 0.15)
                x += offset_x

        return x, y

    def _apply_shadow(
        self,
        canvas: Image.Image,
        char: Image.Image,
        x: int,
        y: int,
    ) -> Image.Image:
        """Apply drop shadow behind character."""
        char_w, char_h = char.size
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))

        # Extract alpha as shadow shape
        char_alpha = char.split()[-1]
        shadow_char = ImageOps.invert(char_alpha.convert("L"))
        shadow_char = shadow_char.filter(ImageFilter.GaussianBlur(radius=12))

        ox, oy = self.config.shadow_offset
        sx = max(0, x + ox)
        sy = max(0, y + oy)

        shadow.paste(
            (0, 0, 0, int(255 * self.config.shadow_opacity)),
            (sx, sy, sx + char_w, sy + char_h),
            shadow_char,
        )

        return Image.alpha_composite(canvas, shadow)

    def _apply_lighting_blend(
        self,
        canvas: Image.Image,
        char: Image.Image,
        x: int,
        y: int,
    ) -> Image.Image:
        """Apply lighting blend mode between character and background."""
        char_w, char_h = char.size

        if self.config.blend_mode == "overlay":
            # Extract character region and apply soft-light blending
            char_region = canvas.crop((x, y, x + char_w, y + char_h))
            blended = Image.blend(char_region, char, 0.15)
            canvas.paste(blended, (x, y))

        elif self.config.blend_mode == "screen":
            # Screen blend: lighter result
            import numpy as np
            bg_arr = np.array(canvas, dtype=np.float32)
            char_arr = np.array(char, dtype=np.float32)

            region = bg_arr[y:y+char_h, x:x+char_w]
            screen = 255.0 - (255.0 - region) * (255.0 - char_arr) / 255.0
            screen = np.clip(screen, 0, 255).astype(np.uint8)

            result_arr = bg_arr.copy()
            result_arr[y:y+char_h, x:x+char_w] = np.where(
                char_arr[:, :, 3:4] > 0, screen, region
            )
            canvas = Image.fromarray(result_arr, "RGBA")

        return canvas

    def _apply_color_grading(self, img: Image.Image) -> Image.Image:
        """Apply subtle color grading for cohesive look."""
        # Slight warmth adjustment
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.05)

        # Slight contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.03)

        return img

    def _apply_depth_of_field(
        self,
        canvas: Image.Image,
        char: Image.Image,
        x: int,
        y: int,
    ) -> Image.Image:
        """Apply simulated depth of field.
        
        Background edges get slight blur, character stays sharp.
        """
        # Blur the far edges of background
        blurred_bg = canvas.copy()
        blurred_bg = blurred_bg.filter(ImageFilter.GaussianBlur(radius=2))

        # Create gradient mask: sharp in center, blurry at edges
        mask = Image.new("L", canvas.size, 255)
        # Keep character region sharp
        char_w, char_h = char.size
        for py in range(y, y + char_h):
            for px in range(x, x + char_w):
                if 0 <= py < canvas.height and 0 <= px < canvas.width:
                    mask.putpixel((px, py), 0)

        canvas = Image.composite(canvas, blurred_bg, mask)
        return canvas
