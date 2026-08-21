"""Prompt Compiler — assembles optimized generation prompts from agent outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Optional
from uuid import uuid4


@dataclass
class CompiledPrompt:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    template_name: str = ""
    positive_prompt: str = ""
    negative_prompt: str = ""
    parameters: dict = field(default_factory=dict)
    source_shot_id: str = ""
    target_node: str = ""      # ComfyUI node name


class PromptCompiler:
    """
    Prompt Compiler — Phase 4 of v0.5 pipeline.

    Takes structured output from Director/Writer/Character agents
    and compiles them into final prompts for ComfyUI generation nodes.

    Supports template-based compilation with context injection.
    """

    def __init__(self):
        self.templates: dict[str, PromptTemplate] = {}
        self.compiled: dict[str, CompiledPrompt] = {}
        self._init_default_templates()

    def _init_default_templates(self):
        """Load default templates on init so compiler works without manual registration."""
        from backend.prompt_compiler.templates import (
            MANGA_PAGE_TEMPLATE, ACTION_TEMPLATE, EMOTION_TEMPLATE,
            BACKGROUND_TEMPLATE, CHARACTER_SHEET_TEMPLATE, COVER_TEMPLATE,
        )
        for t in [MANGA_PAGE_TEMPLATE, ACTION_TEMPLATE, EMOTION_TEMPLATE,
                  BACKGROUND_TEMPLATE, CHARACTER_SHEET_TEMPLATE, COVER_TEMPLATE]:
            self.templates[t.name] = t

    def register_template(self, template: PromptTemplate):
        """Register a prompt template."""
        self.templates[template.name] = template

    def compile_shot(
        self,
        shot_brief,          # ShotBrief from Director
        character_contexts: dict[str, object] = None,  # character_id → CharacterContext
        template_name: str = "manga_page",
    ) -> CompiledPrompt:
        """Compile a full prompt for a single shot."""
        template = self.templates.get(template_name) or self.templates.get("manga_page")
        if template is None:
            raise ValueError(f"No template found for '{template_name}' and fallback 'manga_page' missing")

        shot = shot_brief.shot

        # Assemble context variables
        character_context = self._assemble_character_context(
            shot.character_ids, character_contexts or {}
        )

        variables = {
            "quality_tags": template.quality_tags,
            "scene_description": shot.description[:200] if shot.description else "",
            "character_context": character_context,
            "panel_layout": getattr(shot_brief, 'panel_layout', 'single-panel'),
            "shot_type": shot.shot_type or "medium",
            "camera_angle": (shot_brief.decisions[-1].value
                             if hasattr(shot_brief, 'decisions') and
                                any(getattr(d, 'decision_type', '') == "angle_override" for d in shot_brief.decisions)
                             else getattr(shot, 'camera_angle', 'eye-level')),
            "emotion": getattr(shot, 'emotion', '') or "neutral",
            "mood": getattr(shot, 'emotion', '') or "neutral",
            "action": getattr(shot, 'action', '') or "",
            "dialogue_hint": "yes" if getattr(shot, 'dialogue', '') else "no dialogue",
            "location": getattr(shot, 'location', '') or "",
            "time_of_day": getattr(shot, 'time_of_day', '') or "",
            "details": shot.description[:100] if shot.description else "",
            "title": "",
            "background": "",
        }

        positive = self._fill_template(template.base_template, variables)
        negative = template.negative_prompt

        params = {
            "steps": 20,
            "cfg_scale": 7.0,
            "width": 1024,
            "height": 1536,
            "sampler": "euler_ancestral",
        }

        compiled = CompiledPrompt(
            template_name=template.name,
            positive_prompt=positive,
            negative_prompt=negative,
            parameters=params,
            source_shot_id=shot.id,
        )

        self.compiled[compiled.id] = compiled
        return compiled

    def compile_sequence(
        self,
        briefs: list,          # list[ShotBrief]
        character_contexts: dict[str, object] = None,
    ) -> list[CompiledPrompt]:
        """Compile prompts for a full sequence with appropriate template selection."""
        compiled: list[CompiledPrompt] = []

        for brief in briefs:
            shot = brief.shot

            # Auto-select template based on shot characteristics
            if shot.shot_type in ("close-up", "extreme-close-up") and shot.emotion in ("tense", "dramatic", "dark"):
                template_name = "emotion_shot"
            elif shot.action and len(shot.action) > 20:
                template_name = "action_shot"
            elif not shot.character_ids:
                template_name = "background"
            else:
                template_name = "manga_page"

            cp = self.compile_shot(brief, character_contexts, template_name)
            compiled.append(cp)

        return compiled

    def compile_video_shot(self, shot) -> CompiledPrompt:
        """Compile a motion-safe prompt for image-to-video / FLF2V nodes."""
        positive_parts = [
            getattr(shot, "positive_prompt", "") or getattr(shot, "description", ""),
            getattr(shot, "description", ""),
            getattr(shot, "camera", ""),
            "smooth natural motion, coherent character movement, cinematic temporal continuity",
            "preserve character identity, costume, face and scene layout across frames",
        ]
        negative_parts = [
            getattr(shot, "negative_prompt", ""),
            "jitter, flicker, warping, identity drift, face morphing, extra limbs",
            "mosaic, pixelated blocks, compression artifacts, unintended subtitles, watermark",
        ]
        compiled = CompiledPrompt(
            template_name="video_shot",
            positive_prompt=", ".join(part for part in positive_parts if part),
            negative_prompt=", ".join(part for part in negative_parts if part),
            parameters={"target": "wan_flf2v_or_i2v"},
            source_shot_id=getattr(shot, "id", ""),
            target_node="WanVideoTextEncode",
        )
        self.compiled[compiled.id] = compiled
        return compiled

    def compile_character_sheet(self, character_profile: dict, costume: str = "", expression: str = "neutral") -> CompiledPrompt:
        """Compile a character reference sheet prompt."""
        template = self.templates.get("character_sheet")

        ch = character_profile.get("character", {})
        appearance = ch.get("appearance", "")
        if isinstance(appearance, dict):
            appearance = str(appearance)

        variables = {
            "quality_tags": template.quality_tags,
            "character_name": ch.get("name", ""),
            "gender": ch.get("gender", ""),
            "age": str(ch.get("age", "")),
            "species": ch.get("species", "human"),
            "appearance": appearance,
            "costume": costume or "default outfit",
            "expression": expression,
        }

        return CompiledPrompt(
            template_name="character_sheet",
            positive_prompt=self._fill_template(template.base_template, variables),
            negative_prompt=template.negative_prompt,
            parameters={"steps": 30, "cfg_scale": 7.0, "width": 1024, "height": 1024},
        )

    def compile_cover(
        self,
        title: str,
        main_character_context: str,
        background: str = "",
    ) -> CompiledPrompt:
        """Compile a manga volume cover prompt."""
        template = self.templates.get("cover")

        variables = {
            "quality_tags": template.quality_tags,
            "title": title,
            "character_context": main_character_context,
            "background": background or "dramatic manga background",
        }

        return CompiledPrompt(
            template_name="cover",
            positive_prompt=self._fill_template(template.base_template, variables),
            negative_prompt=template.negative_prompt,
            parameters={"steps": 30, "cfg_scale": 7.5, "width": 1024, "height": 1536},
        )

    # ── Internal ──

    @staticmethod
    def _fill_template(template: str, variables: dict) -> str:
        """Fill template placeholders with variables. Unmatched keys are replaced with ''."""
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{key}}}", str(value))
        # Clean any remaining unfilled {placeholders}
        result = re.sub(r"\{[^}]+\}", "", result)
        return result

    @staticmethod
    def _assemble_character_context(
        character_ids: list[str],
        contexts: dict[str, object],
    ) -> str:
        """Assemble character descriptions from context objects."""
        if not character_ids:
            return ""

        parts: list[str] = []
        for cid in character_ids:
            ctx = contexts.get(cid)
            if ctx and hasattr(ctx, "appearance_summary"):
                parts.append(ctx.appearance_summary)
            else:
                parts.append(f"[Character {cid}]")

        return " | ".join(parts)

    def export_for_comfyui(self, compiled: CompiledPrompt) -> dict:
        """Export compiled prompt to ComfyUI API-compatible format."""
        return {
            "positive": compiled.positive_prompt,
            "negative": compiled.negative_prompt,
            "sampler_params": compiled.parameters,
            "shot_id": compiled.source_shot_id,
        }


# Late import to avoid circular
from backend.prompt_compiler.templates import PromptTemplate, register_default_templates
