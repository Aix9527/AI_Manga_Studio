"""
AI Manga Studio Pro V5 — Character Sheet Generator

Generates consistent character reference images (三身图 / turnaround sheets):
- Front view (正面全身)
- Side view (侧面全身)  
- Back view (背面全身)

Ensures character consistency across all shots by:
1. Building partitioned character DNA from character profiles
2. Generating structured prompts for each view
3. Locking appearance attributes (hair, eyes, clothing, body type)
4. Providing negative prompts to prevent body fragmentation
5. Supporting PuLID/IP-Adapter reference injection
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


# ============================================================
# Constants
# ============================================================

CHARACTER_VIEW_TYPES = ["front", "side", "back"]

# View-specific composition directives (prevents body fragmentation)
VIEW_COMPOSITIONS = {
    "front": (
        "full body front view, standing straight facing forward, "
        "both feet visible, arms at sides, complete body in frame, "
        "no duplicates, no fragmented body parts, clean centered composition, "
        "solo character, full body portrait, waist to head centered"
    ),
    "side": (
        "full body side profile view, standing sideways, "
        "complete body silhouette, both feet visible, "
        "no duplicates, no fragmented body parts, clean centered composition, "
        "solo character, full body side portrait"
    ),
    "back": (
        "full body back view, standing facing away, "
        "complete body visible, both feet visible, "
        "no duplicates, no fragmented body parts, clean centered composition, "
        "solo character, full body back portrait"
    ),
}

# View-specific camera specs
VIEW_CAMERAS = {
    "front": "85mm portrait lens, f/2.8, eye-level angle, shallow DOF",
    "side": "50mm lens, f/2.8, eye-level angle, moderate DOF",
    "back": "50mm lens, f/2.8, eye-level angle, moderate DOF",
}

# Hardened negative prompt for character sheets
CHARACTER_SHEET_NEGATIVE = (
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
    "noise, grain, banding, artifacts, pixelation, "
    "different outfit between views, inconsistent clothing"
)

# Style lock presets
STYLE_LOCKS = {
    "anime": "anime style, cel shading, vibrant colors, clean lineart, masterpiece, best quality, 8K resolution",
    "cinematic": "cinematic film still, anamorphic lens, color graded, film grain, dramatic lighting, 8K, photorealistic",
    "realistic": "photorealistic, detailed skin texture, subsurface scattering, natural lighting, 8K, professional photography",
    "manga": "manga style, black and white, screentone, crosshatching, high contrast, ink lines, dramatic shadows",
    "semi_realistic": "semi-realistic, detailed rendering, soft shading, anime-inspired realism, 8K",
}


# ============================================================
# Data Models
# ============================================================

@dataclass
class CharacterViewPrompt:
    """A single character view prompt (front/side/back)."""
    view_type: str = ""           # front, side, back
    positive_prompt: str = ""
    negative_prompt: str = ""
    camera_spec: str = ""
    composition: str = ""
    character_anchor: str = ""
    quality_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "view_type": self.view_type,
            "positive_prompt": self.positive_prompt,
            "negative_prompt": self.negative_prompt,
            "camera_spec": self.camera_spec,
            "composition": self.composition,
            "character_anchor": self.character_anchor,
            "quality_score": self.quality_score,
        }


@dataclass
class CharacterSheet:
    """Complete character turnaround sheet (三身图)."""
    character_name: str = ""
    character_id: str = ""
    views: List[CharacterViewPrompt] = field(default_factory=list)
    style_lock: str = ""
    seed: int = 0
    resolution: List[int] = field(default_factory=lambda: [1344, 768])
    common_attributes: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "character_name": self.character_name,
            "character_id": self.character_id,
            "views": [v.to_dict() for v in self.views],
            "style_lock": self.style_lock,
            "seed": self.seed,
            "resolution": self.resolution,
            "common_attributes": self.common_attributes,
        }

    def to_json_file(self, filepath: str) -> None:
        """Export character sheet to JSON."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"CharacterSheet: exported to {filepath}")


# ============================================================
# Character Sheet Generator
# ============================================================

