"""TTS engine using edge-tts (free, no API key needed) + CosyVoice 2 voice cloning."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional


class TTSEngine:
    """Text-to-speech using Microsoft Edge TTS (free, high quality).

    Falls back to CosyVoice 2 voice cloning when reference audio is available.
    """

    # Chinese voice mappings (edge-tts)
    VOICE_CN_FEMALE = "zh-CN-XiaoxiaoNeural"
    VOICE_CN_MALE = "zh-CN-YunxiNeural"
    VOICE_CN_NARRATOR = "zh-CN-YunjianNeural"
    VOICE_CN_YOUNG_FEMALE = "zh-CN-XiaoyiNeural"
    VOICE_CN_YOUNG_MALE = "zh-CN-YunyangNeural"

    # Emotion styles for Xiaoxiao
    EMOTION_STYLES = {
        "neutral": "neutral",
        "happy": "cheerful",
        "sad": "sad",
        "angry": "angry",
        "tense": "fearful",
        "dramatic": "excited",
        "dark": "serious",
        "calm": "gentle",
    }

    def __init__(self, output_dir: str | Path = "projects/output/audio"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._voice_cloner = None  # Lazy-loaded CosyVoice 2 provider

    def _get_voice_cloner(self):
        """Lazy-load CosyVoice 2 voice cloning provider."""
        if self._voice_cloner is None:
            from backend.audio.voice_cloning import VoiceCloningProvider
            try:
                self._voice_cloner = VoiceCloningProvider(
                    model_size="tiny",
                    output_dir=str(self.output_dir),
                )
            except (ImportError, RuntimeError):
                self._voice_cloner = None
        return self._voice_cloner

    async def generate(
        self,
        text: str,
        output_path: str | Path,
        voice: str = VOICE_CN_FEMALE,
        emotion: str = "neutral",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        reference_audio: Optional[Path] = None,
    ) -> Path:
        """Generate TTS audio file from text.

        Args:
            text: Chinese text to speak
            output_path: Where to save the WAV file
            voice: edge-tts voice name (e.g., zh-CN-XiaoxiaoNeural)
            emotion: Emotion style (neutral, happy, sad, angry, etc.)
            rate: Speech rate modifier
            pitch: Pitch modifier
            reference_audio: Optional reference audio for voice cloning
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        # Try voice cloning first if reference audio is provided
        if reference_audio and reference_audio.exists():
            cloner = self._get_voice_cloner()
            if cloner is not None:
                try:
                    return await cloner.clone_speak(
                        text=text,
                        reference_audio=reference_audio,
                        output_path=output,
                    )
                except Exception:
                    pass  # Fallback to edge-tts

        # Use edge-tts as primary/fallback
        style = self.EMOTION_STYLES.get(emotion, "neutral")

        try:
            import edge_tts

            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                pitch=pitch,
            )
            await communicate.save(str(output))
        except ImportError:
            try:
                cmd = [
                    sys.executable, "-m", "edge_tts",
                    "--voice", voice,
                    "--rate", rate,
                    "--pitch", pitch,
                    "--text", text,
                    "--write-media", str(output),
                ]
                subprocess.run(cmd, capture_output=True, check=True)
            except Exception:
                output = self._generate_silence(output, duration=len(text) / 5.0)
        except Exception:
            output = self._generate_silence(output, duration=len(text) / 5.0)

        return output

    async def synthesize(self, text: str, profile, output: Path) -> Path:
        """VoiceProvider-compatible boundary for formal novel-video audio."""
        return await self.generate(
            text=text,
            output_path=output,
            voice=getattr(profile, "voice", self.VOICE_CN_FEMALE),
            emotion=getattr(profile, "emotion", "neutral"),
            rate=getattr(profile, "rate", "+0%"),
            pitch=getattr(profile, "pitch", "+0Hz"),
            reference_audio=getattr(profile, "reference_audio", None),
        )

    async def generate_dialogue(
        self,
        dialogue: str,
        shot_id: str,
        character_id: str = "",
        emotion: str = "neutral",
        reference_audio: Optional[Path] = None,
    ) -> Path:
        """Generate dialogue audio for a specific shot with optional voice cloning."""
        output_path = self.output_dir / f"{shot_id}_dialogue.wav"
        voice = self.VOICE_CN_MALE if character_id else self.VOICE_CN_FEMALE
        return await self.generate(
            dialogue, output_path,
            voice=voice, emotion=emotion,
            reference_audio=reference_audio,
        )

    async def generate_narration(
        self,
        text: str,
        shot_id: str,
    ) -> Path:
        """Generate narration audio for a shot."""
        output_path = self.output_dir / f"{shot_id}_narration.wav"
        return await self.generate(text, output_path, voice=self.VOICE_CN_NARRATOR)

    async def generate_character_dialogue(
        self,
        text: str,
        shot_id: str,
        character_id: str,
        archetype: str = "supporting",
        character_index: int = 0,
    ) -> Path:
        """Generate dialogue for a character using archetype-based voice profile.

        Uses VoiceDesigner to pick the right voice for each character archetype
        (hero, mentor, antagonist, etc.), making each character sound distinct.
        Falls back to voice cloning if reference audio is registered.
        """
        output_path = self.output_dir / f"{shot_id}_dialogue.wav"

        # Try voice cloning first
        cloner = self._get_voice_cloner()
        if cloner is not None:
            try:
                return await cloner.speak_as_character(
                    text=text,
                    character_id=character_id,
                    shot_id=shot_id,
                )
            except (ValueError, FileNotFoundError):
                pass  # No reference audio registered, fall through

        # Use archetype-based voice
        from backend.audio.voice_cloning import VoiceDesigner
        designer = VoiceDesigner(output_dir=str(self.output_dir))
        profile = designer.get_voice_profile(archetype, character_index)

        return await self.generate(
            text=text,
            output_path=output_path,
            voice=profile.get("voice", self.VOICE_CN_FEMALE),
            emotion=profile.get("style", "neutral"),
            rate=profile.get("rate", "+0%"),
            pitch=profile.get("pitch", "+0Hz"),
        )

    async def batch_generate(
        self,
        items: list[dict],
    ) -> list[Path]:
        """Generate TTS for multiple items in parallel."""
        tasks = []
        for item in items:
            tasks.append(
                self.generate(
                    text=item["text"],
                    output_path=item["output"],
                    voice=item.get("voice", self.VOICE_CN_FEMALE),
                    emotion=item.get("emotion", "neutral"),
                    reference_audio=item.get("reference_audio"),
                )
            )
        return await asyncio.gather(*tasks)

    @staticmethod
    def _generate_silence(output_path: Path, duration: float = 3.0) -> Path:
        """Generate a silent WAV file as fallback."""
        import struct
        import wave

        sample_rate = 24000
        num_samples = int(sample_rate * duration)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(struct.pack(f"<{num_samples}h", *[0] * num_samples))

        return output_path


