"""Prompt Composer (Phase 13.4-A, GPT spec).

Composes Character / World / Shot prompts from the frozen 13.1 data
contracts (CharacterBible v2 / WorldBible v1 / SceneBible v1 / ShotDNA v1).
Consumes these assets read-only; only versioned prompt templates are
written by the Prompt Intelligence service.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.characters.bible_v2.service import CharacterBibleService
from backend.prompt_intelligence.service import PromptIntelligenceService
from backend.shot_dna.library import ShotDNALibrary
from backend.shot_dna.retrieval import ShotDNARetriever
from backend.world.service import WorldService

DEFAULT_TEMPLATES: dict[str, dict[str, str]] = {
    "character": {
        "base_template": (
            "masterpiece, best quality, {character_name}, {appearance}, "
            "wearing {costume}, {expression}, {view} view"
        ),
        "negative_prompt": (
            "blurry, low quality, extra limbs, distorted face, wrong anatomy, "
            "identity drift, watermark, text"
        ),
        "quality_tags": "masterpiece, best quality, cinematic lighting, highly detailed",
    },
    "world": {
        "base_template": (
            "{world_name}, {era}, {technology}, {civilization}, {power_system}, "
            "physics: {physics_rules}; visual style: {visual_style}, color: {color_language}; "
            "scene: {scene_name} at {location}, {time}, {weather}, architecture: {architecture}; "
            "forbidden: {forbidden_elements}; camera: {camera_rules}; lighting: {lighting_rules}"
        ),
        "negative_prompt": (
            "anachronistic objects, modern buildings, wrong era details, "
            "inconsistent color palette, physics violations"
        ),
        "quality_tags": "masterpiece, best quality, consistent world design, cinematic",
    },
    "shot": {
        "base_template": (
            "{prompt_template}, {camera}, lens {lens}, {lighting}, {composition}, "
            "emotion: {emotion}, style: {style}"
        ),
        "negative_prompt": (
            "jitter, flicker, warping, identity drift, face morphing, extra limbs, "
            "mosaic, compression artifacts, unintended subtitles, watermark"
        ),
        "quality_tags": "cinematic, smooth natural motion, temporal continuity",
    },
}


def _fill(template: str, variables: dict[str, str]) -> str:
    result = template
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value))
    return re.sub(r"\{[^}]+\}", "", result)


class PromptComposer:
    """Composes prompts from industrial assets using versioned templates."""

    def __init__(
        self,
        intelligence: PromptIntelligenceService | None = None,
        characters: CharacterBibleService | None = None,
        world: WorldService | None = None,
        shot_dna: ShotDNALibrary | None = None,
        shot_retriever: ShotDNARetriever | None = None,
    ):
        self.intelligence = intelligence or PromptIntelligenceService()
        self.characters = characters or CharacterBibleService()
        self.world = world or WorldService()
        self.shot_dna = shot_dna or ShotDNALibrary()
        self.retriever = shot_retriever or ShotDNARetriever(self.shot_dna)

    # ------------------------------------------------------------- character
    def compose_character(
        self,
        character_id: str,
        asset_type: str = "portrait",
        asset_key: str = "",
    ) -> dict:
        """Compose a character prompt (portrait | view | expression | action)."""
        bible = self.characters.get(character_id)
        if not bible:
            raise KeyError(f"bible not found: {character_id}")
        identity = bible.identity
        approved = next((v for v in bible.versions.values() if v.locked), None) or next(
            (v for v in bible.versions.values() if v.approved), None
        )
        costume = "default outfit"
        if approved and approved.clothing:
            costume = ", ".join(f"{k}: {v}" for k, v in approved.clothing.items())
        appearance = identity.appearance or {}
        appearance_text = str(appearance) if appearance else identity.background

        asset_text = ""
        if asset_type == "view" and asset_key in bible.views:
            asset_text = f"{asset_key} view: {bible.views[asset_key].prompt}"
        elif asset_type == "expression" and asset_key in bible.expressions:
            asset_text = f"expression {asset_key}: {bible.expressions[asset_key].prompt}"
        elif asset_type == "action" and asset_key in bible.actions:
            asset_text = f"action {asset_key}: {bible.actions[asset_key].prompt}"
        elif asset_type == "portrait":
            asset_text = "full character portrait"

        template, version = self._select_template("character")
        positive = _fill(
            template["base_template"],
            {
                "quality_tags": template.get("quality_tags", ""),
                "character_name": identity.name or character_id,
                "appearance": appearance_text,
                "costume": costume,
                "expression": asset_key or "neutral",
                "view": asset_key if asset_type == "view" else "front",
                "asset": asset_text,
            },
        )
        if asset_text and "{asset}" not in template["base_template"]:
            positive = f"{positive}, {asset_text}"
        return self._result(template, version, positive, character_id, asset_type)

    # ------------------------------------------------------------- world
    def compose_world(
        self,
        project_id: str = "",
        world_id: str = "",
        scene_id: str = "",
    ) -> dict:
        """Compose a world / scene environment prompt."""
        world = self.world.get_world(world_id) if world_id else None
        if not world:
            worlds = self.world.list_worlds(project_id)
            if not worlds:
                raise KeyError(f"world not found: project_id={project_id} world_id={world_id}")
            world = worlds[0]
        scene = self.world.get_scene(scene_id) if scene_id else None
        if not scene:
            scenes = self.world.list_scenes(project_id or world.project_id)
            scene = scenes[0] if scenes else None

        scene_vars = {}
        if scene:
            scene_vars = {
                "scene_name": scene.name,
                "location": scene.location,
                "time": scene.time,
                "weather": scene.weather,
                "architecture": scene.architecture,
                "forbidden_elements": ", ".join(scene.forbidden_elements or []),
                "camera_rules": ", ".join(scene.camera_rules or []),
                "lighting_rules": ", ".join(scene.lighting_rules or []),
            }
        scene_vars.setdefault("scene_name", "")
        scene_vars.setdefault("location", "")
        scene_vars.setdefault("time", "")
        scene_vars.setdefault("weather", "")
        scene_vars.setdefault("architecture", "")
        scene_vars.setdefault("forbidden_elements", "")
        scene_vars.setdefault("camera_rules", "")
        scene_vars.setdefault("lighting_rules", "")

        template, version = self._select_template("world")
        positive = _fill(
            template["base_template"],
            {
                "quality_tags": template.get("quality_tags", ""),
                "world_name": world.name,
                "era": world.era,
                "technology": world.technology,
                "civilization": world.civilization,
                "power_system": world.power_system,
                "physics_rules": ", ".join(world.physics_rules or []),
                "visual_style": world.visual_style,
                "color_language": world.color_language,
                **scene_vars,
            },
        )
        return self._result(template, version, positive, world.id, "world")

    # ------------------------------------------------------------- shot
    def compose_shot(
        self,
        dna_id: str = "",
        features: dict[str, Any] | None = None,
        top_k: int = 1,
    ) -> dict:
        """Compose a shot prompt from Shot DNA (by id or feature retrieval)."""
        features = features or {}
        dna = self.shot_dna.get(dna_id) if dna_id else None
        hits = []
        if dna:
            hits = [dna]
        else:
            retrieval = self.retriever.retrieve(
                category=features.get("category", ""),
                scene=features.get("scene", ""),
                emotion=features.get("emotion", ""),
                camera_movement=features.get("camera_movement", ""),
                lighting=features.get("lighting", ""),
                top_k=top_k,
            )
            hits = [hit.dna for hit in retrieval]
        if not hits:
            raise KeyError(f"shot dna not found: dna_id={dna_id} features={features}")
        dna = hits[0]
        camera = dna.camera or {}
        camera_text = ", ".join(f"{k}: {v}" for k, v in camera.items())

        template, version = self._select_template("shot")
        positive = _fill(
            template["base_template"],
            {
                "quality_tags": template.get("quality_tags", ""),
                "prompt_template": dna.prompt_template or dna.scene,
                "camera": camera_text,
                "lens": dna.lens,
                "lighting": dna.lighting,
                "composition": dna.composition,
                "emotion": dna.emotion,
                "style": dna.style,
                "motion": "smooth natural motion, coherent character movement",
            },
        )
        return self._result(template, version, positive, dna.id, "shot")

    # ------------------------------------------------------------- internal
    def _select_template(self, kind: str) -> tuple[dict, str]:
        """Pick the production template for a kind (locked > approved > latest)."""
        templates = self.intelligence.list_templates(kind=kind)
        template_row = None
        version_id = ""
        if templates:
            template_row = templates[0]
            versions = template_row.get("versions", [])
            for version in sorted(versions, key=lambda v: v.get("version_id", "")):
                if version.get("status") == "locked":
                    version_id = version["version_id"]
            if not version_id:
                for version in versions:
                    if version.get("status") == "approved":
                        version_id = version["version_id"]
            if not version_id and versions:
                version_id = versions[-1]["version_id"]
        if not version_id:
            fallback = DEFAULT_TEMPLATES[kind]
            return fallback, ""
        base = next((v["base_template"] for v in versions if v.get("version_id") == version_id), "")
        negative = next((v["negative_prompt"] for v in versions if v.get("version_id") == version_id), "")
        quality = next((v["quality_tags"] for v in versions if v.get("version_id") == version_id), "")
        return {
            "base_template": base or DEFAULT_TEMPLATES[kind]["base_template"],
            "negative_prompt": negative or DEFAULT_TEMPLATES[kind]["negative_prompt"],
            "quality_tags": quality or DEFAULT_TEMPLATES[kind]["quality_tags"],
        }, version_id

    @staticmethod
    def _result(template: dict, version_id: str, positive: str, source_id: str, kind: str) -> dict:
        return {
            "kind": kind,
            "template": template.get("name", kind) if "name" in template else kind,
            "version_id": version_id,
            "positive_prompt": positive,
            "negative_prompt": template.get("negative_prompt", ""),
            "source_id": source_id,
        }