"""
Scheduler — Subtitle Generation

Stage 7: Generate timed subtitles (SRT format) from shot dialogue + TTS durations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger

from backend.unified_shot import UnifiedShot


@dataclass
class SubtitleResult:
    """A single subtitle entry."""
    index: int
    start: float  # seconds
    end: float    # seconds
    text: str


@dataclass
class SubtitleStageResult:
    """Aggregated subtitle result."""
    subtitle_path: str = ""
    entries: List[SubtitleResult] = field(default_factory=list)
    total: int = 0


class SubtitleStage:
    """Generate timed SRT subtitles from shot dialogue.

    Timing is based on shot duration from UnifiedShot.
    """

    def generate(
        self,
        shots: List[UnifiedShot],
        output_dir: str,
    ) -> SubtitleStageResult:
        """Generate SRT subtitle file from shots with dialogue.

        Args:
            shots: All shots in sequential order.
            output_dir: Where to save subtitle file.

        Returns:
            SubtitleStageResult.
        """
        result = SubtitleStageResult()

        # Build timed entries
        cursor = 0.0
        for shot in shots:
            if not shot.dialogue:
                cursor += shot.duration
                continue

            # Add small padding between subtitles
            entry = SubtitleResult(
                index=result.total + 1,
                start=cursor,
                end=cursor + shot.duration,
                text=shot.dialogue,
            )
            result.entries.append(entry)
            result.total += 1
            cursor += shot.duration

        if not result.entries:
            logger.info("SubtitleStage: No dialogue to subtitle")
            return result

        # Write SRT file
        output_path = os.path.join(output_dir, "subtitles.srt")
        self._write_srt(result.entries, output_path)
        result.subtitle_path = output_path

        logger.info(f"SubtitleStage: {result.total} entries → {output_path}")
        return result

    @staticmethod
    def _write_srt(entries: List[SubtitleResult], path: str) -> None:
        """Write entries in SRT format."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(f"{entry.index}\n")
                f.write(f"{SubtitleStage._fmt_time(entry.start)} --> {SubtitleStage._fmt_time(entry.end)}\n")
                f.write(f"{entry.text}\n\n")

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Format seconds to SRT timestamp: HH:MM:SS,mmm."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