class SFXEngine:
    """Simple sound effects generator using procedural audio."""

    def __init__(self, output_dir: str | Path = "projects/output/audio"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(
        self,
        sfx_type: str,
        output_path: str | Path,
        duration: float = 2.0,
    ) -> Path:
        """Generate a simple sound effect."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        if sfx_type == "water":
            return self._generate_noise(output, duration, freq=200, kind="water")
        elif sfx_type == "impact":
            return self._generate_noise(output, duration, freq=80, kind="impact")
        elif sfx_type == "wind":
            return self._generate_noise(output, duration, freq=400, kind="wind")
        elif sfx_type == "footsteps":
            return self._generate_noise(output, duration, freq=100, kind="footsteps")
        else:
            return TTSEngine._generate_silence(output, duration=0.5)

    def _generate_noise(
        self, output_path: Path, duration: float, freq: int, kind: str
    ) -> Path:
        import struct
        import wave
        import random

        sample_rate = 24000
        num_samples = int(sample_rate * duration)
        random.seed(42)

        samples = []
        if kind == "water":
            for i in range(num_samples):
                t = i / sample_rate
                val = (random.random() * 0.3) * (1 - t / duration)
                samples.append(int(val * 32767))
        elif kind == "impact":
            for i in range(num_samples):
                t = i / sample_rate
                decay = max(0, 1 - t * 5)
                val = (random.random() * 0.5) * decay * decay
                samples.append(int(val * 32767))
        elif kind == "wind":
            for i in range(num_samples):
                t = i / sample_rate
                val = random.random() * 0.15 * (0.5 + 0.5 * (1 - abs(2 * t / duration - 1)))
                samples.append(int(val * 32767))
        elif kind == "footsteps":
            for i in range(num_samples):
                t = i / sample_rate
                beat = (t * 3) % 1
                val = (1 - beat) * 0.4 if beat < 0.05 else 0
                samples.append(int(val * 32767))
        else:
            samples = [0] * num_samples

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(struct.pack(f"<{num_samples}h", *samples))

        return output_path
