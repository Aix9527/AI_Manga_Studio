"""Subtitle generation from dialogue and narration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class SubtitleGenerator:
    """Generate SRT subtitles from production plan shots."""

    def __init__(self, output_dir: str | Path = "projects/output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_srt(
        self,
        shots: list[dict],
        output_path: str | Path,
    ) -> Path:
        """Generate SRT subtitle file from shots."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        current_time = 0.0

        for i, shot in enumerate(shots, start=1):
            start_sec = current_time
            duration = shot.get("duration", 5.0)
            end_sec = start_sec + duration

            text = shot.get("narration", "") or ""
            dialogue = shot.get("dialogue", "")
            if isinstance(dialogue, list):
                dialogue = " ".join(dialogue)
            if dialogue:
                text = dialogue

            if text:
                start_str = self._format_time(start_sec)
                end_str = self._format_time(end_sec)
                lines.append(f"{i}")
                lines.append(f"{start_str} --> {end_str}")
                lines.append(text[:80])
                lines.append("")

            current_time = end_sec

        output.write_text("\n".join(lines), encoding="utf-8")
        return output

    def generate_ass(
        self,
        shots: list[dict],
        output_path: str | Path,
        style: str = "manga",
    ) -> Path:
        """Generate ASS subtitle file with styling."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        header = """[Script Info]
Title: AI Manga Studio Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,36,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,60,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        current_time = 0.0

        for shot in shots:
            start_sec = current_time
            duration = shot.get("duration", 5.0)
            end_sec = start_sec + duration

            text = shot.get("narration", "") or ""
            dialogue = shot.get("dialogue", "")
            if isinstance(dialogue, list):
                dialogue = " ".join(dialogue)
            if dialogue:
                text = dialogue

            if text:
                start_str = self._format_ass_time(start_sec)
                end_str = self._format_ass_time(end_sec)
                events.append(
                    f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}"
                )

            current_time = end_sec

        output.write_text(header + "\n".join(events), encoding="utf-8")
        return output

    @staticmethod
    def _format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"