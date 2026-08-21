"""Prompt templates for manga generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class PromptTemplate:
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    name: str = ""
    category: str = ""         # manga_page, character_sheet, bg, sfx, cover
    style: str = "manga"       # manga, manhwa, manhua, webtoon
    quality_tags: str = "masterpiece, best quality, high resolution, detailed"
    negative_prompt: str = "nsfw, low quality, worst quality, bad anatomy, ugly, blurry, jpeg artifacts, watermark, text, signature, deformed, extra limbs, disfigured, fused fingers"
    base_template: str = ""
    created_at: str = ""


# ── Default Templates ──

MANGA_PAGE_TEMPLATE = PromptTemplate(
    name="manga_page",
    category="manga_page",
    style="manga",
    quality_tags="masterpiece, best quality, high resolution, detailed, manga style, black and white manga, screentone, clean linework, dynamic composition",
    negative_prompt="nsfw, low quality, worst quality, photo, realistic, 3d, color, bad anatomy, ugly, blurry, jpeg artifacts, watermark, text, signature",
    base_template="""
[Quality: {quality_tags}]
[Scene: {scene_description}]
[Character: {character_context}]
[Layout: {panel_layout} panels, {shot_type} shot]
[Camera: {camera_angle} angle]
[Emotion/Mood: {emotion}]
[Action: {action}]
[Dialogue Bubbles: {dialogue_hint}]
[Manga Style: black and white, ink wash, cross-hatching, screentone shading]
""".strip(),
)

CHARACTER_SHEET_TEMPLATE = PromptTemplate(
    name="character_sheet",
    category="character_sheet",
    style="manga",
    quality_tags="masterpiece, best quality, high resolution, character reference sheet, full body, turn-around, multiple views, manga style",
    negative_prompt="nsfw, low quality, worst quality, photo, realistic, 3d, ugly, blurry, jpeg artifacts, watermark, signature, cropped, out of frame",
    base_template="""
[Quality: {quality_tags}]
[Subject: {character_name}, {gender}, age {age}, {species}]
[Appearance: {appearance}]
[Clothing: {costume}]
[Views: front view, side view, 3/4 view]
[Expression: {expression}]
[Style: manga reference sheet, clean line art on white background, character turnaround]
""".strip(),
)

BACKGROUND_TEMPLATE = PromptTemplate(
    name="background",
    category="bg",
    style="manga",
    quality_tags="masterpiece, best quality, detailed background, manga style, environmental art",
    negative_prompt="nsfw, low quality, worst quality, photo, realistic, 3d, character, person, people, face, ugly, blurry, jpeg artifacts, watermark",
    base_template="""
[Quality: {quality_tags}]
[Location: {location}]
[Time: {time_of_day}]
[Mood: {mood}]
[Style: manga background, black and white, screentone, detailed linework]
[Perspective: {camera_angle} angle]
[Details: {details}]
""".strip(),
)

COVER_TEMPLATE = PromptTemplate(
    name="cover",
    category="cover",
    style="manga",
    quality_tags="masterpiece, best quality, ultra high resolution, manga cover art, eye-catching composition, dramatic lighting",
    negative_prompt="nsfw, low quality, worst quality, photo, realistic, 3d, ugly, blurry, jpeg artifacts, watermark, text",
    base_template="""
[Quality: {quality_tags}]
[Title: {title}]
[Main Focus: {character_context}]
[Background: {background}]
[Layout: manga volume cover, full page illustration]
[Style: manga cover art with title space, dramatic composition, heavy inking]
""".strip(),
)

ACTION_TEMPLATE = PromptTemplate(
    name="action_shot",
    category="manga_page",
    style="manga",
    quality_tags="masterpiece, best quality, high resolution, action shot, manga style, dynamic pose, motion lines, impact",
    negative_prompt="nsfw, low quality, worst quality, photo, realistic, 3d, stiff, static, ugly, blurry, jpeg artifacts, watermark",
    base_template="""
[Quality: {quality_tags}]
[Character: {character_context}]
[Action: {action} — dynamic motion lines, speed effects]
[Camera: {camera_angle} angle, {shot_type} shot]
[Impact: impact effects, dramatic composition]
[Style: manga action panel, black and white, screentone, motion blur effects]
""".strip(),
)

EMOTION_TEMPLATE = PromptTemplate(
    name="emotion_shot",
    category="manga_page",
    style="manga",
    quality_tags="masterpiece, best quality, high resolution, close-up portrait, manga style, expressive, emotional",
    negative_prompt="nsfw, low quality, worst quality, photo, realistic, 3d, ugly, blurry, jpeg artifacts, watermark",
    base_template="""
[Quality: {quality_tags}]
[Character: {character_context}]
[Expression: {emotion} — detailed facial expression, eyes, mouth, tension lines]
[Camera: {camera_angle}, {shot_type}]
[Lighting: dramatic shadows, contrast]
[Style: manga emotional panel, screentone, detailed facial shading]
""".strip(),
)

DEFAULT_TEMPLATES = [
    MANGA_PAGE_TEMPLATE,
    CHARACTER_SHEET_TEMPLATE,
    BACKGROUND_TEMPLATE,
    COVER_TEMPLATE,
    ACTION_TEMPLATE,
    EMOTION_TEMPLATE,
]


def register_default_templates(compiler) -> None:
    """Register all default templates with a PromptCompiler instance."""
    for template in DEFAULT_TEMPLATES:
        compiler.register_template(template)
