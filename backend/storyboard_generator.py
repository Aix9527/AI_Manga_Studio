"""
Storyboard Generator V2.0 — StoryGraph-driven Multi-Panel Layout

Generates a storyboard grid image from StoryGraph output, showing
Scene → Beat → Shot hierarchy with metadata and generated images.

Driven by StoryGraph.scene_map for context (time/weather/lighting/mood),
and by the AI Director's hierarchical Chapter→Scene→Beat→Shot output.

Runs AFTER Image Generation (Stage 4) and BEFORE Video (Stage 5).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from loguru import logger

# ============================================================
# Layout Constants
# ============================================================

PANEL_PADDING = 8
MARGIN = 40
HEADER_HEIGHT = 80
SECTION_HEIGHT = 30     # scene header band
LABEL_HEIGHT = 36
MAX_COLS = 4
THUMB_WIDTH = 320
THUMB_HEIGHT = 180      # 16:9


# ============================================================
# Generator
# ============================================================

class StoryboardGenerator:
    """V2.0 — StoryGraph-driven storyboard generator.

    Takes StoryGraph + hierarchical parse output and generates
    annotated grid layouts showing the full narrative structure.

    Usage:
        sg = StoryGraphParser().parse_chapters(chapters)
        gen = StoryboardGenerator()
        gen.generate_from_storygraph(story_graph, chapters, output_path)
    """

    def __init__(self, font_path: str = ""):
        self.font_path = font_path

    # ----------------------------------------------------------
    # V2.0: StoryGraph-driven generation
    # ----------------------------------------------------------

    def generate_from_storygraph(
        self,
        story_graph: Any,          # StoryGraph
        chapters: List[Any],       # List[Chapter] from HierarchicalDirector
        output_dir: str,
        image_dir: str = "",
        chapter_index: Optional[int] = None,
    ) -> List[str]:
        """Generate storyboard images from StoryGraph data.

        Creates one storyboard PNG per chapter, or a single PNG
        if chapter_index is specified.

        Args:
            story_graph: StoryGraph object with scene_map, emotion_curve, etc.
            chapters: List[Chapter] from HierarchicalDirector.parse_hierarchical().
            output_dir: Directory for output PNGs.
            image_dir: Directory with generated shot images (optional).
            chapter_index: If set, generate only for this chapter (1-based).

        Returns:
            List of absolute paths to generated PNG files.
        """
        os.makedirs(output_dir, exist_ok=True)

        # Extract scene_map for context injection
        scene_map = getattr(story_graph, "scene_map", {}) if story_graph else {}

        output_paths: List[str] = []

        chapters_to_render = chapters
        if chapter_index is not None:
            chapters_to_render = [
                ch for ch in chapters
                if getattr(ch, "chapter_idx", 0) == chapter_index
            ]

        for ch in chapters_to_render:
            ch_idx = getattr(ch, "chapter_idx", 0)
            title = getattr(ch, "title", f"Chapter {ch_idx:02d}")
            path = self._generate_chapter_grid(
                chapter=ch,
                chapter_title=title,
                scene_map=scene_map,
                output_path=os.path.join(output_dir, f"storyboard_ch{ch_idx:02d}.png"),
                image_dir=image_dir,
            )
            if path:
                output_paths.append(path)

        logger.info(
            f"StoryboardGenerator V2: Generated {len(output_paths)} storyboard(s) "
            f"→ {output_dir}"
        )
        return output_paths

    def _generate_chapter_grid(
        self,
        chapter: Any,
        chapter_title: str,
        scene_map: Dict[str, Any],
        output_path: str,
        image_dir: str = "",
    ) -> str:
        """Generate one chapter's storyboard grid with Scene→Beat→Shot hierarchy."""
        scenes = getattr(chapter, "scenes", [])

        # Flatten all shots from all scenes
        all_panels: List[dict] = []

        for sc in scenes:
            sc_id = getattr(sc, "scene_id", "")
            ctx = scene_map.get(sc_id)

            beats = getattr(sc, "beats", [])
            shots = getattr(sc, "shots", [])

            # Scene header panel
            all_panels.append({
                "type": "scene_header",
                "scene_id": sc_id,
                "location": ctx.location if ctx and hasattr(ctx, "location") else getattr(sc, "location", ""),
                "time": ctx.time_of_day if ctx and hasattr(ctx, "time_of_day") else getattr(sc, "time", ""),
                "weather": ctx.weather if ctx and hasattr(ctx, "weather") else getattr(sc, "weather", ""),
                "mood": ctx.mood if ctx and hasattr(ctx, "mood") else getattr(sc, "mood", ""),
                "tone": ctx.tone if ctx and hasattr(ctx, "tone") else "",
                "lighting": ctx.lighting if ctx and hasattr(ctx, "lighting") else "",
                "color_scheme": ctx.color_scheme if ctx and hasattr(ctx, "color_scheme") else "",
                "characters_present": ctx.characters_present if ctx and hasattr(ctx, "characters_present") else [],
            })

            # Beat → Shot panels
            for sh in shots:
                beat_info = None
                # Try to find parent beat by matching beat_id
                sh_id = getattr(sh, "shot_id", "")
                for bt in beats:
                    bt_id = getattr(bt, "beat_id", "")
                    # Match: shot_id = sh_{ch}_{sc}_{idx}, beat_id = bt_{ch}_{sc}_{idx}
                    if bt_id and sh_id:
                        bt_parts = bt_id.split("_")
                        sh_parts = sh_id.split("_")
                        if len(bt_parts) >= 3 and len(sh_parts) >= 3:
                            if bt_parts[1:3] == sh_parts[1:3]:  # same ch+sc
                                beat_info = bt
                                break

                camera = getattr(sh, "camera", "medium")
                angle = getattr(sh, "angle", "eye_level")
                composition = getattr(sh, "composition", "")

                all_panels.append({
                    "type": "shot",
                    "shot_id": sh_id,
                    "beat_type": getattr(beat_info, "beat_type", "") if beat_info else "",
                    "beat_emotion": getattr(beat_info, "emotion", "neutral") if beat_info else "neutral",
                    "camera": camera,
                    "angle": angle,
                    "composition": composition,
                    "duration": getattr(sh, "duration", 3.0),
                    "action": getattr(sh, "action", "")[:80],
                })

        if not all_panels:
            return ""

        n_panels = len(all_panels)
        cols = min(MAX_COLS, max(n_panels, 1))
        rows = (n_panels + cols - 1) // cols

        canvas_w = MARGIN * 2 + cols * THUMB_WIDTH + (cols - 1) * PANEL_PADDING
        canvas_h = (
            MARGIN * 2 + HEADER_HEIGHT
            + rows * (THUMB_HEIGHT + LABEL_HEIGHT + SECTION_HEIGHT)
            + (rows - 1) * PANEL_PADDING
        )

        canvas = Image.new("RGB", (canvas_w, canvas_h), color=(25, 25, 25))
        draw = ImageDraw.Draw(canvas)

        # Fonts
        try:
            font_title = ImageFont.truetype(self.font_path or "arial.ttf", 28)
            font_section = ImageFont.truetype(self.font_path or "arial.ttf", 18)
            font_label = ImageFont.truetype(self.font_path or "arial.ttf", 14)
            font_small = ImageFont.truetype(self.font_path or "arial.ttf", 12)
        except Exception:
            font_title = ImageFont.load_default()
            font_section = ImageFont.load_default()
            font_label = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # Header
        draw.text(
            (MARGIN, MARGIN + 6),
            f"{chapter_title} — Storyboard",
            fill=(255, 255, 200),
            font=font_title,
        )
        draw.text(
            (MARGIN, MARGIN + 42),
            f"{n_panels} panels across {len(scenes)} scene(s)",
            fill=(180, 180, 180),
            font=font_section,
        )

        # Draw panels
        for i, panel in enumerate(all_panels):
            row = i // cols
            col_idx = i % cols

            px = MARGIN + col_idx * (THUMB_WIDTH + PANEL_PADDING)
            py = MARGIN + HEADER_HEIGHT + row * (THUMB_HEIGHT + LABEL_HEIGHT + SECTION_HEIGHT + PANEL_PADDING)

            if panel["type"] == "scene_header":
                self._draw_scene_header(draw, px, py, THUMB_WIDTH, SECTION_HEIGHT, panel, font_section)
            else:
                self._draw_shot_panel(draw, px, py, THUMB_WIDTH, THUMB_HEIGHT, LABEL_HEIGHT, panel, font_label, font_small)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        canvas.save(output_path, "PNG")
        logger.info(
            f"StoryboardGenerator V2: {n_panels} panels → {output_path} "
            f"({canvas_w}×{canvas_h})"
        )
        return os.path.abspath(output_path)

    def _draw_scene_header(
        self,
        draw: ImageDraw.Draw,
        x: int, y: int, w: int, h: int,
        panel: dict,
        font: ImageFont.FreeTypeFont,
    ):
        """Draw a scene header band showing location/time/weather/mood."""
        # Background band
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=(60, 40, 80), outline=(120, 80, 160), width=1)

        loc = panel.get("location", "")
        t = panel.get("time", "day")
        weather = panel.get("weather", "clear")
        mood = panel.get("mood", "")

        line1 = f"SCENE: {loc}" if loc else "SCENE"
        if t or weather:
            line1 += f" | {t} | {weather}"

        draw.text((x + 6, y + 2), line1, fill=(220, 200, 255), font=font)
        if mood:
            draw.text((x + 6, y + h - 16), f"Mood: {mood}", fill=(180, 160, 220), font=font)

    def _draw_shot_panel(
        self,
        draw: ImageDraw.Draw,
        x: int, y: int, w: int, h: int, label_h: int,
        panel: dict,
        font: ImageFont.FreeTypeFont,
        font_small: ImageFont.FreeTypeFont,
    ):
        """Draw a shot panel with metadata."""
        # Panel background
        draw.rectangle(
            [x, y, x + w - 1, y + h - 1],
            fill=(45, 45, 45),
            outline=(90, 90, 90),
            width=1,
        )

        # Beat type badge
        beat_type = panel.get("beat_type", "")
        if beat_type:
            colors = {
                "dialogue": (60, 60, 180), "action": (180, 80, 40),
                "monologue": (120, 40, 150), "narration": (40, 120, 80),
                "transition": (100, 100, 100),
            }
            badge_color = colors.get(beat_type, (80, 80, 80))
            draw.rectangle([x + 4, y + 4, x + 80, y + 20], fill=badge_color)
            draw.text((x + 8, y + 5), beat_type.upper(), fill=(255, 255, 255), font=font_small)

        # Shot ID
        shot_id = panel.get("shot_id", "")
        draw.text(
            (x + 6, y + 26),
            shot_id,
            fill=(255, 200, 50),
            font=font_small,
        )

        # Camera + angle
        cam_text = f"{panel.get('camera', '')}/{panel.get('angle', '')}"
        draw.text(
            (x + 6, y + 42),
            cam_text,
            fill=(200, 200, 200),
            font=font_small,
        )

        # Composition
        comp = panel.get("composition", "")
        if comp:
            draw.text(
                (x + 6, y + 56),
                comp,
                fill=(160, 160, 180),
                font=font_small,
            )

        # Emotion
        emotion = panel.get("beat_emotion", "neutral")
        draw.text(
            (x + 6, y + 72),
            f"emotion: {emotion}",
            fill=(180, 140, 200),
            font=font_small,
        )

        # Action text
        action = panel.get("action", "")
        if action:
            action = action[:80] + ("..." if len(action) > 80 else "")
            draw.text(
                (x + 6, y + h - 16),
                action,
                fill=(140, 160, 200),
                font=font_small,
            )

        # Label below panel
        label_y = y + h + 4
        dur = panel.get("duration", 3.0)
        label = (
            f"{shot_id} | {panel.get('beat_type', '').upper()[:6]} | "
            f"{panel.get('camera', '')} | {dur:.1f}s"
        )
        draw.text((x, label_y), label, fill=(200, 200, 200), font=font)


