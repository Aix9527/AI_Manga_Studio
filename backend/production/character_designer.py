"""Character Designer — Character Reference Image Generation.

Based on the Krene tutorial workflow (Step 03), this module:
1. Generates character design documents from novel text
2. Creates character image generation prompts (tutorial format)
3. Generates reference images via ComfyUI for character consistency
4. Provides reference image paths for downstream storyboard generation

The character reference images are used in the storyboard stage to maintain
character consistency across all shots — a critical requirement from the tutorial.

Tutorial reference:
  https://www.krene.com/blog/ai-video-comic-drama-tutorial
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from backend.production.keyframe_generator import KeyframeGenerator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Character Design Prompt Builder
# ─────────────────────────────────────────────────────────────────────────────

# Style anchors for character design sheets
CHARACTER_STYLE_ANCHOR = (
    "character design sheet, full body character art, concept design, "
    "consistent appearance, same face, detailed features, "
    "clean simple background, centered composition"
)

# Quality boosters for character images
CHARACTER_QUALITY_BOOSTERS = (
    "high detail, cinematic lighting, 4K quality, "
    "professional character design, masterpiece, sharp focus"
)

# Negative prompt for character images
CHARACTER_NEGATIVE_PROMPT = (
    "mosaic, pixelated, blocky, low quality, worst quality, blur, deformed, "
    "disfigured, extra limbs, bad anatomy, malformed hands, duplicate person, "
    "anime, manga, illustration, cartoon, 3d render, plastic skin, doll face, "
    "text, logo, subtitle, watermark, multiple views, split screen, grid layout"
)


class CharacterDesigner:
    """Generates character design documents and reference images.

    Implements the tutorial's Step 03 workflow:
    1. Build character design documents (角色设定文档)
    2. Generate image prompts in tutorial format
    3. Generate reference images via ComfyUI
    4. Store reference image paths for storyboard consistency

    The reference images are passed to downstream stages as
    "character reference" inputs, ensuring the same character renders
    consistently across all shots.
    """

    def __init__(
        self,
        keyframe_gen: Optional[KeyframeGenerator] = None,
        output_root: str = "projects",
    ) -> None:
        self.keyframe_gen = keyframe_gen or KeyframeGenerator()
        self.output_root = Path(output_root)

    async def design_characters(
        self,
        project_id: str,
        characters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Generate character design documents and reference images.

        Args:
            project_id: Project identifier for path resolution.
            characters: List of character dicts with name, role, appearance, etc.
                       Expected fields: name, age_gender, appearance, clothing,
                       personality, behavior, image_prompt.

        Returns:
            List of character dicts with added 'reference_image' field
            pointing to the generated reference image path.
        """
        char_dir = self.output_root / project_id / "outputs" / "characters"
        char_dir.mkdir(parents=True, exist_ok=True)

        results: list[dict[str, Any]] = []

        for char_data in characters:
            name = char_data.get("name", "unknown")
            logger.info("Designing character: %s", name)

            # Build image prompt
            image_prompt = self._build_image_prompt(char_data)

            # Generate reference image
            ref_image_path = char_dir / f"{name}_reference.png"

            success = await self.keyframe_gen.generate_keyframe(
                shot_data={
                    "id": f"char_{name}",
                    "positive_prompt": image_prompt,
                    "negative_prompt": CHARACTER_NEGATIVE_PROMPT,
                    "description": f"Character design: {name}",
                    "camera": "full body, centered, front view",
                    "seed": abs(hash(f"char_{name}")) % 1000000,
                },
                output_path=ref_image_path,
                frame_type="first",
            )

            if success and ref_image_path.exists():
                char_data["reference_image"] = str(ref_image_path)
                logger.info("Character reference image saved: %s", ref_image_path)
            else:
                char_data["reference_image"] = ""
                logger.warning("Failed to generate reference image for %s", name)

            # Store the enhanced prompt
            char_data["enhanced_image_prompt"] = image_prompt

            results.append(char_data)

        # Save character design document
        self._save_design_document(project_id, results)

        return results

    def _build_image_prompt(self, char_data: dict[str, Any]) -> str:
        """Build a character image generation prompt following tutorial format.

        Tutorial format:
          (角色视觉描述)
          (服装描述)
          (姿态与表情)
          (角色气质)
          (用户指定风格)
          角色设计图
          全身立绘
          角色概念设计
          高细节
          电影级光影
          4K
        """
        name = char_data.get("name", "")
        age_gender = char_data.get("age_gender", "")
        appearance = char_data.get("appearance", "")
        clothing = char_data.get("clothing", "")
        personality = char_data.get("personality", "")

        # Visual description (角色视觉描述)
        visual_parts = [p for p in [appearance] if p]
        if age_gender:
            gender_en = "young woman" if "女" in age_gender else "young man" if "男" in age_gender else "person"
            visual_parts.insert(0, gender_en)

        # Pose and expression (姿态与表情)
        pose = "standing pose, neutral expression, facing forward"
        if personality:
            if any(w in personality for w in ["冷静", "沉着", "cool"]):
                pose = "standing pose, calm expression, confident stance"
            elif any(w in personality for w in ["活泼", "active"]):
                pose = "dynamic pose, cheerful expression"
            elif any(w in personality for w in ["阴险", "dangerous"]):
                pose = "standing pose, subtle dangerous smile"

        # Build complete prompt
        parts = [
            ", ".join(visual_parts),  # 角色视觉描述
            clothing or "default clothing",  # 服装描述
            pose,  # 姿态与表情
            CHARACTER_STYLE_ANCHOR,
            CHARACTER_QUALITY_BOOSTERS,
        ]

        # Use existing image_prompt if available, otherwise use built prompt
        existing_prompt = char_data.get("image_prompt", "")
        if existing_prompt:
            # Merge with tutorial format
            parts.insert(0, existing_prompt)

        return ", ".join(p for p in parts if p)

    def _save_design_document(
        self,
        project_id: str,
        characters: list[dict[str, Any]],
    ) -> None:
        """Save the character design document as JSON."""
        doc_path = self.output_root / project_id / "character_design.json"
        doc_path.parent.mkdir(parents=True, exist_ok=True)

        doc = {
            "project_id": project_id,
            "character_count": len(characters),
            "characters": characters,
        }

        doc_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Character design document saved: %s", doc_path)

    def get_reference_image_map(
        self,
        characters: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Build a {character_name: reference_image_path} mapping.

        This map is used by the storyboard stage to inject character reference
        images into shot prompts for consistency.
        """
        ref_map: dict[str, str] = {}
        for char in characters:
            name = char.get("name", "")
            ref_path = char.get("reference_image", "")
            if name and ref_path:
                ref_map[name] = ref_path
        return ref_map

    def inject_reference_into_prompt(
        self,
        prompt: str,
        character_names: list[str],
        ref_map: dict[str, str],
    ) -> str:
        """Inject character reference image hints into a prompt.

        Following the tutorial format, when a character appears in a shot,
        their reference image is noted in the prompt:
          "角色外观参考：参考图像N"

        This ensures the image generation model uses the reference for
        character consistency.
        """
        if not character_names or not ref_map:
            return prompt

        ref_hints: list[str] = []
        for idx, name in enumerate(character_names[:6], start=1):
            if name in ref_map:
                ref_hints.append(f"character reference image {idx}: {name}")

        if ref_hints:
            ref_str = "; ".join(ref_hints)
            return f"{prompt}, {ref_str}"

        return prompt


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────

async def design_characters_for_project(
    project_id: str,
    characters: list[dict[str, Any]],
    output_root: str = "projects",
) -> list[dict[str, Any]]:
    """Convenience wrapper: design characters for a project."""
    designer = CharacterDesigner(output_root=output_root)
    return await designer.design_characters(project_id, characters)
