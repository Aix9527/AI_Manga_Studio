from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class MediaValidationError(Exception):
    def __init__(self, path: str, expected: dict, actual: dict):
        self.path = path
        self.expected = expected
        self.actual = actual
        super().__init__(f"Validation failed for {path}: expected {expected}, got {actual}")


@dataclass
class MediaValidator:
    ffprobe_path: str = "ffprobe"

    def validate_image(self, path: str, min_width: int = 256, min_height: int = 256) -> dict[str, Any]:
        info = self._probe(path)
        streams = info.get("streams", [])
        if not streams:
            raise MediaValidationError(path, {"type": "image"}, {"error": "no_streams"})

        s = streams[0]
        w = s.get("width", 0)
        h = s.get("height", 0)
        if w < min_width or h < min_height:
            raise MediaValidationError(path, {"min_width": min_width, "min_height": min_height}, {"width": w, "height": h})

        return {"width": w, "height": h, "codec": s.get("codec_name", "")}

    def validate_video(self, path: str, expected_duration: float | None = None) -> dict[str, Any]:
        info = self._probe(path)
        streams = info.get("streams", [])
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        if not video_streams:
            raise MediaValidationError(path, {"type": "video"}, {"error": "no_video_stream"})

        fmt = info.get("format", {})
        duration = float(fmt.get("duration", 0))
        vs = video_streams[0]

        result: dict[str, Any] = {
            "width": vs.get("width", 0),
            "height": vs.get("height", 0),
            "duration": duration,
            "codec": vs.get("codec_name", ""),
            "fps": self._parse_fps(vs.get("r_frame_rate", "")),
        }

        if expected_duration is not None and duration > 0 and expected_duration > 0:
            ratio = duration / expected_duration
            if ratio < 0.5 or ratio > 1.5:
                raise MediaValidationError(
                    path,
                    {"duration": expected_duration},
                    {"duration": duration, "ratio": ratio},
                )

        return result

    def validate_audio(self, path: str, expected_duration: float | None = None, min_duration: float = 0.1) -> dict[str, Any]:
        info = self._probe(path)
        streams = info.get("streams", [])
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if not audio_streams:
            raise MediaValidationError(path, {"type": "audio"}, {"error": "no_audio_stream"})

        fmt = info.get("format", {})
        duration = float(fmt.get("duration", 0))
        if duration < min_duration:
            raise MediaValidationError(
                path,
                {"min_duration": min_duration},
                {"duration": duration},
            )

        as_ = audio_streams[0]
        result: dict[str, Any] = {
            "duration": duration,
            "codec": as_.get("codec_name", ""),
            "sample_rate": as_.get("sample_rate", "0"),
            "channels": as_.get("channels", 0),
        }

        if expected_duration is not None and duration > 0 and expected_duration > 0:
            ratio = duration / expected_duration
            if ratio < 0.8 or ratio > 1.2:
                raise MediaValidationError(
                    path,
                    {"duration": expected_duration},
                    {"duration": duration, "ratio": ratio},
                )

        return result

    def _probe(self, path: str) -> dict:
        try:
            result = subprocess.run(
                [self.ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise MediaValidationError(path, {}, {"error": result.stderr.strip()})
            return json.loads(result.stdout)
        except FileNotFoundError:
            raise RuntimeError(f"ffprobe not found at {self.ffprobe_path}")
        except json.JSONDecodeError:
            raise MediaValidationError(path, {}, {"error": "invalid_json_output"})

    def _parse_fps(self, r_frame_rate: str) -> float:
        if "/" in r_frame_rate:
            parts = r_frame_rate.split("/")
            try:
                return float(parts[0]) / float(parts[1])
            except (ValueError, ZeroDivisionError):
                pass
        return 0.0
