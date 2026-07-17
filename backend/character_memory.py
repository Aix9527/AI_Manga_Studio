"""
AI Manga Studio Pro V1.0 — Character Memory

Persistent character memory system that stores and retrieves
character profiles including visual identity (Seed / FaceID / LoRA),
voice settings, and reusable prompt templates.

Design principles:
- Every character is identified by a stable seed for reproducibility.
- FaceID and LoRA paths are tracked to ensure visual consistency.
- Voice ID maps to TTS models (CosyVoice) for dialogue generation.
- Common prompts are cached to accelerate shot-level prompt building.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from backend.database import Character as CharacterORM, get_session


# ============================================================
# Data Class
# ============================================================

@dataclass
class CharacterDNA:
    """V3.5 Enhanced Character DNA with partitioned visual attributes.

    Designed to be populated by CharacterReasoner and consumed
    by ImagePromptBuilder for Flux prompt generation.
    """
    name: str = ""
    # 定性层
    style_framework: str = ""  # Q版/写实/游戏角色等
    # 头部
    hair_style: str = ""
    hair_color: str = ""
    hair_texture: str = ""
    ears: str = ""
    head_accessories: str = ""
    horns: str = ""
    # 面部
    face_shape: str = ""
    eyes: str = ""
    nose: str = ""
    mouth: str = ""
    expression_base: str = ""
    # 上身
    upper_clothing: str = ""
    layers: str = ""
    collar: str = ""
    sleeve: str = ""
    trim_color: str = ""
    # 下身
    lower_clothing: str = ""
    lower_style: str = ""
    # 鞋靴
    footwear: str = ""
    # 飘带/附属
    ribbons_belts: str = ""
    cape_tail: str = ""
    # 配件层
    accessories: List[str] = field(default_factory=list)
    # 质感标签
    quality_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON export."""
        return {
            "name": self.name,
            "style_framework": self.style_framework,
            "hair_style": self.hair_style,
            "hair_color": self.hair_color,
            "hair_texture": self.hair_texture,
            "ears": self.ears,
            "head_accessories": self.head_accessories,
            "horns": self.horns,
            "face_shape": self.face_shape,
            "eyes": self.eyes,
            "nose": self.nose,
            "mouth": self.mouth,
            "expression_base": self.expression_base,
            "upper_clothing": self.upper_clothing,
            "layers": self.layers,
            "collar": self.collar,
            "sleeve": self.sleeve,
            "trim_color": self.trim_color,
            "lower_clothing": self.lower_clothing,
            "lower_style": self.lower_style,
            "footwear": self.footwear,
            "ribbons_belts": self.ribbons_belts,
            "cape_tail": self.cape_tail,
            "accessories": self.accessories,
            "quality_tags": self.quality_tags,
        }

    def to_prompt_fragments(self) -> Dict[str, str]:
        """Generate partitioned prompt fragments for structured prompt assembly.

        Returns dict with keys: head, face, upper_body, lower_body,
        footwear, ribbons, accessories, quality.
        """
        parts: Dict[str, str] = {}

        # Head section
        head_parts = []
        if self.hair_style:
            head_parts.append(f"{self.hair_style}发型")
        if self.hair_color:
            head_parts.append(f"{self.hair_color}色")
        if self.hair_texture:
            head_parts.append(self.hair_texture)
        if self.ears:
            head_parts.append(self.ears)
        if self.head_accessories:
            head_parts.append(self.head_accessories)
        if self.horns:
            head_parts.append(self.horns)
        if head_parts:
            parts["head"] = "，".join(head_parts)

        # Face section
        face_parts = []
        if self.face_shape:
            face_parts.append(self.face_shape)
        if self.eyes:
            face_parts.append(self.eyes)
        if self.nose:
            face_parts.append(self.nose)
        if self.mouth:
            face_parts.append(self.mouth)
        if self.expression_base:
            face_parts.append(self.expression_base)
        if face_parts:
            parts["face"] = "，".join(face_parts)

        # Upper body
        if self.upper_clothing:
            parts["upper_body"] = self.upper_clothing

        # Lower body
        if self.lower_clothing:
            parts["lower_body"] = self.lower_clothing

        # Footwear
        if self.footwear:
            parts["footwear"] = self.footwear

        # Ribbons
        if self.ribbons_belts or self.cape_tail:
            parts["ribbons"] = f"{self.ribbons_belts} {self.cape_tail}".strip()

        # Accessories
        if self.accessories:
            parts["accessories"] = "，".join(self.accessories)

        # Quality tags
        if self.quality_tags:
            parts["quality"] = "，".join(self.quality_tags)

        return parts


