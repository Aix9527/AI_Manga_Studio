"""
AI Manga Studio Pro V1.0 — DNA System

Three immutable DNA layers that define the project's visual identity.
Once set by the project creator, the AI Director must NEVER modify them.

DNA Layers:
  ① Character DNA — Face embedding, Seed, LoRA, IPAdapter, outfits, expressions, voice
  ② Scene DNA    — Architecture, lighting, weather, time-of-day, palette, LUT
  ③ Style DNA    — Art style, color style, cinematography, LUT, lighting rules

Usage:
  dna = DNAManager(project_id=1)
  dna.set_style(art_style="国漫", color_palette="warm")
  dna.set_scene("青云宗大殿", architecture="古风仙侠", lighting="god_rays")
  dna.set_character("林凡", seed=128456, face_embedding_path="linfan.emb")

  # AI Director reads, never writes:
  style = dna.get_style()
  scene = dna.get_scene("青云宗大殿")
  char = dna.get_character("林凡")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ============================================================
# ① Character DNA
# ============================================================

@dataclass
class CharacterDNA:
    """Immutable character identity blueprint.

    Every shot reads this DNA — never reconstructs the character.
    """

    # Core identity
    name: str
    seed: int = 0                    # Layer 1: deterministic seed
    gender: str = "unknown"          # male / female

    # Appearance constants (never change between shots)
    hair_color: str = "black"
    hair_style: str = "long"
    eye_color: str = "black"
    skin_tone: str = "fair"
    body_type: str = "slim"
    height: str = "175cm"
    distinctive_features: str = ""   # scar, mole, tattoo, etc.

    # AI embedding & model binding
    face_embedding_path: str = ""    # .emb / .npy face feature vector
    lora_name: str = ""              # linfan_v2.safetensors
    lora_weight: float = 0.85
    ipadapter_style: str = ""        # PuLID / IPAdapter FaceID / InstantID
    ipadapter_weight: float = 0.9

    # Wardrobe (slot-based)
    default_outfit: str = ""
    outfits: Dict[str, str] = field(default_factory=dict)
    # e.g. {"battle": "黑色战甲", "casual": "白色长袍", "formal": "金色礼服"}

    # Expression library
    default_expression: str = "neutral"
    expressions: Dict[str, str] = field(default_factory=dict)
    # e.g. {"angry": "皱眉 瞪眼", "happy": "微笑 弯眼", "sad": "垂眼 泪光"}

    # Voice
    voice_id: str = ""               # TTS voice model ID
    voice_pitch: float = 1.0
    voice_speed: float = 1.0

    # Metadata
    reference_images: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    # --- Serialization ---
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "seed": self.seed,
            "gender": self.gender,
            "hair_color": self.hair_color,
            "hair_style": self.hair_style,
            "eye_color": self.eye_color,
            "skin_tone": self.skin_tone,
            "body_type": self.body_type,
            "height": self.height,
            "distinctive_features": self.distinctive_features,
            "face_embedding_path": self.face_embedding_path,
            "lora_name": self.lora_name,
            "lora_weight": self.lora_weight,
            "ipadapter_style": self.ipadapter_style,
            "ipadapter_weight": self.ipadapter_weight,
            "default_outfit": self.default_outfit,
            "outfits": self.outfits,
            "default_expression": self.default_expression,
            "expressions": self.expressions,
            "voice_id": self.voice_id,
            "voice_pitch": self.voice_pitch,
            "voice_speed": self.voice_speed,
            "reference_images": self.reference_images,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterDNA":
        return cls(
            name=data.get("name", "unknown"),
            seed=data.get("seed", 0),
            gender=data.get("gender", "unknown"),
            hair_color=data.get("hair_color", "black"),
            hair_style=data.get("hair_style", "long"),
            eye_color=data.get("eye_color", "black"),
            skin_tone=data.get("skin_tone", "fair"),
            body_type=data.get("body_type", "slim"),
            height=data.get("height", "175cm"),
            distinctive_features=data.get("distinctive_features", ""),
            face_embedding_path=data.get("face_embedding_path", ""),
            lora_name=data.get("lora_name", ""),
            lora_weight=data.get("lora_weight", 0.85),
            ipadapter_style=data.get("ipadapter_style", ""),
            ipadapter_weight=data.get("ipadapter_weight", 0.9),
            default_outfit=data.get("default_outfit", ""),
            outfits=data.get("outfits", {}),
            default_expression=data.get("default_expression", "neutral"),
            expressions=data.get("expressions", {}),
            voice_id=data.get("voice_id", ""),
            voice_pitch=data.get("voice_pitch", 1.0),
            voice_speed=data.get("voice_speed", 1.0),
            reference_images=data.get("reference_images", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    # --- Prompt assembly ---
    def appearance_prompt(self, outfit_slot: str = "", expression_slot: str = "") -> str:
        """Build the locked appearance fragment for prompts.

        Args:
            outfit_slot: Outfit slot key (e.g. "battle"), or "" for default.
            expression_slot: Expression slot key (e.g. "angry"), or "" for default.

        Returns:
            Comma-separated visual descriptor string.
        """
        parts = [
            f"{self.gender}" if self.gender != "unknown" else "",
            f"{self.hair_color} {self.hair_style} hair",
            f"{self.eye_color} eyes",
            f"{self.skin_tone} skin",
            f"{self.body_type} body",
        ]
        if self.distinctive_features:
            parts.append(self.distinctive_features)

        # Outfit
        outfit = self.outfits.get(outfit_slot, self.default_outfit)
        if outfit:
            parts.append(outfit)

        # Expression
        expression = self.expressions.get(expression_slot, "")
        if expression:
            parts.append(expression)

        return ", ".join(p for p in parts if p)

    def dna_fingerprint(self) -> str:
        """Short identity hash for logging."""
        return (
            f"[{self.name}] seed={self.seed} "
            f"lora={self.lora_name or 'none'} "
            f"face_emb={'yes' if self.face_embedding_path else 'no'} "
            f"ipa={self.ipadapter_style or 'none'}"
        )


# ============================================================
# ② Scene DNA
# ============================================================

@dataclass
class SceneDNA:
    """Immutable scene location blueprint.

    Once defined, every shot in this scene shares the same
    architecture, lighting, and color rules — across all chapters.
    """

    name: str                       # "青云宗大殿"

    # Architecture
    architecture_style: str = ""     # "古风仙侠", "赛博朋克", "欧洲古典"
    building_material: str = ""     # "白玉石", "钢铁", "木材"
    scale: str = ""                 # "vast hall", "small room", "open courtyard"
    decorations: str = ""           # "floating crystals", "dragon statues"

    # Lighting (fixed for this scene)
    lighting_style: str = ""        # "god_rays", "candlelight", "neon", "overcast"
    light_source: str = ""          # "chandelier", "window", "torch", "skylight"
    light_color: str = ""           # "warm", "cool", "golden", "blue"
    light_intensity: str = ""       # "bright", "dim", "dramatic"

    # Environment
    default_weather: str = ""       # "clear", "rainy", "snow", "fog"
    default_time: str = ""          # "day", "night", "dawn", "dusk"
    season: str = ""                # "spring", "summer", "autumn", "winter"

    # Color palette (scene-specific)
    palette_primary: str = ""       # hex or name, e.g. "#4A90D9"
    palette_secondary: str = ""
    palette_accent: str = ""
    palette_description: str = ""   # "golden and white with blue accents"

    # Camera
    default_lut: str = ""           # "cinematic_warm", "mystic_blue"
    default_fov: str = ""           # "wide", "medium", "narrow"

    # Audio
    ambient_sound: str = ""         # "wind_through_hall", "dripping_water"

    # Metadata
    reference_images: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    # --- Serialization ---
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneDNA":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    # --- Prompt assembly ---
    def environment_prompt(self) -> str:
        """Build the locked environment fragment."""
        parts = []
        if self.architecture_style:
            parts.append(f"{self.architecture_style} {self.name}")
        if self.building_material:
            parts.append(f"{self.building_material} materials")
        if self.scale:
            parts.append(self.scale)
        if self.decorations:
            parts.append(self.decorations)
        if self.lighting_style:
            parts.append(f"{self.lighting_style} lighting")
        if self.light_color:
            parts.append(f"{self.light_color} light")
        if self.light_intensity:
            parts.append(self.light_intensity)
        if self.palette_description:
            parts.append(f"{self.palette_description} palette")
        return ", ".join(parts)

    def dna_fingerprint(self) -> str:
        return (
            f"[{self.name}] arch={self.architecture_style or '?'} "
            f"light={self.lighting_style or '?'} "
            f"palette={self.palette_description or '?'}"
        )


# ============================================================
# ③ Style DNA (Global Project Style)
# ============================================================

@dataclass
class StyleDNA:
    """Immutable project-wide visual style.

    The AI Director must NEVER modify these.
    All shots inherit this style as a base layer.
    """

    # Art direction
    art_style: str = "国漫"        # "国漫", "日漫", "写实", "美漫", "像素"
    sub_style: str = ""            # "水墨", "赛璐璐", "厚涂", "线描"

    # Color system
    color_palette: str = ""        # "warm", "cool", "pastel", "monochrome"
    saturation: str = ""           # "vivid", "natural", "muted", "desaturated"
    contrast: str = ""             # "high", "medium", "low"

    # Cinematography
    lens_language: str = ""        # "cinematic", "anime", "documentary", "surveillance"
    depth_of_field: str = ""       # "shallow", "deep", "tilt-shift"
    camera_movement: str = ""      # "steady", "handheld", "dolly", "drone"

    # Global LUT
    global_lut: str = ""           # path to .cube or name, applied to ALL shots
    lut_intensity: float = 0.8

    # Lighting rules
    light_rules: str = ""          # "rim_light_always", "3_point", "natural"
    rim_light_color: str = ""      # "warm_white", "blue", "gold"
    shadow_style: str = ""         # "soft", "hard", "cel-shaded", "no_shadow"

    # Quality rules
    target_resolution: str = "1920x1080"
    aspect_ratio: str = "16:9"
    fps: int = 24

    # Post-processing
    grain_amount: float = 0.0      # 0 = none
    vignette: bool = False
    bloom: bool = False

    # Reference images (for IPAdapter / ControlNet)
    reference_images: List[str] = field(default_factory=list)

    # Metadata
    created_at: str = ""
    updated_at: str = ""

    # --- Serialization ---
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StyleDNA":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    # --- Prompt assembly ---
    def base_prompt_fragment(self) -> str:
        """Build the global style fragment that prefixes every prompt."""
        parts = [
            f"{self.sub_style} {self.art_style}" if self.sub_style else self.art_style,
            f"{self.saturation} saturation" if self.saturation else "",
            f"{self.contrast} contrast" if self.contrast else "",
            f"{self.lens_language} cinematography" if self.lens_language else "",
            f"{self.depth_of_field} DOF" if self.depth_of_field else "",
            f"{self.light_rules}" if self.light_rules else "",
            f"{self.shadow_style} shadows" if self.shadow_style else "",
        ]
        return ", ".join(p for p in parts if p)

    def anti_style_negative(self) -> str:
        """Build negative prompt fragment to prevent style drift."""
        banned = []
        if self.art_style == "国漫":
            banned.extend(["anime style", "Japanese manga", "western cartoon"])
        elif self.art_style == "日漫":
            banned.extend(["Chinese anime", "realistic", "3D render"])
        elif self.art_style == "写实":
            banned.extend(["anime", "cartoon", "manga style", "illustration"])
        return ", ".join(banned)

    def dna_fingerprint(self) -> str:
        return (
            f"[Style] {self.art_style} | "
            f"colors={self.color_palette or '?'} | "
            f"lut={self.global_lut or 'none'} | "
            f"lights={self.light_rules or '?'}"
        )


# ============================================================
# DNA Manager — Central Registry
# ============================================================

class DNAManager:
    """Central manager for all three DNA layers.

    Reads/writes JSON files in project_dir/dna/.
    All DNA is immutable once set — DNAManager is read-mostly.

    Usage:
        mgr = DNAManager(project_dir="projects/my_manga")
        mgr.set_style(art_style="国漫", color_palette="warm")
        mgr.set_scene("青云宗大殿", architecture_style="古风仙侠")
        mgr.set_character("林凡", seed=128456, lora_name="linfan_v2")

        style = mgr.get_style()       # never modified by AI Director
        scene = mgr.get_scene("青云宗大殿")
        char = mgr.get_character("林凡")
    """

    def __init__(self, project_dir: str = "") -> None:
        """Initialize DNA manager.

        Args:
            project_dir: Root directory of the project.
        """
        self.project_dir = Path(project_dir) if project_dir else Path(".")
        self.dna_dir = self.project_dir / "dna"
        self.dna_dir.mkdir(parents=True, exist_ok=True)

        self._style: Optional[StyleDNA] = None
        self._scenes: Dict[str, SceneDNA] = {}
        self._characters: Dict[str, CharacterDNA] = {}
        self._style_references: Dict[str, StyleDNA] = {}

        self._load_all()

    # ----------------------------------------------------------
    # ③ Style DNA — Global Project Style
    # ----------------------------------------------------------

    def set_style(self, **kwargs) -> StyleDNA:
        """Set or update the global project style.

        Args:
            **kwargs: Any StyleDNA field (art_style, color_palette, etc.)

        Returns:
            The StyleDNA object.
        """
        if self._style is None:
            self._style = StyleDNA(**kwargs)
        else:
            for k, v in kwargs.items():
                if k == "name":
                    continue
                if hasattr(self._style, k) and v:
                    setattr(self._style, k, v)
        self._save_style()
        logger.info(f"DNAManager: Style set → {self._style.dna_fingerprint()}")
        return self._style

    def get_style(self) -> StyleDNA:
        """Get the project style. Returns default if not set."""
        if self._style is None:
            self._style = StyleDNA()  # default
        return self._style

    @property
    def style(self) -> StyleDNA:
        return self.get_style()

    # ----------------------------------------------------------
    # ② Scene DNA — Per-Scene Location
    # ----------------------------------------------------------

    def set_scene(self, name: str, **kwargs) -> SceneDNA:
        """Define or update a scene location.

        Args:
            name: Scene name (unique key, e.g. "青云宗大殿").
            **kwargs: Any SceneDNA field.

        Returns:
            The SceneDNA object.
        """
        if name in self._scenes:
            scene = self._scenes[name]
            for k, v in kwargs.items():
                if hasattr(scene, k) and v:
                    setattr(scene, k, v)
        else:
            kwargs["name"] = name
            scene = SceneDNA(**kwargs)

        self._scenes[name] = scene
        self._save_scenes()
        logger.info(f"DNAManager: Scene '{name}' set → {scene.dna_fingerprint()}")
        return scene

    def get_scene(self, name: str) -> Optional[SceneDNA]:
        """Get a scene by name. Returns None if not found."""
        return self._scenes.get(name)

    def list_scenes(self) -> List[str]:
        """List all defined scene names."""
        return sorted(self._scenes.keys())

    # ----------------------------------------------------------
    # ① Character DNA — Per-Character Identity
    # ----------------------------------------------------------

    def set_character(self, name: str, **kwargs) -> CharacterDNA:
        """Define or update a character's DNA.

        Args:
            name: Character name (unique key, e.g. "林凡").
            **kwargs: Any CharacterDNA field.

        Returns:
            The CharacterDNA object.
        """
        if name in self._characters:
            char = self._characters[name]
            for k, v in kwargs.items():
                if hasattr(char, k) and v:
                    setattr(char, k, v)
        else:
            kwargs["name"] = name
            char = CharacterDNA(**kwargs)

        self._characters[name] = char
        self._save_characters()
        logger.info(f"DNAManager: Character '{name}' set → {char.dna_fingerprint()}")
        return char

    def get_character(self, name: str) -> Optional[CharacterDNA]:
        """Get a character by name. Returns None if not found."""
        return self._characters.get(name)

    def list_characters(self) -> List[str]:
        """List all defined character names."""
        return sorted(self._characters.keys())

    def has_character(self, name: str) -> bool:
        return name in self._characters

    # ----------------------------------------------------------
    # Cross-layer Assembly
    # ----------------------------------------------------------

    def assemble_prompt_context(
        self,
        character_name: str,
        scene_name: str = "",
        outfit_slot: str = "",
        expression_slot: str = "",
    ) -> Dict[str, str]:
        """Assemble a complete prompt from all three DNA layers.

        This is the single entry point for building a shot prompt
        from immutable DNA — the AI Director only adds action/emotion.

        Returns:
            {
                "style_prefix": str,      # Global style (prepended to every prompt)
                "character_block": str,   # Locked character appearance
                "scene_block": str,       # Locked scene environment
                "negative_prefix": str,   # Anti-style-drift negative tokens
            }
        """
        result: Dict[str, str] = {}

        # Layer: Style
        style = self.get_style()
        result["style_prefix"] = style.base_prompt_fragment()
        result["negative_prefix"] = style.anti_style_negative()

        # Layer: Character
        char = self.get_character(character_name)
        if char:
            result["character_block"] = char.appearance_prompt(outfit_slot, expression_slot)
        else:
            result["character_block"] = ""

        # Layer: Scene
        if scene_name:
            scene = self.get_scene(scene_name)
            if scene:
                result["scene_block"] = scene.environment_prompt()
            else:
                result["scene_block"] = ""
        else:
            result["scene_block"] = ""

        return result

    def get_project_config(self) -> Dict[str, Any]:
        """Export the entire DNA as a project config dict."""
        return {
            "style": self._style.to_dict() if self._style else None,
            "scenes": {k: v.to_dict() for k, v in self._scenes.items()},
            "characters": {k: v.to_dict() for k, v in self._characters.items()},
        }

    # ----------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------

    def _style_path(self) -> Path:
        return self.dna_dir / "style.json"

    def _scenes_path(self) -> Path:
        return self.dna_dir / "scenes.json"

    def _characters_path(self) -> Path:
        return self.dna_dir / "characters.json"

    def _load_all(self) -> None:
        """Load all DNA from disk."""
        self._load_style()
        self._load_scenes()
        self._load_characters()
        self._load_style_references()
        logger.debug(
            f"DNAManager: Loaded style={'yes' if self._style else 'no'}, "
            f"scenes={len(self._scenes)}, characters={len(self._characters)}, "
            f"style_refs={len(self._style_references)}"
        )

    def _load_style(self) -> None:
        path = self._style_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._style = StyleDNA.from_dict(data)

    def _load_scenes(self) -> None:
        path = self._scenes_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._scenes = {
                    k: SceneDNA.from_dict(v) for k, v in data.items()
                }

    def _load_characters(self) -> None:
        path = self._characters_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._characters = {
                    k: CharacterDNA.from_dict(v) for k, v in data.items()
                }

    def _save_style(self) -> None:
        if self._style:
            with open(self._style_path(), "w", encoding="utf-8") as f:
                json.dump(self._style.to_dict(), f, ensure_ascii=False, indent=2)

    def _save_scenes(self) -> None:
        with open(self._scenes_path(), "w", encoding="utf-8") as f:
            json.dump(
                {k: v.to_dict() for k, v in self._scenes.items()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _save_characters(self) -> None:
        with open(self._characters_path(), "w", encoding="utf-8") as f:
            json.dump(
                {k: v.to_dict() for k, v in self._characters.items()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def save_all(self) -> None:
        """Force-save all DNA layers to disk."""
        self._save_style()
        self._save_scenes()
        self._save_characters()
        self._save_style_references()
        logger.info("DNAManager: All DNA layers saved to disk")

    # ----------------------------------------------------------
    # Style Reference Images (for IPAdapter)
    # ----------------------------------------------------------

    # Mapping from Chinese directory names to canonical style names
    STYLE_DIR_MAP: Dict[str, str] = {
        "国漫风": "国漫",
        "日漫风": "日漫",
        "韩漫风": "韩漫",
        "电影写实风": "电影写实",
        "游戏CG风（商业级）": "游戏CG",
        "迪士尼动画风": "迪士尼动画",
        "Q版漫画": "Q版漫画",
        "Pixar 风格": "Pixar",
    }

    def import_style_references(self, base_dir: str) -> Dict[str, List[str]]:
        """Scan subdirectories and register reference images to each style's StyleDNA.

        Each subdirectory name is mapped to a canonical style. All image files
        within become that style's reference_images list.

        Args:
            base_dir: Root directory containing style subdirectories
                      (e.g. C:\\Users\\X\\Desktop\\漫剧人物风格\\).

        Returns:
            Dict mapping canonical style name → list of image paths.
        """
        base = Path(base_dir)
        if not base.exists():
            logger.warning(f"DNAManager: Reference base dir not found: {base_dir}")
            return {}

        imported: Dict[str, List[str]] = {}
        image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

        for sub_dir in sorted(base.iterdir()):
            if not sub_dir.is_dir():
                continue

            dir_name = sub_dir.name
            canonical = self.STYLE_DIR_MAP.get(dir_name)
            if canonical is None:
                logger.info(f"DNAManager: Skipping unknown style dir '{dir_name}'")
                continue

            images: List[str] = []
            for f in sorted(sub_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in image_exts:
                    images.append(str(f.resolve()))

            if images:
                style_ref = StyleDNA(art_style=canonical, reference_images=images)
                self._style_references[canonical] = style_ref
                imported[canonical] = images
                logger.info(
                    f"DNAManager: Imported {len(images)} reference images "
                    f"for style '{canonical}' from '{dir_name}'"
                )
            else:
                logger.info(f"DNAManager: No images found in '{dir_name}'")

        self._save_style_references()
        return imported

    def get_style_reference_image(
        self, style_name: str
    ) -> Optional[List[str]]:
        """Get reference image paths for a given canonical style name.

        Args:
            style_name: Canonical style name (e.g. "国漫", "日漫", "韩漫").

        Returns:
            List of absolute image paths, or None if not registered.
        """
        ref = self._style_references.get(style_name)
        if ref and ref.reference_images:
            return ref.reference_images
        return None

    def list_registered_styles(self) -> List[str]:
        """List all style names that have reference images registered."""
        return sorted(self._style_references.keys())

    # ----------------------------------------------------------
    # Persistence — Style References
    # ----------------------------------------------------------

    def _style_references_path(self) -> Path:
        return self.dna_dir / "style_references.json"

    def _save_style_references(self) -> None:
        if not self._style_references:
            return
        with open(self._style_references_path(), "w", encoding="utf-8") as f:
            json.dump(
                {k: v.to_dict() for k, v in self._style_references.items()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _load_style_references(self) -> None:
        path = self._style_references_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._style_references = {
                    k: StyleDNA.from_dict(v) for k, v in data.items()
                }
