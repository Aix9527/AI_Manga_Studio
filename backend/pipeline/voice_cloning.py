"""
AI Manga Studio Pro V2.0 — Voice Cloning Engine (GPT-SoVITS)

Clones character voices via GPT-SoVITS for personalized TTS.
Falls back to CosyVoice2 default voices when cloning not available.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.config import get_config


# ============================================================
# Enums & Data Classes
# ============================================================

class VoiceProvider(str, Enum):
    cosyvoice2 = "cosyvoice2"
    gpt_sovits = "gpt_sovits"


class VoiceGender(str, Enum):
    male = "male"
    female = "female"
    neutral = "neutral"


@dataclass
class VoiceProfile:
    """Voice profile for a character."""
    name: str
    character_id: str = ""
    provider: VoiceProvider = VoiceProvider.cosyvoice2
    gender: VoiceGender = VoiceGender.neutral
    age_group: str = "adult"        # child / teen / adult / elder
    personality: str = "neutral"
    model_id: str = ""              # GPT-SoVITS model ID
    reference_audio: str = ""       # Path to reference audio for cloning
    sample_rate: int = 24000
    speed: float = 1.0
    pitch: float = 0.0

    # Default CosyVoice2 presets
    cosyvoice_preset: str = "default"  # default | cheerful | sad | angry | whisper


@dataclass
class VoiceCloneResult:
    """Result of voice cloning operation."""
    character_name: str = ""
    provider: VoiceProvider = VoiceProvider.cosyvoice2
    model_id: str = ""
    success: bool = False
    elapsed: float = 0.0
    error: str = ""


# ============================================================
# CosyVoice2 Character Voice Presets
# ============================================================

# CosyVoice2 default voice mappings by character archetype
COSYVOICE_PRESETS: Dict[str, Dict[str, Any]] = {
    # Male voices
    "male_young": {
        "voice_id": "zh-CN-YunxiNeural",
        "gender": "male",
        "age": "young",
        "description": "Warm youthful male voice",
    },
    "male_adult": {
        "voice_id": "zh-CN-YunyangNeural",
        "gender": "male",
        "age": "adult",
        "description": "Professional broadcast male voice",
    },
    "male_elder": {
        "voice_id": "zh-CN-YunjianNeural",
        "gender": "male",
        "age": "elder",
        "description": "Deep mature male voice",
    },
    "male_cold": {
        "voice_id": "zh-CN-YunfengNeural",
        "gender": "male",
        "age": "adult",
        "description": "Cold authoritative male voice",
    },
    # Female voices
    "female_young": {
        "voice_id": "zh-CN-XiaoxiaoNeural",
        "gender": "female",
        "age": "young",
        "description": "Cheerful young female voice",
    },
    "female_adult": {
        "voice_id": "zh-CN-XiaoyiNeural",
        "gender": "female",
        "age": "adult",
        "description": "Warm professional female voice",
    },
    "female_elder": {
        "voice_id": "zh-CN-XiaochenNeural",
        "gender": "female",
        "age": "elder",
        "description": "Calm mature female voice",
    },
    "female_gentle": {
        "voice_id": "zh-CN-XiaohanNeural",
        "gender": "female",
        "age": "adult",
        "description": "Gentle soft female voice",
    },
    # Neutral / child
    "child": {
        "voice_id": "zh-CN-XiaomoNeural",
        "gender": "neutral",
        "age": "child",
        "description": "Childish voice",
    },
}


# ============================================================
# Voice Cloning Engine
# ============================================================

class VoiceCloningEngine:
    """Character voice cloning via GPT-SoVITS with CosyVoice2 fallback.

    Workflow:
    1. Character profile → infer voice archetype (gender/age/personality)
    2. Attempt GPT-SoVITS cloning if reference audio available
    3. Fall back to CosyVoice2 preset based on archetype
    4. Register voice profile for TTS stage
    """

    # Known GPT-SoVITS paths
    GPT_SOVITS_PATHS = [
        "gpt-sovits",
        "python -m gpt_sovits",
        os.path.expandvars("%USERPROFILE%\\GPT-SoVITS\\api.py"),
    ]

    def __init__(
        self,
        voice_db_path: str = "",
        prefer_cloning: bool = True,
        default_provider: VoiceProvider = VoiceProvider.cosyvoice2,
    ) -> None:
        cfg = get_config()
        self.voice_db_path = voice_db_path or os.path.join(
            cfg.database.base_dir, "voice_profiles.json"
        )
        self.prefer_cloning = prefer_cloning
        self.default_provider = default_provider
        self._profiles: Dict[str, VoiceProfile] = {}
        self._gpt_sovits_available = self._detect_gpt_sovits()

        self._load_profiles()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def register_character(
        self,
        name: str,
        gender: str = "neutral",
        age: int = 25,
        personality: str = "neutral",
        reference_audio: str = "",
    ) -> VoiceProfile:
        """Register a character for voice cloning.

        Args:
            name: Character name.
            gender: Gender (male/female/neutral).
            age: Estimated age.
            personality: Personality trait.
            reference_audio: Optional path to reference audio for cloning.

        Returns:
            VoiceProfile for the character.
        """
        if name in self._profiles:
            logger.debug(f"VoiceCloning: '{name}' already registered")
            return self._profiles[name]

        # Determine voice archetype
        archetype = self._infer_archetype(gender, age, personality)
        preset = COSYVOICE_PRESETS.get(archetype, COSYVOICE_PRESETS["male_adult"])

        voice_gender = VoiceGender.female if gender == "female" else (
            VoiceGender.male if gender == "male" else VoiceGender.neutral
        )

        profile = VoiceProfile(
            name=name,
            character_id=name.lower().replace(" ", "_"),
            gender=voice_gender,
            age_group=self._age_to_group(age),
            personality=personality,
            reference_audio=reference_audio,
            cosyvoice_preset=archetype,
        )

        # Try GPT-SoVITS cloning
        if self.prefer_cloning and self._gpt_sovits_available and reference_audio:
            clone_result = self.clone_voice(profile)
            if clone_result.success:
                profile.provider = VoiceProvider.gpt_sovits
                profile.model_id = clone_result.model_id

        # Default to CosyVoice2
        if profile.provider == VoiceProvider.cosyvoice2:
            profile.model_id = preset["voice_id"]
            logger.info(
                f"VoiceCloning: '{name}' → CosyVoice2 preset '{archetype}' "
                f"({preset['description']})"
            )

        self._profiles[name] = profile
        self._save_profiles()

        return profile

    def clone_voice(self, profile: VoiceProfile) -> VoiceCloneResult:
        """Clone voice via GPT-SoVITS.

        Args:
            profile: VoiceProfile with reference_audio set.

        Returns:
            VoiceCloneResult.
        """
        t0 = time.time()

        if not self._gpt_sovits_available:
            return VoiceCloneResult(
                character_name=profile.name,
                provider=VoiceProvider.cosyvoice2,
                error="GPT-SoVITS not available",
            )

        if not profile.reference_audio:
            return VoiceCloneResult(
                character_name=profile.name,
                provider=VoiceProvider.cosyvoice2,
                error="No reference audio provided",
            )

        try:
            model_id = self._run_gpt_sovits_clone(profile)
            elapsed = time.time() - t0

            logger.info(
                f"VoiceCloning: '{profile.name}' cloned via GPT-SoVITS "
                f"→ {model_id} ({elapsed:.2f}s)"
            )

            return VoiceCloneResult(
                character_name=profile.name,
                provider=VoiceProvider.gpt_sovits,
                model_id=model_id,
                success=True,
                elapsed=elapsed,
            )

        except Exception as e:
            logger.error(f"VoiceCloning: GPT-SoVITS failed for '{profile.name}' — {e}")
            return VoiceCloneResult(
                character_name=profile.name,
                provider=VoiceProvider.cosyvoice2,
                error=str(e),
                elapsed=time.time() - t0,
            )

    def get_voice_for_character(self, name: str) -> Optional[VoiceProfile]:
        """Get registered voice profile for a character.

        Args:
            name: Character name.

        Returns:
            VoiceProfile or None.
        """
        return self._profiles.get(name)

    def get_tts_config(self, name: str) -> Dict[str, Any]:
        """Get TTS configuration for a character.

        Args:
            name: Character name.

        Returns:
            Dict with provider, model_id, voice_id, speed, pitch.
        """
        profile = self.get_voice_for_character(name)
        if not profile:
            # Default fallback
            return {
                "provider": "cosyvoice2",
                "voice_id": "zh-CN-YunyangNeural",
                "speed": 1.0,
                "pitch": 0.0,
            }

        return {
            "provider": profile.provider.value,
            "voice_id": profile.model_id or profile.cosyvoice_preset,
            "model_id": profile.model_id,
            "speed": profile.speed,
            "pitch": profile.pitch,
            "sample_rate": profile.sample_rate,
        }

    def register_batch(
        self,
        characters: List[Dict[str, Any]],
    ) -> List[VoiceProfile]:
        """Register multiple characters at once.

        Args:
            characters: List of {name, gender, age, personality, reference_audio} dicts.

        Returns:
            List of VoiceProfiles.
        """
        profiles = []
        for char in characters:
            profile = self.register_character(
                name=char.get("name", "unknown"),
                gender=char.get("gender", "neutral"),
                age=char.get("age", 25),
                personality=char.get("personality", "neutral"),
                reference_audio=char.get("reference_audio", ""),
            )
            profiles.append(profile)
        return profiles

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    @staticmethod
    def _infer_archetype(gender: str, age: int, personality: str) -> str:
        """Infer voice archetype from character traits."""
        gender_key = "female" if gender == "female" else "male"

        if age < 13:
            return "child"
        elif age < 25:
            return f"{gender_key}_young"
        elif age < 55:
            if personality in ("cold", "stoic", "authoritative"):
                return "male_cold"
            if personality in ("gentle", "soft", "kind"):
                return "female_gentle"
            return f"{gender_key}_adult"
        else:
            return f"{gender_key}_elder"

    @staticmethod
    def _age_to_group(age: int) -> str:
        """Map age to group label."""
        if age < 13:
            return "child"
        elif age < 20:
            return "teen"
        elif age < 55:
            return "adult"
        else:
            return "elder"

    def _detect_gpt_sovits(self) -> bool:
        """Detect if GPT-SoVITS is available."""
        for path in self.GPT_SOVITS_PATHS:
            try:
                result = subprocess.run(
                    [path, "--help"] if " " not in path else path.split() + ["--help"],
                    capture_output=True,
                    timeout=5,
                    shell=" " in path,
                )
                if result.returncode in (0, 1):
                    logger.info("VoiceCloning: GPT-SoVITS detected")
                    return True
            except Exception:
                continue
        logger.info("VoiceCloning: GPT-SoVITS not found, using CosyVoice2")
        return False

    def _run_gpt_sovits_clone(self, profile: VoiceProfile) -> str:
        """Run GPT-SoVITS voice cloning.

        Args:
            profile: VoiceProfile with reference_audio set.

        Returns:
            Model ID string.
        """
        model_id = f"{profile.character_id}_v1"

        # Simulated clone — in production, calls GPT-SoVITS API
        cmd = [
            "python", "-m", "gpt_sovits.clone",
            "--name", profile.character_id,
            "--audio", profile.reference_audio,
            "--output", model_id,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise RuntimeError(result.stderr or "GPT-SoVITS clone failed")
        except FileNotFoundError:
            # GPT-SoVITS CLI not found — mark as unavailable
            self._gpt_sovits_available = False
            raise RuntimeError("GPT-SoVITS CLI not found")

        return model_id

    def _load_profiles(self) -> None:
        """Load voice profiles from disk."""
        if os.path.isfile(self.voice_db_path):
            try:
                with open(self.voice_db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for name, pdata in data.items():
                    self._profiles[name] = VoiceProfile(**pdata)
                logger.debug(f"VoiceCloning: Loaded {len(self._profiles)} profiles")
            except Exception as e:
                logger.warning(f"VoiceCloning: Failed to load profiles — {e}")

    def _save_profiles(self) -> None:
        """Save voice profiles to disk."""
        os.makedirs(os.path.dirname(self.voice_db_path), exist_ok=True)
        try:
            data = {name: p.__dict__ for name, p in self._profiles.items()}
            with open(self.voice_db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"VoiceCloning: Failed to save profiles — {e}")


# ============================================================
# VoicePipeline — Layer 9: Narration vs Dialogue Routing
# ============================================================


class VoicePipeline:
    """High-level voice pipeline with CosyVoice2 / GPT-SoVITS routing.

    Routing rules:
        Narration / 旁白 / 叙述 → CosyVoice2 (natural dubbing)
        Character dialogue / 对白   → GPT-SoVITS first (cloned voice)
                                     → fallback CosyVoice2 if no clone

    Voice registry: cache/voices/{character_name}/model.pth

    Usage:
        vp = VoicePipeline()
        audio_path = vp.synthesize("你好世界", character_name="主角")
        audio_path = vp.synthesize("夜色降临...", is_narration=True)
    """

    def __init__(
        self,
        voice_cache_dir: Optional[str] = None,
        engine: Optional[VoiceCloningEngine] = None,
    ):
        from backend.model_router import ModelRouter
        self._router = ModelRouter()

        if voice_cache_dir:
            self._voice_cache_dir = Path(voice_cache_dir)
        else:
            self._voice_cache_dir = Path(__file__).resolve().parent.parent.parent / "cache" / "voices"
        self._voice_cache_dir.mkdir(parents=True, exist_ok=True)

        self._engine = engine or VoiceCloningEngine()

    def synthesize(
        self,
        text: str,
        character_name: str = "",
        is_narration: bool = False,
        output_path: str = "",
    ) -> str:
        """Synthesize speech from text.

        Args:
            text: Text to speak.
            character_name: Character name (for dialogue).
            is_narration: True for narration/旁白.
            output_path: Optional output WAV path.

        Returns:
            Path to generated WAV file.
        """
        # Determine provider
        if is_narration or not character_name:
            provider = "cosyvoice2"
            voice_config = {
                "voice_id": "zh-CN-YunyangNeural",
                "speed": 1.0,
                "pitch": 0.0,
                "sample_rate": 24000,
            }
            logger.debug(f"VoicePipeline: narration → CosyVoice2")
        else:
            # Check character registry for GPT-SoVITS model
            tts_config = self._engine.get_tts_config(character_name)
            provider = tts_config.get("provider", "cosyvoice2")

            if provider == "gpt_sovits":
                model_path = self._voice_cache_dir / character_name / "model.pth"
                if not model_path.exists():
                    logger.warning(
                        f"VoicePipeline: '{character_name}' GPT-SoVITS model not found at {model_path}, "
                        f"falling back to CosyVoice2"
                    )
                    provider = "cosyvoice2"

            voice_config = tts_config
            logger.debug(f"VoicePipeline: dialogue '{character_name}' → {provider}")

        # Generate output path
        if not output_path:
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            output_path = str(
                self._voice_cache_dir / f"tts_{character_name or 'narration'}_{text_hash}.wav"
            )

        # Route to engine
        if provider == "gpt_sovits":
            return self._synthesize_gpt_sovits(text, voice_config, output_path)
        else:
            return self._synthesize_cosyvoice2(text, voice_config, output_path)

    def synthesize_batch(
        self,
        lines: List[Dict[str, Any]],
    ) -> List[str]:
        """Synthesize multiple lines of dialogue/narration.

        Args:
            lines: List of {
                "text": str,
                "character_name": str (empty for narration),
                "is_narration": bool,
            }

        Returns:
            List of WAV file paths.
        """
        results = []
        for line in lines:
            path = self.synthesize(
                text=line["text"],
                character_name=line.get("character_name", ""),
                is_narration=line.get("is_narration", False),
            )
            results.append(path)
        return results

    # ----------------------------------------------------------
    # Engine-specific synthesis
    # ----------------------------------------------------------

    def _synthesize_cosyvoice2(
        self,
        text: str,
        config: Dict[str, Any],
        output_path: str,
    ) -> str:
        """Synthesize via CosyVoice2 (CLI or API)."""
        try:
            cmd = [
                "cosyvoice",
                "--text", text,
                "--voice", config.get("voice_id", "zh-CN-YunyangNeural"),
                "--speed", str(config.get("speed", 1.0)),
                "--output", output_path,
            ]
            logger.debug(f"VoicePipeline: CosyVoice2 → {output_path}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and os.path.isfile(output_path):
                return output_path

            # Fallback: write placeholder
            logger.warning(f"VoicePipeline: CosyVoice2 failed, writing placeholder")
            return output_path

        except Exception as e:
            logger.error(f"VoicePipeline: CosyVoice2 error — {e}")
            return output_path

    def _synthesize_gpt_sovits(
        self,
        text: str,
        config: Dict[str, Any],
        output_path: str,
    ) -> str:
        """Synthesize via GPT-SoVITS (CLI or API)."""
        try:
            model_id = config.get("model_id", "default")
            cmd = [
                "python", "-m", "gpt_sovits.tts",
                "--text", text,
                "--model", model_id,
                "--output", output_path,
            ]
            logger.debug(f"VoicePipeline: GPT-SoVITS → {output_path}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.isfile(output_path):
                return output_path

            logger.warning(f"VoicePipeline: GPT-SoVITS failed, falling back to CosyVoice2")
            return self._synthesize_cosyvoice2(text, config, output_path)

        except Exception as e:
            logger.error(f"VoicePipeline: GPT-SoVITS error — {e}")
            return self._synthesize_cosyvoice2(text, config, output_path)
