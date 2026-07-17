"""
V3.0 Layer 3 — Character DNA

Character identity definition with visual (face/LoRA/prompt), audio (voice),
and motion attributes. Every shot generation loads CharacterDNA directly
rather than regenerating references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CharacterDNA:
    """Complete character identity definition.

    Visual genes ensure consistent character appearance across all shots.
    Audio genes enable voice cloning. Motion genes define movement style.
    """

    character_id: str
    name: str

    # ── Visual Genes ──────────────────────────────────────
    face_embedding_path: str = ""       # CLIP/IP-Adapter face embedding vector
    lora_path: str = ""                 # Character-specific LoRA weights
    seed: int = 42                      # Fixed seed for deterministic generation
    prompt_template: str = ""           # Base character prompt template
    cfg: float = 7.0                    # Classifier-free guidance scale
    sampler: str = "euler_ancestral"    # Sampler type

    # Appearance
    clothing: str = ""                  # Default outfit description
    hair_style: str = ""                # Hair style
    hair_color: str = ""                # Hair color
    height: str = ""                    # Height (tall/average/short)
    body_type: str = ""                 # Body type (slim/athletic/average/plump)
    skin_tone: str = ""                 # Skin tone
    eye_color: str = ""                 # Eye color

    # ── Audio Genes ───────────────────────────────────────
    voice_id: str = ""                  # CosyVoice / GPT-SoVITS voice ID
    voice_sample_path: str = ""         # Reference audio sample path
    voice_pitch: str = "neutral"        # Pitch bias (low/neutral/high)

    # ── Motion Genes ──────────────────────────────────────
    motion_style: str = ""              # Movement style (elegant/aggressive/gentle/nervous)
    emotion_style: str = ""             # Emotional expression style
    idle_animation: str = ""            # Default idle pose description

    # ── Metadata ──────────────────────────────────────────
    reference_image_paths: list[str] = field(default_factory=list)
    age: str = ""
    gender: str = ""
    role: str = ""                      # protagonist/antagonist/supporting/extra
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "name": self.name,
            "face_embedding_path": self.face_embedding_path,
            "lora_path": self.lora_path,
            "seed": self.seed,
            "prompt_template": self.prompt_template,
            "cfg": self.cfg,
            "sampler": self.sampler,
            "clothing": self.clothing,
            "hair_style": self.hair_style,
            "hair_color": self.hair_color,
            "height": self.height,
            "body_type": self.body_type,
            "skin_tone": self.skin_tone,
            "eye_color": self.eye_color,
            "voice_id": self.voice_id,
            "voice_sample_path": self.voice_sample_path,
            "voice_pitch": self.voice_pitch,
            "motion_style": self.motion_style,
            "emotion_style": self.emotion_style,
            "idle_animation": self.idle_animation,
            "reference_image_paths": self.reference_image_paths,
            "age": self.age,
            "gender": self.gender,
            "role": self.role,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterDNA":
        return cls(
            character_id=data.get("character_id", ""),
            name=data.get("name", ""),
            face_embedding_path=data.get("face_embedding_path", ""),
            lora_path=data.get("lora_path", ""),
            seed=data.get("seed", 42),
            prompt_template=data.get("prompt_template", ""),
            cfg=data.get("cfg", 7.0),
            sampler=data.get("sampler", "euler_ancestral"),
            clothing=data.get("clothing", ""),
            hair_style=data.get("hair_style", ""),
            hair_color=data.get("hair_color", ""),
            height=data.get("height", ""),
            body_type=data.get("body_type", ""),
            skin_tone=data.get("skin_tone", ""),
            eye_color=data.get("eye_color", ""),
            voice_id=data.get("voice_id", ""),
            voice_sample_path=data.get("voice_sample_path", ""),
            voice_pitch=data.get("voice_pitch", "neutral"),
            motion_style=data.get("motion_style", ""),
            emotion_style=data.get("emotion_style", ""),
            idle_animation=data.get("idle_animation", ""),
            reference_image_paths=data.get("reference_image_paths", []),
            age=data.get("age", ""),
            gender=data.get("gender", ""),
            role=data.get("role", ""),
            notes=data.get("notes", ""),
        )

    def get_prompt_context(self) -> str:
        """Build the character portion of a generation prompt.

        Returns a fixed prompt fragment that never changes between shots,
        ensuring character visual consistency.
        """
        parts = []

        if self.prompt_template:
            parts.append(self.prompt_template)
        else:
            parts.append(f"{self.name}")

        if self.clothing:
            parts.append(f"wearing {self.clothing}")
        if self.hair_style:
            parts.append(f"{self.hair_style} hair")
        if self.hair_color:
            parts.append(f"{self.hair_color} hair")
        if self.body_type:
            parts.append(f"{self.body_type} build")

        return ", ".join(parts)

    def get_lora_injection(self) -> str:
        """Get the LoRA injection string for the prompt."""
        if not self.lora_path:
            return ""
        # Extract LoRA name from path for prompt injection
        lora_name = self.lora_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].replace(".safetensors", "")
        return f"<lora:{lora_name}:0.85>"

    def get_negative_traits(self) -> list[str]:
        """Traits that should NOT appear for this character."""
        negative = ["deformed", "bad anatomy", "extra limbs"]
        if self.gender == "male":
            negative.extend(["feminine", "makeup", "lipstick"])
        elif self.gender == "female":
            negative.extend(["beard", "facial hair", "muscular"])
        return negative