@dataclass
class CharacterMemoryEntry:
    """In-memory character profile used during active generation.

    This is the runtime representation; persistence goes through
    the ORM model (CharacterORM).
    """
    name: str
    alias: str = ""
    age: int = 0
    gender: str = "unknown"
    height_cm: float = 0.0
    body_type: str = ""
    hair_style: str = ""
    hair_color: str = ""
    eye_color: str = ""
    clothing: str = ""
    personality: str = ""
    seed: int = 0
    face_id: str = ""
    lora_path: str = ""
    voice_id: str = ""
    voice_model: str = "CosyVoice-300M"
    common_prompt: str = ""
    reference_images: List[str] = field(default_factory=list)
    db_id: Optional[int] = None  # populated after save

    # V3.5 enhanced fields
    hair_texture: str = ""
    ears: str = ""
    horns: str = ""
    head_accessories: str = ""
    upper_clothing: str = ""
    layers: str = ""
    collar: str = ""
    sleeve: str = ""
    trim: str = ""
    ribbons: str = ""
    accessories: str = ""
    quality_tags: str = ""
    char_dna: Optional[CharacterDNA] = None


# ============================================================
# Character Memory Manager
# ============================================================

class CharacterMemory:
    """Manages persistent character profiles across a project.

    Responsibilities:
    - Create / update / delete characters.
    - Generate deterministic seeds from character names.
    - Build reuseable prompt fragments for consistent image generation.
    - Export / import character libraries.
    """

    # Default body type prompt fragments
    BODY_TYPE_PROMPTS: Dict[str, str] = {
        "slim": "slim body, slender figure, lean build",
        "athletic": "athletic build, toned muscles, fit physique",
        "muscular": "muscular build, broad shoulders, strong physique",
        "petite": "petite frame, small stature, delicate build",
        "tall": "tall stature, long limbs, elegant proportions",
        "chubby": "soft features, round face, chubby cheeks",
    }

    # Hair style prompt fragments
    HAIR_STYLE_PROMPTS: Dict[str, str] = {
        "long_straight": "long straight hair flowing down",
        "long_wavy": "long wavy hair, soft curls",
        "short_bob": "short bob cut, neat and clean",
        "ponytail": "high ponytail, energetic look",
        "twin_tails": "twin tails, symmetrical pigtails",
        "buzz_cut": "buzz cut, military style short hair",
        "messy": "messy hair, windswept look",
        "braid": "braided hair, intricate plait",
    }

    def __init__(self, project_id: int = 1, storage_path: str = "") -> None:
        """Initialize character memory for a specific project.

        Args:
            project_id: The database ID of the owning project.
            storage_path: (Deprecated) Kept for backward compatibility.
        """
        self.project_id = project_id
        self._cache: Dict[str, CharacterMemoryEntry] = {}
        self._seed_counter: int = 0
        if storage_path:
            logger.debug(f"CharacterMemory: Ignoring deprecated storage_path='{storage_path}'")

    # ----------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------

    def create_character(
        self,
        name: str,
        alias: str = "",
        age: int = 0,
        gender: str = "unknown",
        height_cm: float = 0.0,
        body_type: str = "",
        hair_style: str = "",
        hair_color: str = "",
        eye_color: str = "",
        clothing: str = "",
        personality: str = "",
        voice_id: str = "",
        voice_model: str = "CosyVoice-300M",
    ) -> CharacterMemoryEntry:
        """Create a new character profile and persist it.

        Args:
            name: Character name.
            alias: Alternate names / nicknames.
            age: Estimated age.
            gender: Male / Female / unknown.
            height_cm: Height in centimeters.
            body_type: Body type keyword.
            hair_style: Hair style keyword.
            hair_color: Hair color.
            eye_color: Eye color.
            clothing: Clothing description.
            personality: Personality traits.
            voice_id: Voice ID for TTS.
            voice_model: TTS model name.

        Returns:
            The created CharacterMemoryEntry.
        """
        # Generate deterministic seed from name
        seed = self._generate_seed(name)
        lora_path = self._build_lora_path(name)
        face_id = self._build_face_id(name)
        common_prompt = self._build_common_prompt(
            name=name,
            gender=gender,
            hair_style=hair_style,
            hair_color=hair_color,
            eye_color=eye_color,
            body_type=body_type,
            clothing=clothing,
        )

        entry = CharacterMemoryEntry(
            name=name,
            alias=alias,
            age=age,
            gender=gender,
            height_cm=height_cm,
            body_type=body_type,
            hair_style=hair_style,
            hair_color=hair_color,
            eye_color=eye_color,
            clothing=clothing,
            personality=personality,
            seed=seed,
            face_id=face_id,
            lora_path=lora_path,
            voice_id=voice_id,
            voice_model=voice_model,
            common_prompt=common_prompt,
        )

        # Persist to database
        session: Session = get_session()
        try:
            orm = CharacterORM(
                project_id=self.project_id,
                name=entry.name,
                alias=entry.alias,
                age=entry.age,
                gender=entry.gender,
                height_cm=entry.height_cm,
                body_type=entry.body_type,
                hair_style=entry.hair_style,
                hair_color=entry.hair_color,
                eye_color=entry.eye_color,
                clothing=entry.clothing,
                personality=entry.personality,
                seed=entry.seed,
                face_id=entry.face_id,
                lora_path=entry.lora_path,
                voice_id=entry.voice_id,
                voice_model=entry.voice_model,
                common_prompt=entry.common_prompt,
            )
            session.add(orm)
            session.commit()
            session.refresh(orm)
            entry.db_id = orm.id
            logger.info(f"CharacterMemory: Created character '{name}' (id={orm.id})")
        except Exception as exc:
            session.rollback()
            logger.error(f"CharacterMemory: Failed to create character '{name}': {exc}")
            raise
        finally:
            session.close()

        self._cache[name] = entry
        return entry

    def get_character(self, name: str) -> Optional[CharacterMemoryEntry]:
        """Retrieve a character profile by name.

        Args:
            name: The exact character name.

        Returns:
            CharacterMemoryEntry if found, None otherwise.
        """
        # Check cache first
        if name in self._cache:
            return self._cache[name]

        # Query database
        session: Session = get_session()
        try:
            orm: Optional[CharacterORM] = (
                session.query(CharacterORM)
                .filter(
                    CharacterORM.project_id == self.project_id,
                    CharacterORM.name == name,
                )
                .first()
            )
            if orm:
                entry = self._orm_to_entry(orm)
                self._cache[name] = entry
                return entry
        finally:
            session.close()

        return None

    def get_all_characters(self) -> List[CharacterMemoryEntry]:
        """Get all characters for the current project.

        Returns:
            List of all CharacterMemoryEntry objects.
        """
        session: Session = get_session()
        try:
            orms = (
                session.query(CharacterORM)
                .filter(CharacterORM.project_id == self.project_id)
                .all()
            )
            entries = [self._orm_to_entry(orm) for orm in orms]
            for entry in entries:
                self._cache[entry.name] = entry
            return entries
        finally:
            session.close()

    def add_character(
        self,
        name: str,
        body_type: str = "",
        hair_style: str = "",
        hair_color: str = "",
        eye_color: str = "",
        clothing: str = "",
        gender: str = "unknown",
        personality: str = "",
        alias: str = "",
        age: int = 0,
        height_cm: float = 0.0,
        voice_id: str = "",
        voice_model: str = "CosyVoice-300M",
    ) -> CharacterMemoryEntry:
        """Convenience wrapper around create_character for the Scheduler.

        Maps the Scheduler's field names to CharacterMemory's create_character API.
        If the character already exists, updates it instead of raising.

        Args:
            name: Character name.
            body_type: Body type (slim, athletic, etc.).
            hair_style: Hair style keyword.
            hair_color: Hair color.
            eye_color: Eye color.
            clothing: Clothing description.
            gender: Gender.
            personality: Personality traits.
            alias: Alternate names.
            age: Age.
            height_cm: Height in cm.
            voice_id: Voice ID.
            voice_model: TTS model name.

        Returns:
            The created or updated CharacterMemoryEntry.
        """
        existing = self.get_character(name)
        if existing:
            logger.debug(f"CharacterMemory: Character '{name}' already exists, updating")
            return self.update_character(
                name=name,
                body_type=body_type or existing.body_type,
                hair_style=hair_style or existing.hair_style,
                hair_color=hair_color or existing.hair_color,
                eye_color=eye_color or existing.eye_color,
                clothing=clothing or existing.clothing,
                gender=gender or existing.gender,
                personality=personality or existing.personality,
                alias=alias or existing.alias,
                age=age or existing.age,
                height_cm=height_cm or existing.height_cm,
                voice_id=voice_id or existing.voice_id,
                voice_model=voice_model or existing.voice_model,
            )

        return self.create_character(
            name=name,
            alias=alias,
            age=age,
            gender=gender,
            height_cm=height_cm,
            body_type=body_type,
            hair_style=hair_style,
            hair_color=hair_color,
            eye_color=eye_color,
            clothing=clothing,
            personality=personality,
            voice_id=voice_id,
            voice_model=voice_model,
        )

    def update_character(self, name: str, **kwargs: Any) -> Optional[CharacterMemoryEntry]:
        """Update fields of an existing character.

        Args:
            name: Character name to update.
            **kwargs: Fields to update.

        Returns:
            Updated CharacterMemoryEntry or None if not found.
        """
        session: Session = get_session()
        try:
            orm: Optional[CharacterORM] = (
                session.query(CharacterORM)
                .filter(
                    CharacterORM.project_id == self.project_id,
                    CharacterORM.name == name,
                )
                .first()
            )
            if not orm:
                logger.warning(f"CharacterMemory: Character '{name}' not found for update")
                return None

            for key, value in kwargs.items():
                if hasattr(orm, key):
                    setattr(orm, key, value)

            # Rebuild common prompt if appearance fields changed
            appearance_fields = {"hair_style", "hair_color", "eye_color", "body_type", "clothing", "gender"}
            if appearance_fields & set(kwargs.keys()):
                orm.common_prompt = self._build_common_prompt(
                    name=orm.name,
                    gender=orm.gender,
                    hair_style=orm.hair_style,
                    hair_color=orm.hair_color,
                    eye_color=orm.eye_color,
                    body_type=orm.body_type,
                    clothing=orm.clothing,
                )

            session.commit()
            session.refresh(orm)
            entry = self._orm_to_entry(orm)
            self._cache[name] = entry
            logger.info(f"CharacterMemory: Updated character '{name}'")
            return entry
        except Exception as exc:
            session.rollback()
            logger.error(f"CharacterMemory: Failed to update character '{name}': {exc}")
            raise
        finally:
            session.close()

    def delete_character(self, name: str) -> bool:
        """Delete a character profile.

        Args:
            name: Character name to delete.

        Returns:
            True if deleted, False if not found.
        """
        session: Session = get_session()
        try:
            orm: Optional[CharacterORM] = (
                session.query(CharacterORM)
                .filter(
                    CharacterORM.project_id == self.project_id,
                    CharacterORM.name == name,
                )
                .first()
            )
            if not orm:
                return False
            session.delete(orm)
            session.commit()
            self._cache.pop(name, None)
            logger.info(f"CharacterMemory: Deleted character '{name}'")
            return True
        except Exception as exc:
            session.rollback()
            logger.error(f"CharacterMemory: Failed to delete character '{name}': {exc}")
            raise
        finally:
            session.close()

    # ----------------------------------------------------------
    # Identity Generation
    # ----------------------------------------------------------

    def _generate_seed(self, name: str) -> int:
        """Generate a deterministic seed from a character name.

        Uses SHA256 hash → truncated integer to ensure the same name
        always produces the same seed across sessions.

        Args:
            name: Character name.

        Returns:
            Integer seed (0 ~ 2^31-1).
        """
        hash_bytes = hashlib.sha256(name.encode("utf-8")).digest()
        seed = int.from_bytes(hash_bytes[:4], "big") % (2**31 - 1)
        return seed

    def _build_face_id(self, name: str) -> str:
        """Build a Face ID reference string.

        In production, this would point to a trained FaceID embedding.
        For now, returns a deterministic path based on the character.

        Args:
            name: Character name.

        Returns:
            Face ID path string.
        """
        safe_name = name.replace(" ", "_").replace("/", "_")
        return f"D:/AI_Manga_Studio/models/faceid/{safe_name}_faceid.pt"

    def _build_lora_path(self, name: str) -> str:
        """Build a LoRA model path for the character.

        Args:
            name: Character name.

        Returns:
            LoRA file path string.
        """
        safe_name = name.replace(" ", "_").replace("/", "_")
        return f"D:/AI_Manga_Studio/models/lora/{safe_name}_character.safetensors"

    # ----------------------------------------------------------
    # Prompt Building
    # ----------------------------------------------------------

    def _build_common_prompt(
        self,
        name: str,
        gender: str,
        hair_style: str,
        hair_color: str,
        eye_color: str,
        body_type: str,
        clothing: str,
    ) -> str:
        """Build a reusable common prompt fragment for the character.

        This prompt is appended to every shot prompt that includes
        this character, ensuring visual consistency.

        Args:
            name: Character name.
            gender: Gender.
            hair_style: Hair style keyword.
            hair_color: Hair color.
            eye_color: Eye color.
            body_type: Body type keyword.
            clothing: Clothing description.

        Returns:
            Common prompt string fragment.
        """
        parts: List[str] = [f"1girl" if gender in ("female", "unknown") else "1boy"]

        # Hair
        hair_desc = self.HAIR_STYLE_PROMPTS.get(hair_style, hair_style)
        if hair_desc:
            parts.append(hair_desc)
        if hair_color:
            parts.append(f"{hair_color} hair")

        # Eyes
        if eye_color:
            parts.append(f"{eye_color} eyes")

        # Body
        body_desc = self.BODY_TYPE_PROMPTS.get(body_type, body_type)
        if body_desc:
            parts.append(body_desc)

        # Clothing
        if clothing:
            parts.append(f"wearing {clothing}")

        return ", ".join(p for p in parts if p)

    def get_character_prompt(self, name: str) -> str:
        """Get the common prompt for a character.

        Args:
            name: Character name.

        Returns:
            Prompt string, or empty string if character not found.
        """
        char = self.get_character(name)
        return char.common_prompt if char else ""

    def get_all_prompts(self) -> Dict[str, str]:
        """Get common prompts for all characters in the project.

        Returns:
            Dict mapping character name → prompt string.
        """
        return {c.name: c.common_prompt for c in self.get_all_characters()}

    def build_multi_character_prompt(self, names: List[str]) -> str:
        """Combine prompts for multiple characters in a single shot.

        Args:
            names: List of character names.

        Returns:
            Combined prompt fragment.
        """
        prompts: List[str] = []
        for i, name in enumerate(names):
            char = self.get_character(name)
            if char:
                gender_prefix = "1girl" if char.gender in ("female", "unknown") else "1boy"
                prompts.append(f"{gender_prefix} ({char.common_prompt})")
        return " and ".join(prompts)

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _orm_to_entry(self, orm: CharacterORM) -> CharacterMemoryEntry:
        """Convert ORM model to runtime entry."""
        return CharacterMemoryEntry(
            name=orm.name,
            alias=orm.alias or "",
            age=orm.age or 0,
            gender=orm.gender or "unknown",
            height_cm=orm.height_cm or 0.0,
            body_type=orm.body_type or "",
            hair_style=orm.hair_style or "",
            hair_color=orm.hair_color or "",
            eye_color=orm.eye_color or "",
            clothing=orm.clothing or "",
            personality=orm.personality or "",
            seed=orm.seed or 0,
            face_id=orm.face_id or "",
            lora_path=orm.lora_path or "",
            voice_id=orm.voice_id or "",
            voice_model=orm.voice_model or "CosyVoice-300M",
            common_prompt=orm.common_prompt or "",
            reference_images=orm.reference_images or [],
            db_id=orm.id,
        )

    def export_to_dict(self) -> Dict[str, Any]:
        """Export all characters to a serializable dict."""
        return {
            "project_id": self.project_id,
            "characters": [
                {
                    "name": c.name,
                    "alias": c.alias,
                    "age": c.age,
                    "gender": c.gender,
                    "height_cm": c.height_cm,
                    "body_type": c.body_type,
                    "hair_style": c.hair_style,
                    "hair_color": c.hair_color,
                    "eye_color": c.eye_color,
                    "clothing": c.clothing,
                    "personality": c.personality,
                    "seed": c.seed,
                    "face_id": c.face_id,
                    "lora_path": c.lora_path,
                    "voice_id": c.voice_id,
                    "voice_model": c.voice_model,
                    "common_prompt": c.common_prompt,
                }
                for c in self.get_all_characters()
            ],
        }

    def export_json(self, filepath: str) -> None:
        """Export characters to a JSON file.

        Args:
            filepath: Destination JSON file path.
        """
        data = self.export_to_dict()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"CharacterMemory: Exported to {filepath}")
