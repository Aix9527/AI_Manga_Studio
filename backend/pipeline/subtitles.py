"""
AI Manga Studio Pro V2.0 — Layer 11: Whisper Subtitles

Generates timestamped subtitles from audio using Whisper.

Output formats:
    SRT  — standard subtitle format (primary)
    ASS  — advanced subtitle format with styling (colored by character role)

Whisper model: auto-detects best available (tiny to large-v3).
Runs on CPU, zero GPU impact.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.model_router import ModelRouter


# ---------------------------------------------------------------------------
# Character colour palette for ASS subtitles
# ---------------------------------------------------------------------------

CHARACTER_COLORS: Dict[str, str] = {
    "protagonist": "&H00FFFF&",      # Yellow
    "antagonist": "&H0000FF&",       # Red
    "supporting": "&H00FF00&",       # Green
    "narrator": "&HFFFFFF&",         # White
    "default": "&HFFFFFF&",
}

ROLE_COLOR_MAP: Dict[str, str] = {
    "主角": CHARACTER_COLORS["protagonist"],
    "反派": CHARACTER_COLORS["antagonist"],
    "配角": CHARACTER_COLORS["supporting"],
    "旁白": CHARACTER_COLORS["narrator"],
    "narrator": CHARACTER_COLORS["narrator"],
    "protagonist": CHARACTER_COLORS["protagonist"],
    "antagonist": CHARACTER_COLORS["antagonist"],
}


# ---------------------------------------------------------------------------
# WhisperSubtitles
# ---------------------------------------------------------------------------


class WhisperSubtitles:
    """Whisper-based automatic subtitle generation.

    Produces SRT (standard) and ASS (styled) subtitle files from audio.

    Usage:
        ws = WhisperSubtitles()
        srt_path, ass_path = ws.generate("dialog.wav", "ch01_sh03")
    """

    WHISPER_MODELS = [
        "large-v3", "large-v2", "large", "medium", "small", "base", "tiny",
    ]

    def __init__(
        self,
        model_size: str = "medium",
        language: str = "zh",
        output_dir: Optional[str] = None,
    ):
        self._router = ModelRouter()
        self._model_size = model_size
        self._language = language

        if output_dir:
            self._output_dir = Path(output_dir)
        else:
            self._output_dir = Path(__file__).resolve().parent.parent.parent / "output" / "subtitles"
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Verify whisper availability
        self._whisper_available = self._detect_whisper()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def generate(
        self,
        audio_path: str,
        label: str = "output",
        character_roles: Optional[Dict[int, str]] = None,
    ) -> Dict[str, str]:
        """Generate SRT and ASS subtitles from audio.

        Args:
            audio_path: Path to WAV audio file.
            label: Label for output filenames (e.g. 'ch01_sh03').
            character_roles: Optional dict of {line_index: role_name} for ASS coloring.

        Returns:
            {"srt": "<srt_path>", "ass": "<ass_path>"}
        """
        if not self._whisper_available:
            logger.warning("WhisperSubtitles: Whisper not available, skipping subtitles")
            return {"srt": "", "ass": ""}

        srt_path = str(self._output_dir / f"{label}.srt")
        ass_path = str(self._output_dir / f"{label}.ass")

        # Step 1: Transcribe → SRT
        success = self._transcribe_to_srt(audio_path, srt_path)
        if not success:
            return {"srt": "", "ass": ""}

        # Step 2: Convert SRT → ASS with styling
        self._srt_to_ass(srt_path, ass_path, character_roles)

        logger.info(
            f"WhisperSubtitles: generated subtitles for '{label}' → {srt_path}, {ass_path}"
        )
        return {"srt": srt_path, "ass": ass_path}

    def generate_batch(
        self,
        audio_paths: List[str],
        labels: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Generate subtitles for multiple audio files."""
        results = []
        for i, audio_path in enumerate(audio_paths):
            label = labels[i] if labels and i < len(labels) else f"line_{i:04d}"
            results.append(self.generate(audio_path, label))
        return results

    def merge_srt_files(
        self,
        srt_paths: List[str],
        output_path: str,
    ) -> str:
        """Merge multiple SRT files into one with sequential timestamps."""
        entries: List[str] = []
        index = 1
        time_offset = 0.0

        for srt_path in srt_paths:
            if not srt_path or not os.path.isfile(srt_path):
                continue
            with open(srt_path, "r", encoding="utf-8") as f:
                content = f.read()
            parsed = self._parse_srt(content)
            for entry in parsed:
                entry["index"] = index
                entry["start"] += time_offset
                entry["end"] += time_offset
                index += 1
            if parsed:
                time_offset = parsed[-1]["end"] + 0.1

        merged = self._format_srt(parsed) if parsed else ""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(merged)

        return output_path

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _transcribe_to_srt(self, audio_path: str, output_path: str) -> bool:
        """Run Whisper transcription to SRT."""
        if not os.path.isfile(audio_path):
            logger.error(f"WhisperSubtitles: audio not found: {audio_path}")
            return False

        try:
            cmd = [
                "whisper",
                audio_path,
                "--model", self._model_size,
                "--language", self._language,
                "--output_format", "srt",
                "--output_dir", str(self._output_dir),
                "--task", "transcribe",
            ]

            # Use faster-whisper if available
            try:
                subprocess.run(
                    ["faster-whisper", "--help"],
                    capture_output=True,
                    timeout=5,
                )
                cmd = [
                    "faster-whisper",
                    audio_path,
                    "--model", self._model_size,
                    "--language", self._language,
                    "--output_format", "srt",
                    "--output_dir", str(self._output_dir),
                ]
            except Exception:
                pass

            logger.debug(f"WhisperSubtitles: transcribing — {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"WhisperSubtitles: transcription failed — {result.stderr[:300]}")
                return False

            return os.path.isfile(output_path)

        except subprocess.TimeoutExpired:
            logger.error("WhisperSubtitles: transcription timeout")
            return False
        except Exception as e:
            logger.error(f"WhisperSubtitles: transcription error — {e}")
            return False

    def _srt_to_ass(
        self,
        srt_path: str,
        ass_path: str,
        character_roles: Optional[Dict[int, str]] = None,
    ) -> None:
        """Convert SRT to styled ASS subtitle."""
        if not os.path.isfile(srt_path):
            return

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        entries = self._parse_srt(srt_content)
        if not entries:
            return

        ass_header = """[Script Info]
Title: AI Manga Studio Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,10,10,30,1
Style: Protagonist,Microsoft YaHei,48,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,10,10,30,1
Style: Antagonist,Microsoft YaHei,48,&H000000FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,10,10,30,1
Style: Supporting,Microsoft YaHei,48,&H0000FF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,10,10,30,1
Style: Narrator,Microsoft YaHei,40,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,0,10,10,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        lines = [ass_header]
        for i, entry in enumerate(entries):
            role = "Default"
            if character_roles:
                char_role = character_roles.get(i, "")
                role = self._role_to_style(char_role)

            start_ass = self._seconds_to_ass_time(entry["start"])
            end_ass = self._seconds_to_ass_time(entry["end"])
            text_escaped = entry["text"].replace("\\", "\\\\").replace("\n", "\\N")

            lines.append(
                f"Dialogue: 0,{start_ass},{end_ass},{role},,0,0,0,,{text_escaped}"
            )

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # ----------------------------------------------------------
    # Parsing helpers
    # ----------------------------------------------------------

    @staticmethod
    def _parse_srt(content: str) -> List[Dict[str, Any]]:
        """Parse SRT content into list of {index, start, end, text}."""
        entries = []
        blocks = content.strip().split("\n\n")
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue
            try:
                index = int(lines[0])
                times = lines[1].split(" --> ")
                start = WhisperSubtitles._srt_time_to_seconds(times[0])
                end = WhisperSubtitles._srt_time_to_seconds(times[1])
                text = "\n".join(lines[2:])
                entries.append({
                    "index": index,
                    "start": start,
                    "end": end,
                    "text": text,
                })
            except (ValueError, IndexError):
                continue
        return entries

    @staticmethod
    def _format_srt(entries: List[Dict[str, Any]]) -> str:
        """Format parsed entries back to SRT string."""
        blocks = []
        for e in entries:
            start_srt = WhisperSubtitles._seconds_to_srt_time(e["start"])
            end_srt = WhisperSubtitles._seconds_to_srt_time(e["end"])
            blocks.append(f"{e['index']}\n{start_srt} --> {end_srt}\n{e['text']}")
        return "\n\n".join(blocks) + "\n"

    @staticmethod
    def _srt_time_to_seconds(time_str: str) -> float:
        """Convert SRT timestamp (HH:MM:SS,mmm) to float seconds."""
        h, m, s = time_str.replace(",", ":").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        """Convert float seconds to SRT timestamp."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    @staticmethod
    def _seconds_to_ass_time(seconds: float) -> str:
        """Convert float seconds to ASS timestamp (H:MM:SS.cc)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    @staticmethod
    def _role_to_style(role: str) -> str:
        """Map character role to ASS style name."""
        role_lower = role.lower()
        for key, color in ROLE_COLOR_MAP.items():
            if key.lower() in role_lower:
                if key in ("protagonist", "主角"):
                    return "Protagonist"
                elif key in ("antagonist", "反派"):
                    return "Antagonist"
                elif key in ("supporting", "配角"):
                    return "Supporting"
                elif key in ("narrator", "旁白"):
                    return "Narrator"
        return "Default"

    @staticmethod
    def _detect_whisper() -> bool:
        """Detect if Whisper is available."""
        for cmd in ["whisper", "faster-whisper"]:
            try:
                result = subprocess.run(
                    [cmd, "--help"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode in (0, 1):
                    return True
            except Exception:
                continue
        return False


# Convenience function
def generate_subtitles(
    audio_path: str,
    label: str = "output",
    character_roles: Optional[Dict[int, str]] = None,
) -> Dict[str, str]:
    """Shortcut: generate subtitles from audio."""
    return WhisperSubtitles().generate(audio_path, label, character_roles)
