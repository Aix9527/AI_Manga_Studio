"""Voice cloning engine using CosyVoice 2 — zero-shot voice cloning (3s audio)."""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Optional


class VoiceCloningProvider:
    """Zero-shot voice cloning with CosyVoice 2.

    Requires: pip install cosyvoice
    Model auto-downloads on first use (~1.5GB for CosyVoice2-0.5B).

    Usage:
        provider = VoiceCloningProvider()
        audio = await provider.clone_speak(
            text="我命由我不由天！",
            reference_audio=Path("character_ref.wav"),
            output_path=Path("output.wav"),
        )
    """

    # Available CosyVoice 2 model sizes
    MODEL_SIZES = {
        "tiny": "CosyVoice2-0.5B",   # ~1.5GB, fastest
        "base": "CosyVoice2-1.8B",   # ~4GB, balanced
        "large": "CosyVoice2-3B",    # ~7GB, best quality
    }

    def __init__(
        self,
        model_size: str = "tiny",
        output_dir: str | Path = "projects/output/audio",
    ):
        self.model_size = model_size
        self.model_name = self.MODEL_SIZES.get(model_size, self.MODEL_SIZES["tiny"])
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._voice_cache: dict[str, Path] = {}  # character_id -> cached reference path

    def _get_model(self):
        """Lazy-load CosyVoice 2 model."""
        if self._model is not None:
            return self._model

        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2
            self._model = CosyVoice2(self.model_name, load_jit=False, load_trt=False, fp16=False)
        except ImportError:
            raise ImportError(
                "CosyVoice 2 is not installed. Run: pip install cosyvoice\n"
                "Or use edge-tts as fallback (already supported)."
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load CosyVoice 2 model '{self.model_name}': {e}\n"
                "Try a smaller model: VoiceCloningProvider(model_size='tiny')"
            )
        return self._model

    async def clone_speak(
        self,
        text: str,
        reference_audio: Path,
        output_path: Path,
        speed: float = 1.0,
        stream: bool = False,
    ) -> Path:
        """Clone voice from reference audio and speak the given text.

        Args:
            text: Chinese text to synthesize
            reference_audio: 3-10 second WAV file of the target voice
            output_path: Where to save the output WAV
            speed: Speech speed multiplier (0.5-2.0)
            stream: If True, use streaming mode (lower latency)
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not reference_audio.exists():
            raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

        model = self._get_model()

        try:
            # Run in thread pool since CosyVoice2.inference may be blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_inference,
                text,
                str(reference_audio),
                str(output_path),
                speed,
                stream,
            )
        except Exception as e:
            # Fallback: try edge-tts CLI as last resort
            try:
                await self._fallback_edge_tts(text, output_path)
            except Exception:
                raise RuntimeError(f"Voice cloning failed: {e}") from e

        return output_path

    def _run_inference(
        self,
        text: str,
        ref_audio_path: str,
        output_path: str,
        speed: float,
        stream: bool,
    ) -> None:
        """Run CosyVoice 2 inference (called in thread pool)."""
        model = self._get_model()

        output = model.inference_zero_shot(
            text,
            ref_audio_path,
            stream=stream,
            speed=speed,
        )

        if stream:
            # Streaming output: concatenate chunks
            import soundfile as sf
            import numpy as np

            chunks = []
            for chunk in output:
                chunks.append(chunk["tts_speech"])
            if chunks:
                audio = np.concatenate(chunks)
                sf.write(output_path, audio, 22050)
            else:
                raise RuntimeError("CosyVoice 2 streaming produced no output")
        else:
            # Non-streaming output: direct write
            import soundfile as sf
            sf.write(output_path, output["tts_speech"], 22050)

    def register_character_voice(
        self,
        character_id: str,
        reference_audio: Path,
    ) -> None:
        """Register a character's reference voice for future use."""
        if not reference_audio.exists():
            raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

        # Cache reference audio by character
        cache_dir = self.output_dir / "voice_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        cached_path = cache_dir / f"{character_id}_ref.wav"
        if reference_audio != cached_path:
            import shutil
            shutil.copy2(reference_audio, cached_path)

        self._voice_cache[character_id] = cached_path

    async def speak_as_character(
        self,
        text: str,
        character_id: str,
        shot_id: str,
        emotion: str = "neutral",
        speed: float = 1.0,
    ) -> Path:
        """Speak text using a registered character's cloned voice."""
        output_path = self.output_dir / f"{shot_id}_dialogue.wav"

        if character_id in self._voice_cache:
            ref_audio = self._voice_cache[character_id]
        else:
            # Try to load from cache
            cache_path = self.output_dir / "voice_cache" / f"{character_id}_ref.wav"
            if cache_path.exists():
                ref_audio = cache_path
                self._voice_cache[character_id] = cache_path
            else:
                raise ValueError(
                    f"No reference audio registered for character '{character_id}'. "
                    f"Call register_character_voice() first."
                )

        return await self.clone_speak(
            text=text,
            reference_audio=ref_audio,
            output_path=output_path,
            speed=speed,
        )

    async def _fallback_edge_tts(self, text: str, output_path: Path) -> None:
        """Fallback to edge-tts when voice cloning is unavailable."""
        from backend.audio.tts_engine import TTSEngine
        tts = TTSEngine(output_dir=str(output_path.parent))
        await tts.generate(text, output_path, voice=TTSEngine.VOICE_CN_FEMALE)

    @staticmethod
    def check_available() -> bool:
        """Check if CosyVoice 2 is installed and importable."""
        try:
            import cosyvoice  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def generate_reference_audio_hint() -> str:
        """Return instructions for creating reference audio for voice cloning."""
        return (
            "To enable voice cloning, provide a 3-10 second clean WAV recording "
            "of the character's voice. The recording should:\n"
            "  - Be in a quiet environment\n"
            "  - Contain natural speech (not whispering or shouting)\n"
            "  - Be in the same language as the target text (Chinese)\n"
            "Place reference files in: projects/voice_references/<character_name>.wav"
        )