class CharacterSheetGenerator:
    """Generates consistent character turnaround sheets (三身图).

    Architecture:
      1. Parse character DNA (appearance attributes)
      2. Build view-specific prompts (front/side/back)
      3. Lock style across all views
      4. Ensure consistency of key attributes (hair, eyes, clothing)
      5. Generate negative prompts to prevent body fragmentation
    """

    def __init__(
        self,
        style: str = "anime",
        style_lock_override: str = "",
        resolution: List[int] = None,
    ):
        self.style = style
        self.style_lock = style_lock_override or STYLE_LOCKS.get(style, STYLE_LOCKS["anime"])
        self.resolution = resolution or [1344, 768]
        logger.info(f"CharacterSheetGenerator initialized (style={style}, resolution={self.resolution})")

    def generate_sheet(
        self,
        character_name: str,
        character_data: Dict[str, Any],
        seed: int = -1,
    ) -> CharacterSheet:
        """Generate a complete character turnaround sheet.

        Args:
            character_name: Character display name.
            character_data: Dict with keys like hair_style, hair_color,
                          eye_color, clothing, body_type, gender, etc.
            seed: Random seed (-1 for random).

        Returns:
            CharacterSheet with front/side/back view prompts.
        """
        sheet = CharacterSheet(
            character_name=character_name,
            character_id=self._make_id(character_name),
            style_lock=self.style_lock,
            seed=seed if seed >= 0 else int(hashlib.sha256(character_name.encode()).hexdigest()[:8], 16) % (2**31),
            resolution=self.resolution,
        )

        # Extract common attributes
        sheet.common_attributes = {
            "gender": character_data.get("gender", "unknown"),
            "hair_style": character_data.get("hair_style", ""),
            "hair_color": character_data.get("hair_color", ""),
            "hair_texture": character_data.get("hair_texture", ""),
            "eye_color": character_data.get("eye_color", ""),
            "eye_shape": character_data.get("eye_shape", ""),
            "face_shape": character_data.get("face_shape", ""),
            "body_type": character_data.get("body_type", ""),
            "height_cm": str(character_data.get("height_cm", "")),
            "clothing": character_data.get("clothing", ""),
            "upper_clothing": character_data.get("upper_clothing", ""),
            "lower_clothing": character_data.get("lower_clothing", ""),
            "footwear": character_data.get("footwear", ""),
            "accessories": character_data.get("accessories", ""),
            "head_accessories": character_data.get("head_accessories", ""),
            "skin_tone": character_data.get("skin_tone", ""),
            "personality": character_data.get("personality", ""),
        }

        # Generate each view
        for view_type in CHARACTER_VIEW_TYPES:
            view_prompt = self._generate_view_prompt(view_type, character_name, sheet.common_attributes)
            sheet.views.append(view_prompt)

        logger.info(
            f"CharacterSheet: generated {len(sheet.views)} views for '{character_name}'"
        )
        return sheet

    def generate_batch(
        self,
        characters: List[Dict[str, Any]],
    ) -> List[CharacterSheet]:
        """Generate character sheets for a list of characters."""
        sheets = []
        for char in characters:
            name = char.get("name", char.get("character_name", "Unknown"))
            data = {
                "gender": char.get("gender", "unknown"),
                "hair_style": char.get("hair_style", ""),
                "hair_color": char.get("hair_color", ""),
                "eye_color": char.get("eye_color", ""),
                "body_type": char.get("body_type", ""),
                "clothing": char.get("clothing", ""),
                "upper_clothing": char.get("upper_clothing", ""),
                "lower_clothing": char.get("lower_clothing", ""),
                "footwear": char.get("footwear", ""),
                "accessories": char.get("accessories", ""),
                "head_accessories": char.get("head_accessories", ""),
                "face_shape": char.get("face_shape", ""),
                "eye_shape": char.get("eye_shape", ""),
                "hair_texture": char.get("hair_texture", ""),
                "skin_tone": char.get("skin_tone", ""),
                "personality": char.get("personality", ""),
            }
            sheets.append(self.generate_sheet(name, data))
        logger.info(f"CharacterSheetGenerator: generated {len(sheets)} character sheets")
        return sheets

    def _generate_view_prompt(
        self,
        view_type: str,
        character_name: str,
        attrs: Dict[str, str],
    ) -> CharacterViewPrompt:
        """Generate a single view prompt (front/side/back)."""
        prompt = CharacterViewPrompt(view_type=view_type)

        # 1. Composition directive
        prompt.composition = VIEW_COMPOSITIONS[view_type]

        # 2. Camera spec
        prompt.camera_spec = VIEW_CAMERAS[view_type]

        # 3. Character anchor (shared across all views)
        parts = self._build_character_anchor(character_name, attrs)
        prompt.character_anchor = parts

        # 4. View-specific modifiers
        view_modifiers = self._get_view_modifiers(view_type, attrs)

        # 5. Assemble positive prompt
        prompt.positive_prompt = self._assemble_positive(
            composition=prompt.composition,
            character_anchor=parts,
            view_modifiers=view_modifiers,
            lighting=self._get_view_lighting(view_type),
            camera=prompt.camera_spec,
            style=self.style_lock,
        )

        # 6. Negative prompt
        prompt.negative_prompt = CHARACTER_SHEET_NEGATIVE

        # 7. Quality check
        prompt.quality_score = self._assess_quality(prompt)

        return prompt

    def _build_character_anchor(
        self,
        name: str,
        attrs: Dict[str, str],
    ) -> str:
        """Build character-first anchor description shared across views."""
        parts = []

        # Gender prefix
        gender = attrs.get("gender", "unknown").lower()
        if gender in ("female", "girl", "woman"):
            parts.append("1girl")
        elif gender in ("male", "boy", "man"):
            parts.append("1boy")
        else:
            parts.append("1character")

        # Name as identifier
        parts.append(f"featuring {name}")

        # Hair
        hair_style = attrs.get("hair_style", "")
        hair_color = attrs.get("hair_color", "")
        hair_texture = attrs.get("hair_texture", "")
        if hair_color:
            parts.append(f"{hair_color} hair")
        if hair_style:
            parts.append(f"{hair_style} hairstyle")
        if hair_texture:
            parts.append(f"{hair_texture} hair texture")

        # Eyes
        eye_color = attrs.get("eye_color", "")
        eye_shape = attrs.get("eye_shape", "")
        if eye_color:
            parts.append(f"{eye_color} eyes")
        if eye_shape:
            parts.append(f"{eye_shape} eye shape")

        # Face
        face_shape = attrs.get("face_shape", "")
        if face_shape:
            parts.append(f"{face_shape} face")

        # Skin
        skin = attrs.get("skin_tone", "")
        if skin:
            parts.append(f"{skin} skin tone")

        # Body type
        body_type = attrs.get("body_type", "")
        if body_type:
            parts.append(f"{body_type} body type")

        # Height
        height = attrs.get("height_cm", "")
        if height:
            parts.append(f"{height}cm tall")

        # Upper clothing
        upper = attrs.get("upper_clothing", "") or attrs.get("clothing", "")
        if upper:
            parts.append(f"wearing {upper}")

        # Lower clothing
        lower = attrs.get("lower_clothing", "")
        if lower:
            parts.append(f"{lower}")

        # Footwear
        footwear = attrs.get("footwear", "")
        if footwear:
            parts.append(f"wearing {footwear}")

        # Accessories
        accessories = attrs.get("accessories", "")
        head_acc = attrs.get("head_accessories", "")
        if head_acc:
            parts.append(f"with {head_acc}")
        if accessories:
            parts.append(f"accessories: {accessories}")

        return ", ".join(parts)

    def _get_view_modifiers(
        self,
        view_type: str,
        attrs: Dict[str, str],
    ) -> List[str]:
        """View-specific modifiers."""
        modifiers = []

        if view_type == "front":
            modifiers.append("facing directly forward, both eyes visible, symmetric pose")
            # Show face details prominently
            eye_color = attrs.get("eye_color", "")
            if eye_color:
                modifiers.append(f"clear {eye_color} eyes visible")

        elif view_type == "side":
            modifiers.append("profile view, side silhouette, one eye visible")
            modifiers.append("showing facial profile, nose and mouth in side view")

        elif view_type == "back":
            modifiers.append("back view, showing back of head and rear clothing")
            # Hair from back
            hair_style = attrs.get("hair_style", "")
            if hair_style:
                modifiers.append(f"{hair_style} hairstyle from behind")

        return modifiers

    def _get_view_lighting(self, view_type: str) -> str:
        """Lighting for character sheet views."""
        lights = {
            "front": "soft studio lighting from front, even illumination, minimal shadows, clean background",
            "side": "soft side lighting from profile direction, gentle shadow on opposite side, clean background",
            "back": "soft backlight from behind, rim light on edges, clean background",
        }
        return lights.get(view_type, lights["front"])

    def _assemble_positive(
        self,
        composition: str,
        character_anchor: str,
        view_modifiers: List[str],
        lighting: str,
        camera: str,
        style: str,
    ) -> str:
        """Assemble the final positive prompt."""
        parts = [
            composition,
            character_anchor,
            ", ".join(view_modifiers),
            lighting,
            camera,
            style,
        ]
        return ", ".join(p for p in parts if p)

    def _assess_quality(self, prompt: CharacterViewPrompt) -> float:
        """Self-assess prompt quality."""
        score = 1.0
        if not prompt.character_anchor:
            score -= 0.3
        if not prompt.composition:
            score -= 0.2
        if len(prompt.positive_prompt) < 50:
            score -= 0.2
        return max(0.0, round(score, 2))

    @staticmethod
    def _make_id(name: str) -> str:
        """Generate a stable character ID from name."""
        return hashlib.md5(name.encode("utf-8")).hexdigest()[:12]
