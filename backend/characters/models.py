"""Character data models for v0.5 Character Memory System."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4


@dataclass
class FaceAppearance:
    shape: str = ""           # sharp, round, oval, square, diamond
    skin_tone: str = ""       # pale, fair, tan, dark
    emotion_default: str = "" # cold, warm, neutral, angry, sad
    distinctive: str = ""     # scar, mole, piercing, etc.


@dataclass
class BodyAppearance:
    height: float = 0.0       # cm
    build: str = ""           # slim, athletic, muscular, heavy
    posture: str = ""         # upright, slouched, confident
    distinctive: str = ""     # tattoo, limp, etc.


@dataclass
class HairAppearance:
    style: str = ""           # long, short, tied, braided, etc.
    color: str = ""           # black, brown, blonde, white, etc.
    texture: str = ""         # straight, wavy, curly
    length: str = ""          # description


@dataclass
class Appearance:
    face: FaceAppearance = field(default_factory=FaceAppearance)
    body: BodyAppearance = field(default_factory=BodyAppearance)
    hair: HairAppearance = field(default_factory=HairAppearance)
    eyes: str = ""
    age_apparent: int = 0

    def to_prompt(self) -> str:
        parts = [
            f"{self.age_apparent} years old",
            f"{self.hair.style} {self.hair.color} hair, {self.hair.texture}",
            f"{self.eyes} eyes",
            f"{self.face.shape} face, {self.face.skin_tone} skin",
            f"{self.body.build} build, {self.body.posture} posture",
            f"facial expression: {self.face.emotion_default}",
        ]
        if self.face.distinctive:
            parts.append(f"distinctive: {self.face.distinctive}")
        if self.body.distinctive:
            parts.append(f"distinctive: {self.body.distinctive}")
        return "; ".join(parts)


@dataclass
class Personality:
    traits: list[str] = field(default_factory=list)
    mbti: str = ""
    core_motivation: str = ""
    inner_conflict: str = ""
    speech_style: str = ""    # formal, casual, terse, eloquent
    habits: list[str] = field(default_factory=list)
    fears: list[str] = field(default_factory=list)


@dataclass
class CombatStyle:
    weapon: str = ""
    fighting_style: str = ""
    movement: str = ""        # fast, heavy, agile, precise
    signature_move: str = ""


@dataclass
class Character:
    id: str = field(default_factory=lambda: uuid4().hex[:16])
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    species: str = "human"
    gender: str = ""
    age: int = 0
    role: str = ""            # protagonist, antagonist, supporting, cameo
    archetype: str = ""       # hero, mentor, trickster, etc.

    appearance: Appearance = field(default_factory=Appearance)
    personality: Personality = field(default_factory=Personality)
    combat_style: CombatStyle = field(default_factory=CombatStyle)

    backstory: str = ""
    goal: str = ""
    arc_description: str = ""

    novel_id: str = ""
    chapter_introduced: int = 0
    status: str = "active"    # active, deceased, departed, unknown

    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["appearance"] = json.dumps(self._serialize_appearance())
        d["personality"] = json.dumps(asdict(self.personality))
        d["combat_style"] = json.dumps(asdict(self.combat_style))
        d["aliases"] = json.dumps(self.aliases)
        return d

    def _serialize_appearance(self) -> dict:
        return asdict(self.appearance)

    def to_prompt_context(self) -> str:
        """Generate a prompt-ready character description for image generation."""
        lines = [
            f"Character: {self.name}",
            f"Gender: {self.gender}, Age: {self.age}, Species: {self.species}",
            f"Appearance: {self.appearance.to_prompt()}",
            f"Personality: {', '.join(self.personality.traits)}",
        ]
        if self.combat_style.weapon:
            lines.append(f"Weapon: {self.combat_style.weapon}")
        return "\n".join(lines)


@dataclass
class CharacterTrait:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    character_id: str = ""
    trait_type: str = ""      # personality, physical, behavioral
    name: str = ""
    value: str = ""
    intensity: float = 1.0    # 0.0-1.0
    source_chapter: int = 0
    source_evidence: str = ""


@dataclass
class CharacterImage:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    character_id: str = ""
    image_type: str = ""      # reference, front_view, side_view, expression, costume, full_body
    file_path: str = ""
    prompt_used: str = ""
    generation_params: str = ""
    is_primary: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CharacterCostume:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    character_id: str = ""
    name: str = ""
    description: str = ""
    chapter_range: str = ""   # e.g. "1-5", "6-10"
    season: str = ""
    occasion: str = ""
    image_id: str = ""


@dataclass
class CharacterRelationship:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    character_id: str = ""
    related_id: str = ""
    relation_type: str = ""   # family, friend, enemy, rivalry, mentor, romantic
    description: str = ""
    intensity: float = 1.0    # 0.0-1.0
    chapter_established: int = 0
    history: str = ""


@dataclass
class CharacterEmbedding:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    character_id: str = ""
    embedding_type: str = ""  # visual, textual, multimodal
    model: str = ""           # e.g. "clip-vit-large"
    vector: list[float] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
