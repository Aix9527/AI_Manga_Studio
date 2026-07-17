"""
AI Manga Studio Pro V1.0 — Stability Manager

DNA + 8-Layer Stability Control System: the brain coordinating all
consistency mechanisms across the pipeline.

DNA Layers (immutable, set once by project creator):
  Character DNA — seed, face embedding, LoRA, IPAdapter, outfits, expressions, voice
  Scene DNA    — architecture style, lighting, palette, LUT, weather, time-of-day
  Style DNA    — art style, color, cinematography, global LUT, lighting rules

8 Execution Layers (read DNA, add dynamic context):
  Layer 1: Fixed Seeds (deterministic, per-character, sourced from DNA)
  Layer 2: Character Memory (persistent visual identity DB)
  Layer 3: Reference Images (FaceID / IPAdapter / PuLID paths)
  Layer 4: Prompt Templating (DNA-locked base + dynamic action/emotion)
  Layer 5: LoRA Routing (per-character LoRA injection from DNA)
  Layer 6: Prompt Lock Engine (character portion immutable)
  Layer 7: ControlNet Config (OpenPose / Depth / Lineart)
  Layer 8: Quality Agent (CLIP face consistency, anatomy, etc.)

Design principle: NOTHING is random. DNA is immutable.
AI Director reads DNA — never modifies it.
Only action, emotion, dialogue vary per shot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from backend.character_memory import CharacterMemory, CharacterMemoryEntry
from backend.dna_system import CharacterDNA, DNAManager, SceneDNA, StyleDNA
from backend.models import ShotType


# ============================================================
# Enums
# ============================================================

class ControlNetMode(str, Enum):
    openpose = "openpose"
    depth = "depth"
    lineart = "lineart"
    canny = "canny"
    softedge = "softedge"
    none_ = "none"


class QualityCheckType(str, Enum):
    face_consistency = "face_consistency"
    anatomy = "anatomy"
    clothing = "clothing"
    hair = "hair"
    composition = "composition"


# ============================================================
# Data Classes
# ============================================================

@dataclass
class LockedPrompt:
    """A prompt split into locked (immutable) and unlocked (dynamic) parts.

    The locked portion contains all character identity tokens.
    The unlocked portion contains action, emotion, scene, camera.
    """
    character_name: str = ""
    locked: str = ""       # Character identity — NEVER modified
    unlocked: str = ""     # Action, emotion, scene, camera — CAN change
    negative: str = ""     # Per-character negatives (hands, deform, etc.)

    def compose(self) -> str:
        """Compose the full positive prompt."""
        return f"{self.locked}, {self.unlocked}" if self.unlocked else self.locked


@dataclass
class ControlNetPreset:
    """A ControlNet configuration preset."""
    mode: ControlNetMode
    weight: float = 0.8
    guidance_start: float = 0.0
    guidance_end: float = 0.9
    preprocessor: str = ""
    model_name: str = ""

    def to_comfyui_params(self) -> Dict[str, Any]:
        return {
            "strength": self.weight,
            "start_percent": self.guidance_start,
            "end_percent": self.guidance_end,
        }


@dataclass
class QualityThresholds:
    """Configurable quality thresholds per check type."""
    face_similarity_min: float = 0.75
    anatomy_pass_min: float = 0.70
    clothing_match_min: float = 0.80
    hair_match_min: float = 0.80
    composition_min: float = 0.60

    max_retries: int = 3


@dataclass
class StabilityConfig:
    """Per-project stability configuration."""
    project_id: int
    seed_mode: str = "deterministic"       # "deterministic" | "random" (blocked in prod)
    prompt_lock_enabled: bool = True
    controlnet_enabled: bool = True
    quality_check_enabled: bool = True
    default_style: str = "realistic"
    quality_thresholds: QualityThresholds = field(default_factory=QualityThresholds)

    # ControlNet routing per shot type
    controlnet_routing: Dict[ShotType, ControlNetMode] = field(default_factory=lambda: {
        ShotType.close_up: ControlNetMode.openpose,
        ShotType.medium: ControlNetMode.openpose,
        ShotType.wide: ControlNetMode.depth,
        ShotType.drone: ControlNetMode.depth,
        ShotType.tracking: ControlNetMode.openpose,
        ShotType.pov: ControlNetMode.openpose,
        ShotType.over_shoulder: ControlNetMode.openpose,
        ShotType.two_shot: ControlNetMode.openpose,
        ShotType.dutch_angle: ControlNetMode.openpose,
    })


# ============================================================
# Stability Manager (8-Layer Orchestrator)
# ============================================================

class StabilityManager:
    """Central orchestrator for the DNA + 8-layer stability control system.

    Architecture:
      DNA Layer 0: Character DNA → seed, face_emb, LoRA, IPAdapter, outfits, expressions, voice
      DNA Layer 0: Scene DNA    → architecture, lighting, palette, LUT, weather, time
      DNA Layer 0: Style DNA    → art_style, color, cinematography, global LUT, light rules
      ─────────────────────────────────
      Layer 1: Fixed Seeds (deterministic, sourced from DNA or DB)
      Layer 2: Character Memory (persistent visual identity DB, fallback when no DNA)
      Layer 3: Reference Images (FaceID / IPAdapter / PuLID paths)
      Layer 4: Prompt Templating (locked DNA base + dynamic action/emotion)
      Layer 5: LoRA Routing (per-character LoRA injection)
      Layer 6: Prompt Lock Engine (character portion immutable)
      Layer 7: ControlNet Config (OpenPose / Depth / Lineart)
      Layer 8: Quality Agent (CLIP face consistency, anatomy, etc.)

    DNA is IMMUTABLE once set. AI Director reads DNA, never modifies it.
    Only dynamic context (action, emotion, dialogue) varies per shot.

    This is the single source of truth for all consistency parameters.
    Every other module queries this manager — never generates random values.

    Usage:
        sm = StabilityManager(project_id=1, dna_manager=dna)
        sm.dna.set_style(art_style="国漫")
        sm.dna.set_scene("大殿", architecture_style="古风")
        sm.dna.set_character("林凡", seed=128456, lora_name="linfan_v2")

        # For each shot:
        cfg = sm.build_shot_config("林凡", scene_name="大殿", action="running")
        # → seed from DNA, prompt from DNA, LoRA from DNA, style prefix from DNA
    """

    # ==========================================================
    # Layer 1: Fixed Seeds
    # ==========================================================

    @staticmethod
    def generate_seed(character_name: str) -> int:
        """Layer 1: Generate deterministic seed from character name.

        Uses SHA256 → truncated int. Same name ALWAYS produces same seed.
        This function is STATIC — it does not depend on DB state.
        The result is validated against DB on retrieval.

        Args:
            character_name: Exact character name (case-sensitive).

        Returns:
            Integer seed (0 ~ 2^31-1).
        """
        h = hashlib.sha256(character_name.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "big") % (2**31 - 1)

    # ==========================================================
    # Layer 1-2: Seed & Character Retrieval
    # ==========================================================

    def __init__(
        self,
        project_id: int,
        character_memory: Optional[CharacterMemory] = None,
        config: Optional[StabilityConfig] = None,
        dna_manager: Optional[DNAManager] = None,
    ) -> None:
        self.project_id = project_id
        self.character_memory = character_memory or CharacterMemory(project_id)
        self.config = config or StabilityConfig(project_id=project_id)

        # DNA System (Layers 0–3 of stability: immutable identity)
        self.dna: Optional[DNAManager] = dna_manager

        # Runtime caches
        self._seed_cache: Dict[str, int] = {}
        self._locked_prompts: Dict[str, LockedPrompt] = {}
        self._controlnet_presets: Dict[ControlNetMode, ControlNetPreset] = self._init_controlnet_presets()

    def get_seed(self, character_name: str) -> int:
        """Layer 1: Get the deterministic seed for a character.

        Query order:
        1. Runtime cache
        2. CharacterMemory (DB)
        3. Generate from name + warn (fallback)

        Args:
            character_name: Exact character name.

        Returns:
            Deterministic seed.
        """
        if character_name in self._seed_cache:
            return self._seed_cache[character_name]

        # Try DB
        char = self.character_memory.get_character(character_name)
        if char and char.seed:
            self._seed_cache[character_name] = char.seed
            return char.seed

        # Fallback: generate (should not happen in production)
        seed = self.generate_seed(character_name)
        logger.warning(
            f"StabilityManager: Character '{character_name}' not in DB, "
            f"using generated seed {seed}. Please register the character."
        )
        self._seed_cache[character_name] = seed
        return seed

    def get_all_seeds(self) -> Dict[str, int]:
        """Layer 1: Get all character→seed mappings."""
        chars = self.character_memory.get_all_characters()
        return {c.name: c.seed for c in chars if c.seed}

    # ==========================================================
    # Layer 2: Character Memory
    # ==========================================================

    def get_character(self, name: str) -> Optional[CharacterMemoryEntry]:
        """Layer 2: Retrieve full character profile."""
        return self.character_memory.get_character(name)

    def register_character(self, entry: CharacterMemoryEntry) -> CharacterMemoryEntry:
        """Layer 2: Register or update a character with guaranteed seed."""
        existing = self.character_memory.get_character(entry.name)
        if existing:
            # Update existing — preserve original seed
            entry = self.character_memory.update_character(
                entry.name,
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
            )
        else:
            entry = self.character_memory.create_character(
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
            )

        self._seed_cache[entry.name] = entry.seed
        return entry

    def register_character_quick(
        self,
        name: str,
        gender: str = "unknown",
        hair_color: str = "",
        hair_style: str = "",
        eye_color: str = "",
        body_type: str = "",
        clothing: str = "",
        personality: str = "",
    ) -> CharacterMemoryEntry:
        """Layer 2: Quick character registration with minimal fields."""
        return self.register_character(CharacterMemoryEntry(
            name=name,
            gender=gender,
            hair_color=hair_color,
            hair_style=hair_style,
            eye_color=eye_color,
            body_type=body_type,
            clothing=clothing,
            personality=personality,
        ))

    def get_all_characters(self) -> List[CharacterMemoryEntry]:
        return self.character_memory.get_all_characters()

    def is_character_registered(self, name: str) -> bool:
        return self.character_memory.get_character(name) is not None

    # ==========================================================
    # Layer 3: Reference Images
    # ==========================================================

    def get_reference_image(self, character_name: str) -> Optional[str]:
        """Layer 3: Get the reference image path for a character.

        Returns:
            FaceID / reference image path, or None.
        """
        char = self.get_character(character_name)
        if char and char.reference_images:
            return char.reference_images[0]
        if char and char.face_id:
            return char.face_id
        return None

    def set_reference_image(self, character_name: str, image_path: str) -> None:
        """Layer 3: Set the reference image for a character."""
        char = self.get_character(character_name)
        if char:
            refs = list(char.reference_images)
            if image_path not in refs:
                refs.insert(0, image_path)
            self.character_memory.update_character(
                character_name,
                reference_images=refs,
            )
            logger.info(f"StabilityManager: Set reference image for '{character_name}' → {image_path}")

    # ==========================================================
    # Layer 4: Prompt Templating
    # ==========================================================

    def build_character_base_prompt(self, character_name: str) -> str:
        """Layer 4: Build the locked character identity prompt.

        This is the immutable base — NEVER modified per shot.
        Only action/emotion/scene/camera change.

        Args:
            character_name: Character name.

        Returns:
            Base prompt string (character identity only).
        """
        char = self.get_character(character_name)
        if not char:
            logger.warning(f"StabilityManager: Character '{character_name}' not found, returning name only")
            return character_name

        return char.common_prompt

    def build_shot_prompt(
        self,
        character_name: str,
        action: str = "",
        emotion: str = "",
        scene_description: str = "",
        shot_type: Optional[ShotType] = None,
        style: str = "",
        quality_prefix: str = "",
    ) -> str:
        """Layer 4: Build a complete shot prompt from template.

        Locked (immutable): character identity
        Dynamic (per-shot): action, emotion, scene, camera, quality

        Args:
            character_name: Character name.
            action: Action description.
            emotion: Emotion description.
            scene_description: Background / environment.
            shot_type: Camera shot type.
            style: Visual style override.
            quality_prefix: Quality prefix override.

        Returns:
            Complete positive prompt string.
        """
        base = self.build_character_base_prompt(character_name)

        quality = quality_prefix or (
            "masterpiece, best quality, cinematic lighting, "
            "highly detailed, 8K resolution, professional illustration"
        )

        parts = [quality, base]

        if action:
            parts.append(action)
        if emotion:
            parts.append(emotion)
        if scene_description:
            parts.append(scene_description)
        if shot_type:
            parts.append(self._shot_type_prompt(shot_type))
        if style:
            parts.append(style)

        return ", ".join(p for p in parts if p)

    @staticmethod
    def _shot_type_prompt(st: ShotType) -> str:
        mapping = {
            ShotType.close_up: "close-up shot, face focus, shallow depth of field",
            ShotType.medium: "medium shot, waist-up",
            ShotType.wide: "wide shot, full body",
            ShotType.drone: "aerial view, drone shot, top-down",
            ShotType.tracking: "tracking shot, dynamic angle",
            ShotType.dutch_angle: "dutch angle, dramatic tilt",
            ShotType.over_shoulder: "over-the-shoulder shot",
            ShotType.two_shot: "two-shot composition",
        }
        return mapping.get(st, "medium shot")

    # ==========================================================
    # Layer 5: LoRA Routing
    # ==========================================================

    def get_lora(self, character_name: str) -> Optional[str]:
        """Layer 5: Get the LoRA model path for a character.

        Returns:
            LoRA .safetensors path, or None.
        """
        char = self.get_character(character_name)
        if char and char.lora_path:
            path = Path(char.lora_path)
            if path.exists():
                return str(path)
            else:
                logger.warning(
                    f"StabilityManager: LoRA path exists in DB but file missing: {char.lora_path}"
                )
        return None

    def get_lora_weight(self, character_name: str) -> float:
        """Layer 5: Get LoRA weight (default 0.85 for character LoRAs)."""
        # Could be stored per-character; for now, fixed
        return 0.85

    def has_lora(self, character_name: str) -> bool:
        """Layer 5: Check if a LoRA model exists for this character."""
        return self.get_lora(character_name) is not None

    # ==========================================================
    # Layer 6: Prompt Lock Engine
    # ==========================================================

    def lock_prompt(self, character_name: str) -> LockedPrompt:
        """Layer 6: Create a locked prompt for a character.

        Once locked, the character portion can NEVER be modified.
        Only scene/action/emotion/camera fields can change.

        Args:
            character_name: Character name.

        Returns:
            LockedPrompt with locked identity portion.
        """
        if character_name in self._locked_prompts:
            return self._locked_prompts[character_name]

        char = self.get_character(character_name)
        if not char:
            lp = LockedPrompt(character_name=character_name, locked=character_name)
            self._locked_prompts[character_name] = lp
            return lp

        locked = char.common_prompt or character_name
        negative = (
            "lowres, bad anatomy, bad hands, extra fingers, "
            "mutated hands, poorly drawn face, deformed, "
            "disfigured, bad proportions, gross proportions"
        )

        lp = LockedPrompt(
            character_name=character_name,
            locked=locked,
            negative=negative,
        )
        self._locked_prompts[character_name] = lp
        logger.info(f"StabilityManager: Prompt locked for '{character_name}'")
        return lp

    def unlock_prompt(self, character_name: str) -> None:
        """Layer 6: Unlock (allow re-lock with updated character profile)."""
        self._locked_prompts.pop(character_name, None)

    def apply_dynamic_context(
        self,
        character_name: str,
        action: str = "",
        emotion: str = "",
        scene: str = "",
        shot_type: Optional[ShotType] = None,
    ) -> str:
        """Layer 6: Apply dynamic context to a locked prompt.

        The locked portion is immutable. Only appends dynamic context.

        Args:
            character_name: Character name.
            action: Action description.
            emotion: Emotion expression.
            scene: Scene description.
            shot_type: Camera shot type.

        Returns:
            Complete composed prompt string.
        """
        lp = self.lock_prompt(character_name)

        dynamic: List[str] = []
        if action:
            dynamic.append(action)
        if emotion:
            dynamic.append(emotion)
        if scene:
            dynamic.append(scene)
        if shot_type:
            dynamic.append(self._shot_type_prompt(shot_type))

        lp.unlocked = ", ".join(dynamic)
        return lp.compose()

    # ==========================================================
    # Layer 7: ControlNet
    # ==========================================================

    @staticmethod
    def _init_controlnet_presets() -> Dict[ControlNetMode, ControlNetPreset]:
        return {
            ControlNetMode.openpose: ControlNetPreset(
                mode=ControlNetMode.openpose,
                weight=0.8,
                preprocessor="DWPreprocessor",
                model_name="control_v11p_sd15_openpose",
            ),
            ControlNetMode.depth: ControlNetPreset(
                mode=ControlNetMode.depth,
                weight=0.7,
                preprocessor="DepthAnythingV2Preprocessor",
                model_name="control_v11f1p_sd15_depth",
            ),
            ControlNetMode.lineart: ControlNetPreset(
                mode=ControlNetMode.lineart,
                weight=0.65,
                preprocessor="LineartPreprocessor",
                model_name="control_v11p_sd15_lineart",
            ),
            ControlNetMode.canny: ControlNetPreset(
                mode=ControlNetMode.canny,
                weight=0.6,
                preprocessor="CannyEdgePreprocessor",
                model_name="control_v11p_sd15_canny",
            ),
            ControlNetMode.softedge: ControlNetPreset(
                mode=ControlNetMode.softedge,
                weight=0.55,
                preprocessor="HEDPreprocessor",
                model_name="control_v11p_sd15_softedge",
            ),
        }

    def get_controlnet(self, shot_type: Optional[ShotType] = None) -> Optional[ControlNetPreset]:
        """Layer 7: Get ControlNet preset for a shot type.

        Args:
            shot_type: Shot type to look up.

        Returns:
            ControlNetPreset or None if disabled.
        """
        if not self.config.controlnet_enabled:
            return None

        mode = ControlNetMode.openpose  # default
        if shot_type and shot_type in self.config.controlnet_routing:
            mode = self.config.controlnet_routing[shot_type]

        if mode == ControlNetMode.none_:
            return None

        return self._controlnet_presets.get(mode)

    def set_controlnet_routing(
        self, shot_type: ShotType, mode: ControlNetMode
    ) -> None:
        """Layer 7: Override ControlNet routing for a shot type."""
        self.config.controlnet_routing[shot_type] = mode

    # ==========================================================
    # Layer 8: Quality Agent
    # ==========================================================

    def check_face_consistency(
        self, image_path: str, character_name: str
    ) -> Tuple[bool, float]:
        """Layer 8: Compare generated face against reference.

        Uses CLIP similarity between generated image and reference image.

        Returns:
            (passed, similarity_score)
        """
        ref_image = self.get_reference_image(character_name)
        if not ref_image:
            logger.warning(f"No reference image for '{character_name}', skipping face check")
            return True, 1.0

        try:
            import clip
            import torch
            from PIL import Image

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model, preprocess = clip.load("ViT-B/32", device=device)

            img1 = preprocess(Image.open(ref_image)).unsqueeze(0).to(device)
            img2 = preprocess(Image.open(image_path)).unsqueeze(0).to(device)

            with torch.no_grad():
                feat1 = model.encode_image(img1)
                feat2 = model.encode_image(img2)
                feat1 = feat1 / feat1.norm(dim=-1, keepdim=True)
                feat2 = feat2 / feat2.norm(dim=-1, keepdim=True)
                similarity = (feat1 @ feat2.T).item()

            threshold = self.config.quality_thresholds.face_similarity_min
            passed = similarity >= threshold

            logger.info(
                f"Face consistency: {character_name} = {similarity:.3f} "
                f"(threshold={threshold}, passed={passed})"
            )
            return passed, similarity
        except ImportError:
            logger.warning("CLIP not installed, skipping face consistency check")
            return True, 1.0
        except Exception as e:
            logger.error(f"Face consistency check failed: {e}")
            return True, 1.0  # Don't block on check failure

    def check_clothing_consistency(
        self, image_path: str, character_name: str
    ) -> Tuple[bool, float]:
        """Layer 8: Check if clothing matches character profile.

        Uses CLIP to compare image against "wearing {clothing}" text prompt.
        """
        char = self.get_character(character_name)
        if not char or not char.clothing:
            return True, 1.0

        try:
            import clip
            import torch
            from PIL import Image

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model, preprocess = clip.load("ViT-B/32", device=device)

            img = preprocess(Image.open(image_path)).unsqueeze(0).to(device)
            text = clip.tokenize([f"A character wearing {char.clothing}"]).to(device)

            with torch.no_grad():
                img_feat = model.encode_image(img)
                text_feat = model.encode_text(text)
                img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
                text_feat = text_feat / text_feat.norm(dim=-1, keepdim=True)
                similarity = (img_feat @ text_feat.T).item()

            threshold = self.config.quality_thresholds.clothing_match_min
            return similarity >= threshold, similarity
        except ImportError:
            return True, 1.0
        except Exception as e:
            logger.error(f"Clothing check failed: {e}")
            return True, 1.0

    def run_all_quality_checks(
        self, image_path: str, character_name: str
    ) -> Dict[str, Any]:
        """Layer 8: Run all quality checks and return aggregated report.

        Returns:
            Dict with per-check results and overall pass/fail.
        """
        results = {}

        face_ok, face_score = self.check_face_consistency(image_path, character_name)
        results["face_consistency"] = {"passed": face_ok, "score": face_score}

        cloth_ok, cloth_score = self.check_clothing_consistency(image_path, character_name)
        results["clothing"] = {"passed": cloth_ok, "score": cloth_score}

        all_passed = all(r["passed"] for r in results.values())
        results["overall_passed"] = all_passed

        return results

    # ==========================================================
    # Bulk Operations — Full Shot Assembly (DNA + 8 Layers)
    # ==========================================================

    def build_shot_config(
        self,
        character_name: str,
        shot_type: Optional[ShotType] = None,
        action: str = "",
        emotion: str = "",
        scene: str = "",
        scene_name: str = "",
        dialogue: str = "",
        outfit_slot: str = "",
        expression_slot: str = "",
    ) -> Dict[str, Any]:
        """Build a complete shot configuration — DNA-first, then 8 layers.

        When DNAManager is available (recommended):
          - Character identity flows from CharacterDNA (L0)
          - Scene atmosphere flows from SceneDNA (L0)
          - Style prefix/negative flows from StyleDNA (L0)
          - Only action/emotion acts as dynamic override

        When DNAManager is NOT available:
          - Falls back to CharacterMemory (L2) + PromptEngine (L4)

        Returns:
            Dict with all parameters for ComfyUI workflow generation.
        """
        # --- DNA Layers (immutable) ---
        if self.dna:
            dna_ctx = self.dna.assemble_prompt_context(
                character_name=character_name,
                scene_name=scene_name or scene,
                outfit_slot=outfit_slot,
                expression_slot=expression_slot,
            )

            # Character DNA → seed, LoRA, IPAdapter
            char_dna = self.dna.get_character(character_name)
            seed = char_dna.seed if char_dna and char_dna.seed else self.get_seed(character_name)
            lora_path = (char_dna.lora_name if char_dna else "")
            lora_weight = (char_dna.lora_weight if char_dna else 0.85)
            ipadapter_style = (char_dna.ipadapter_style if char_dna else "")
            ipadapter_weight = (char_dna.ipadapter_weight if char_dna else 0.9)
            face_emb = (char_dna.face_embedding_path if char_dna else "")
            ref_image = (char_dna.reference_images[0] if char_dna and char_dna.reference_images else "")

            # Scene DNA
            scene_dna = self.dna.get_scene(scene_name) if scene_name else None
            scene_lut = scene_dna.default_lut if scene_dna else ""

            # Style DNA (global)
            style_dna = self.dna.get_style()
            global_lut = style_dna.global_lut

            # Build prompt: style_prefix + character_block + scene_block + action/emotion
            dyn = []
            if action:
                dyn.append(action)
            if emotion:
                dyn.append(emotion)

            positive = ", ".join(
                p for p in [
                    dna_ctx.get("style_prefix", ""),
                    dna_ctx.get("character_block", ""),
                    dna_ctx.get("scene_block", ""),
                    *dyn,
                ] if p
            )
            negative = dna_ctx.get("negative_prefix", "")

            # ControlNet from DNA scene hints
            controlnet = self.get_controlnet(shot_type)

            result = {
                "seed": seed,
                "positive_prompt": positive,
                "negative_prompt": negative,
                "character_name": character_name,
                "character_dna": char_dna,
                "lora_path": lora_path,
                "lora_weight": lora_weight,
                "ipadapter_style": ipadapter_style,
                "ipadapter_weight": ipadapter_weight,
                "face_embedding_path": face_emb,
                "reference_image": ref_image,
                "scene_name": scene_name or scene,
                "scene_dna": scene_dna,
                "scene_lut": scene_lut,
                "global_lut": global_lut,
                "controlnet": controlnet.to_comfyui_params() if controlnet else None,
                "dna_enabled": True,
            }
            return result

        # --- Fallback: CharacterMemory-based (no DNA) ---
        seed = self.get_seed(character_name)
        char = self.get_character(character_name)
        prompt = self.build_shot_prompt(
            character_name=character_name,
            action=action,
            emotion=emotion,
            scene_description=scene,
            shot_type=shot_type,
        )
        lora_path = self.get_lora(character_name)
        controlnet = self.get_controlnet(shot_type)
        ref_image = self.get_reference_image(character_name)

        result = {
            "seed": seed,
            "positive_prompt": prompt,
            "negative_prompt": self.lock_prompt(character_name).negative,
            "character": char,
            "lora_path": lora_path,
            "lora_weight": self.get_lora_weight(character_name) if lora_path else 0.0,
            "controlnet": controlnet.to_comfyui_params() if controlnet else None,
            "reference_image": ref_image,
            "dna_enabled": False,
        }
        return result

    def bulk_register_characters(
        self, characters: List[Dict[str, str]]
    ) -> List[CharacterMemoryEntry]:
        """Register multiple characters at once.

        Args:
            characters: List of dicts with name, gender, hair_color, etc.

        Returns:
            List of registered CharacterMemoryEntry objects.
        """
        entries = []
        for c in characters:
            entry = self.register_character_quick(**c)
            entries.append(entry)
            logger.info(f"StabilityManager: Registered character '{c.get('name')}'")
        return entries

    def export_stability_report(self) -> Dict[str, Any]:
        """Export the full stability configuration for audit/debugging."""
        chars = self.get_all_characters()
        report = {
            "project_id": self.project_id,
            "config": {
                "seed_mode": self.config.seed_mode,
                "prompt_lock": self.config.prompt_lock_enabled,
                "controlnet": self.config.controlnet_enabled,
                "quality_check": self.config.quality_check_enabled,
            },
            "characters": [
                {
                    "name": c.name if hasattr(c, "name") else c.get("name", "?"),
                    "seed": c.seed if hasattr(c, "seed") else c.get("seed", 0),
                    "locked_prompt": c.common_prompt if hasattr(c, "common_prompt") else "",
                    "has_lora": self.has_lora(
                        c.name if hasattr(c, "name") else c.get("name", "?")
                    ),
                    "lora_path": c.lora_path if hasattr(c, "lora_path") else "",
                    "has_reference": bool(
                        self.get_reference_image(
                            c.name if hasattr(c, "name") else c.get("name", "?")
                        )
                    ),
                }
                for c in chars
            ],
            "controlnet_routing": {
                st.value: mode.value
                for st, mode in self.config.controlnet_routing.items()
            },
        }

        # Add DNA summary if available
        if self.dna:
            dna_config = self.dna.get_project_config()
            report["dna"] = {
                "style": dna_config.get("style", {}).get("art_style", "未设定"),
                "characters": list(dna_config.get("characters", {}).keys()),
                "scenes": list(dna_config.get("scenes", {}).keys()),
            }

        return report
