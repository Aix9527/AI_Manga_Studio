"""
AI Manga Studio Pro V1.0 — Subtitle Plugin

SRT subtitle generation from shot dialogue + timing.
Self-contained: swap with ASS/PGS/smart-subtitle by
replacing this directory.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from plugins.base import SubtitlePlugin


class Plugin(SubtitlePlugin):
    """Basic SRT subtitle generation plugin.

    Generates timed subtitles from shot dialogue and duration.
    """

    # Character-per-second rates for duration estimation
    CPS_RATES: Dict[str, float] = {
        "zh": 3.5,   # Chinese
        "en": 10.0,  # English
        "ja": 5.0,   # Japanese
    }

    def __init__(self) -> None:
        pass

    # ----------------------------------------------------------
    # Plugin Interface
    # ----------------------------------------------------------

    def generate(
        self,
        shots: List[Any],
        timing: Optional[Dict[str, float]] = None,
        output_path: str = "",
        template: str = "basic",
    ) -> str:
        """Generate SRT subtitle file.

        Args:
            shots: List of UnifiedShot objects in order.
            timing: Override timing {shot_id: duration_seconds}.
            output_path: Target SRT file path.
            template: Style template (ignored for basic SRT).

        Returns:
            Path to generated .srt file.
        """
        if not output_path:
            raise ValueError("SubtitlePlugin: output_path is required")

        if not shots:
            logger.warning("SubtitlePlugin: No shots provided")
            open(output_path, "w", encoding="utf-8").close()
            return output_path

        # Build entries
        entries = []
        cursor = 0.0

        for shot in shots:
            if not shot.dialogue:
                cursor += shot.duration
                continue

            # Use override timing if available
            shot_id = shot.shot_id or f"sh{shot.shot:03d}"
            duration = (
                timing.get(shot_id, shot.duration)
                if timing
                else shot.duration
            )

            entries.append({
                "index": len(entries) + 1,
                "start": cursor,
                "end": cursor + duration,
                "text": shot.dialogue,
            })
            cursor += duration

        if not entries:
            logger.info("SubtitlePlugin: No dialogue to subtitle")
            open(output_path, "w", encoding="utf-8").close()
            return output_path

        # Write SRT
        self._write_srt(entries, output_path)
        logger.info(f"SubtitlePlugin: {len(entries)} entries → {output_path}")
        return output_path

    # ----------------------------------------------------------
    # SRT Writer
    # ----------------------------------------------------------

    @staticmethod
    def _write_srt(entries: List[dict], path: str) -> None:
        """Write subtitle entries in SRT format."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(f"{e['index']}\n")
                f.write(
                    f"{Plugin._fmt_time(e['start'])} --> "
                    f"{Plugin._fmt_time(e['end'])}\n"
                )
                f.write(f"{e['text']}\n\n")

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Format seconds to SRT timestamp: HH:MM:SS,mmm."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def estimate_duration(self, text: str, lang: str = "zh") -> float:
        """Estimate speech duration from text length.

        Args:
            text: Dialogue text.
            lang: Language code (zh/en/ja).

        Returns:
            Estimated duration in seconds.
        """
        cps = self.CPS_RATES.get(lang, self.CPS_RATES["zh"])
        return len(text) / cps
