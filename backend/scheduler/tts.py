"""
Scheduler — Text-to-Speech (TTS)

Stage 6: Generate voice audio from shot dialogue text.
Produces WAV files that can be combined during render.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger

from backend.unified_shot import UnifiedShot
from backend.config import get_config


@dataclass
class TTSResult:
    """Result of one TTS generation."""
    shot_id: str
    text: str = ""
    audio_path: str = ""
    duration: float = 0.0
    success: bool = False


@dataclass
class TTSStageResult:
    """Aggregated TTS result."""
    results: List[TTSResult] = field(default_factory=list)
    total: int = 0
    success: int = 0


class TTSStage:
    """Convert shot dialogue to speech audio files."""

    def __init__(self, voice: str = "default"):
        self.voice = voice

    def generate(
        self,
        shots: List[UnifiedShot],
        output_dir: str,
    ) -> TTSStageResult:
        """Generate speech audio for all shots with dialogue.

        Args:
            shots: Shots to process.
            output_dir: Where to save audio files.

        Returns:
            TTSStageResult.
        """
        result = TTSStageResult()

        # Filter shots with dialogue
        talking = [s for s in shots if s.dialogue]
        result.total = len(talking)

        if not talking:
            logger.info("TTSStage: No dialogue to synthesize")
            return result

        audio_dir = Path(output_dir) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        for shot in talking:
            tr = self._synthesize(shot, str(audio_dir))
            result.results.append(tr)
            if tr.success:
                result.success += 1

        logger.info(f"TTSStage: {result.success}/{result.total} audio files generated")
        return result

    def _synthesize(self, shot: UnifiedShot, output_dir: str) -> TTSResult:
        """Synthesize speech for a single shot.

        In production: use edge-tts / coqui / Azure TTS API.
        For now: generates a placeholder with estimated duration.
        """
        tr = TTSResult(
            shot_id=shot.shot_id or f"sh{shot.shot:03d}",
            text=shot.dialogue,
        )

        audio_path = os.path.join(output_dir, f"{tr.shot_id}.wav")

        try:
            # Try edge-tts first
            import subprocess
            ret = subprocess.run(
                ["edge-tts", "--text", shot.dialogue, "--voice", "zh-CN-XiaoxiaoNeural",
                 "--write-media", audio_path],
                capture_output=True,
                timeout=30,
            )
            if ret.returncode == 0 and os.path.exists(audio_path):
                tr.audio_path = audio_path
                tr.success = True
                logger.info(f"TTSStage: {tr.shot_id} → edge-tts")
                return tr
        except Exception:
            pass

        # Fallback: estimate duration, mark as pending
        chars_per_sec = 4  # average Chinese speech rate
        tr.duration = len(shot.dialogue) / chars_per_sec
        tr.success = False
        logger.warning(f"TTSStage: {tr.shot_id} TTS not available, estimated {tr.duration:.1f}s")

        return tr