class VoiceDesigner:
    """Design and manage character voice profiles without cloning."""

    # Voice profiles mapped to character archetypes
    ARCHETYPE_VOICES: dict[str, list[dict]] = {
        "hero": [
            {"voice": "zh-CN-YunxiNeural", "style": "cheerful", "rate": "+5%"},
            {"voice": "zh-CN-YunjianNeural", "style": "excited", "rate": "+10%"},
        ],
        "mentor": [
            {"voice": "zh-CN-YunjianNeural", "style": "gentle", "rate": "-5%"},
            {"voice": "zh-CN-YunxiNeural", "style": "calm", "rate": "-10%"},
        ],
        "trickster": [
            {"voice": "zh-CN-XiaoxiaoNeural", "style": "cheerful", "rate": "+15%"},
            {"voice": "zh-CN-XiaoyiNeural", "style": "excited", "rate": "+10%"},
        ],
        "antagonist": [
            {"voice": "zh-CN-YunxiNeural", "style": "angry", "rate": "-5%", "pitch": "-8Hz"},
            {"voice": "zh-CN-YunjianNeural", "style": "serious", "rate": "-10%"},
        ],
        "supporting": [
            {"voice": "zh-CN-XiaoxiaoNeural", "style": "gentle", "rate": "+0%"},
            {"voice": "zh-CN-XiaoyiNeural", "style": "neutral", "rate": "+0%"},
        ],
    }

    def __init__(self, output_dir: str | Path = "projects/output/audio"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_voice_profile(self, archetype: str, index: int = 0) -> dict:
        """Get a voice profile for a character archetype."""
        profiles = self.ARCHETYPE_VOICES.get(archetype, self.ARCHETYPE_VOICES["supporting"])
        return profiles[index % len(profiles)]