# ============================================================
# Convenience functions
# ============================================================

def generate_storyboard(
    project_dir: str,
    chapter_index: int,
    output_dir: str = "",
    chapter_title: str = "",
) -> str:
    """Legacy wrapper — generate storyboard from shot JSON files."""
    import json as _json
    gen = StoryboardGenerator()

    # Look for chapter shots directory
    shots_dir = os.path.join(project_dir, f"ch{chapter_index:02d}", "shots")
    if not os.path.isdir(shots_dir):
        # Try flat structure
        shots_dir = project_dir

    if not os.path.isdir(shots_dir):
        logger.warning(f"Storyboard: shots directory not found: {shots_dir}")
        return ""

    output_path = os.path.join(
        output_dir or project_dir,
        f"storyboard_ch{chapter_index:02d}.png",
    )
    return gen.generate_chapter_storyboard(
        chapter_index=chapter_index,
        shots_dir=shots_dir,
        output_path=output_path,
        chapter_title=chapter_title,
    )


def generate_storyboard_v2(
    story_graph: Any,
    chapters: List[Any],
    output_dir: str,
    image_dir: str = "",
    chapter_index: Optional[int] = None,
) -> List[str]:
    """V2.0 — Generate storyboard from StoryGraph and hierarchical parse.

    Args:
        story_graph: StoryGraph from StoryGraphParser.
        chapters: List[Chapter] from HierarchicalDirector.
        output_dir: Output directory.
        image_dir: Generated image directory.
        chapter_index: Single chapter (1-based) or None for all.

    Returns:
        List of generated PNG paths.
    """
    gen = StoryboardGenerator()
    return gen.generate_from_storygraph(
        story_graph=story_graph,
        chapters=chapters,
        output_dir=output_dir,
        image_dir=image_dir,
        chapter_index=chapter_index,
    )
