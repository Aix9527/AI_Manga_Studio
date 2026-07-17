"""
Scheduler — Final Render

Stage 8: Composite all generated assets into a final video.
  - Concatenate video clips sequentially
  - Overlay subtitles
  - Mix in voice audio + BGM
  - Output single MP4 file

Uses ffmpeg for video processing.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger

from backend.unified_shot import UnifiedShot
from backend.config import get_config


@dataclass
class RenderResult:
    """Result of final render."""
    output_path: str = ""
    total_duration: float = 0.0
    shot_count: int = 0
    success: bool = False
    error: str = ""


class RenderStage:
    """Composite all assets into the final manga video.

    Supports two audio sources:
      1. Per-shot TTS voice audio (from audio_dir/<shot_id>.wav)
      2. Background music (bgm_path)

    Both are mixed into the final video track at correct timestamps.
    """

    def __init__(self, fps: int = 24):
        self.fps = fps

    def render(
        self,
        shots: List[UnifiedShot],
        output_dir: str,
        subtitle_path: str = "",
        bgm_path: str = "",
        audio_dir: str = "",
    ) -> RenderResult:
        """Render the final video from all shot outputs.

        Args:
            shots: All shots with image/video paths filled.
            output_dir: Render output directory.
            subtitle_path: Path to SRT subtitle file.
            bgm_path: Path to background music file.
            audio_dir: Directory containing per-shot TTS .wav files (optional).

        Returns:
            RenderResult.
        """
        result = RenderResult(shot_count=len(shots))
        os.makedirs(output_dir, exist_ok=True)

        # Collect valid media files
        media_files = [s.video_path or s.image_path for s in shots
                       if s.video_path or s.image_path]

        if not media_files:
            result.error = "No media files to render"
            logger.error(result.error)
            return result

        output_path = os.path.join(output_dir, "final_render.mp4")
        result.output_path = output_path

        try:
            if len(media_files) == 1 and media_files[0].endswith((".mp4", ".mov", ".webm")):
                # Single video: just add subtitles + BGM
                self._render_single(media_files[0], output_path, subtitle_path, bgm_path, result)
            elif len(media_files) == 1:
                # Single image: create still-frame video
                self._render_from_image(media_files[0], shots[0].duration, output_path, subtitle_path, result)
            else:
                # Multiple files: build concat list with audio mixing
                self._render_concat(shots, media_files, output_path, subtitle_path, bgm_path, audio_dir, result)

            # Calculate total duration
            result.total_duration = sum(s.duration for s in shots if s.duration > 0)

            if os.path.exists(output_path):
                result.success = True
                logger.info(f"RenderStage: Done → {output_path}")
            else:
                result.error = "Output file not found after render"
                logger.error(result.error)

        except FileNotFoundError:
            result.error = "ffmpeg not found. Install ffmpeg and add to PATH."
            logger.error(result.error)
        except subprocess.CalledProcessError as e:
            result.error = f"ffmpeg error: {e.stderr.decode('utf-8','replace')[:500] if e.stderr else str(e)}"
            logger.error(f"RenderStage: ffmpeg failed — {result.error}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"RenderStage: Failed — {e}")

        return result

    def _render_single(
        self,
        video_path: str,
        output: str,
        subtitle: str,
        bgm: str,
        result: RenderResult,
    ) -> None:
        """Render single video with optional subtitles + BGM."""
        # Build ffmpeg command
        cmd = ["ffmpeg", "-y", "-i", video_path]

        # Subtitles filter
        vf_parts = []
        if subtitle and os.path.exists(subtitle):
            # Escape path for ffmpeg subtitles filter
            escaped = subtitle.replace("\\", "/").replace(":", "\\:")
            vf_parts.append(f"subtitles='{escaped}'")

        # BGM
        if bgm and os.path.exists(bgm):
            cmd.insert(2, "-i")
            cmd.insert(3, bgm)
            cmd.insert(2, "-stream_loop")
            cmd.insert(3, "-1")

        # Video filter
        if vf_parts:
            cmd.extend(["-vf", ",".join(vf_parts)])

        # Audio: mix original + BGM
        if len(cmd) > 6:
            cmd.extend(["-filter_complex", "[1:a]volume=0.3[bgm];[0:a][bgm]amix=inputs=2:duration=first"])

        cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-preset", "fast", output])
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)

    def _render_from_image(
        self,
        image_path: str,
        duration: float,
        output: str,
        subtitle: str,
        result: RenderResult,
    ) -> None:
        """Create still-frame video from a single image."""
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-t", str(duration or 3),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
        ]

        if subtitle and os.path.exists(subtitle):
            escaped = subtitle.replace("\\", "/").replace(":", "\\:")
            cmd.extend(["-vf", f"subtitles='{escaped}'"])

        cmd.append(output)
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)

    def _render_concat(
        self,
        shots: List[UnifiedShot],
        media_files: List[str],
        output: str,
        subtitle: str,
        bgm: str,
        audio_dir: str,
        result: RenderResult,
    ) -> None:
        """Concatenate multiple video/image files into one, with per-shot voice audio.

        Strategy:
          1. Build a concat list for all video/image files
          2. Collect per-shot TTS WAV files and build a single mixed audio track
          3. If no audio files exist, render video-only
          4. Use ffmpeg to combine video track + audio track + subtitles + BGM
        """
        concat_path = os.path.join(os.path.dirname(output), "_concat_list.txt")

        # --- Build concat file + collect audio segments ---
        audio_inputs = []   # list of (wav_path, start_sec, duration_sec)
        total_duration = 0.0

        with open(concat_path, "w", encoding="utf-8") as f:
            for i, mf in enumerate(media_files):
                f.write(f"file '{mf.replace(chr(92), '/')}'\n")
                # Duration for images (videos carry their own duration)
                if not mf.endswith((".mp4", ".mov", ".webm")):
                    dur = shots[i].duration if i < len(shots) and shots[i].duration > 0 else 3.0
                    f.write(f"duration {dur}\n")
                    total_duration += dur
                else:
                    # Approximate duration for video — will be refined by ffmpeg
                    dur = shots[i].duration if i < len(shots) and shots[i].duration > 0 else 3.0
                    total_duration += dur

                # Check for TTS audio
                if audio_dir and i < len(shots):
                    shot = shots[i]
                    sid = shot.shot_id or f"sh{shot.shot:03d}"
                    wav_path = os.path.join(audio_dir, f"{sid}.wav")
                    if os.path.exists(wav_path):
                        audio_inputs.append((wav_path, total_duration - dur, dur))

        # --- Build ffmpeg command ---
        has_audio = bool(audio_inputs)
        has_bgm = bool(bgm and os.path.exists(bgm))
        has_subtitle = bool(subtitle and os.path.exists(subtitle))

        if not has_audio and not has_bgm:
            # Simple concat (no audio to mix)
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_path,
            ]
            if has_subtitle:
                escaped = subtitle.replace("\\", "/").replace(":", "\\:")
                cmd.extend(["-vf", f"subtitles='{escaped}'"])
            cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", output])
            subprocess.run(cmd, capture_output=True, timeout=600, check=True)

        else:
            # Audio mixing: build a silent audio track first, then overlay TTS+BGM
            audio_dir_tmp = os.path.dirname(output)

            # Step 1: Build the video track (no audio)
            video_raw = os.path.join(audio_dir_tmp, "_video_raw.mp4")
            cmd_vid = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_path,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-an",  # no audio
                video_raw,
            ]
            subprocess.run(cmd_vid, capture_output=True, timeout=600, check=True)

            # Step 2: Build a mixed audio track from per-shot WAVs + optional BGM
            audio_mixed = os.path.join(audio_dir_tmp, "_audio_mixed.wav")
            self._build_audio_track(audio_inputs, bgm_path, total_duration, audio_mixed)

            # Step 3: Mux video + audio + subtitles
            cmd_final = [
                "ffmpeg", "-y",
                "-i", video_raw,
                "-i", audio_mixed,
            ]

            vf_parts = []
            if has_subtitle:
                escaped = subtitle.replace("\\", "/").replace(":", "\\:")
                vf_parts.append(f"subtitles='{escaped}'")

            if vf_parts:
                cmd_final.extend(["-vf", ",".join(vf_parts)])

            cmd_final.extend([
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                output,
            ])
            subprocess.run(cmd_final, capture_output=True, timeout=600, check=True)

            # Cleanup temp files
            for tmp in [video_raw, audio_mixed]:
                if os.path.exists(tmp):
                    os.remove(tmp)

        # Clean up concat list
        if os.path.exists(concat_path):
            os.remove(concat_path)

    def _build_audio_track(
        self,
        audio_inputs: list,
        bgm_path: str,
        total_duration: float,
        output_path: str,
    ) -> None:
        """Build a single mixed audio track from per-shot WAVs + optional BGM.

        Uses ffmpeg adelay + amix to place each audio clip at the correct timestamp.

        Args:
            audio_inputs: List of (wav_path, start_sec, duration_sec) tuples.
            bgm_path: Optional BGM file path.
            total_duration: Total video duration in seconds.
            output_path: Where to write the mixed WAV.
        """
        if not audio_inputs and not bgm_path:
            # Create a silent audio track
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r=44100:cl=stereo:d={total_duration:.1f}",
                "-t", f"{total_duration:.1f}",
                output_path,
            ], capture_output=True, timeout=60, check=True)
            return

        # Build complex filter for ffmpeg
        cmd = ["ffmpeg", "-y"]

        # Generate silent background
        cmd.extend(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={total_duration:.1f}"])

        input_idx = 1  # 0 = silent bg
        filter_parts = []
        mix_inputs = ["[0:a]"]  # silent track

        # Add each voice WAV
        for wav_path, start_sec, duration_sec in audio_inputs:
            cmd.extend(["-i", wav_path])
            # Delay this audio to its correct start position
            delay_ms = int(start_sec * 1000)
            filter_parts.append(
                f"[{input_idx}:a]adelay={delay_ms}|{delay_ms},apad=whole_dur={total_duration:.1f}[a{input_idx}]"
            )
            mix_inputs.append(f"[a{input_idx}]")
            input_idx += 1

        # Add BGM if available
        has_bgm = bool(bgm_path and os.path.exists(bgm_path))
        if has_bgm:
            cmd.extend(["-stream_loop", "-1", "-i", bgm_path])
            filter_parts.append(
                f"[{input_idx}:a]volume=0.25,apad=whole_dur={total_duration:.1f}[a{input_idx}]"
            )
            mix_inputs.append(f"[a{input_idx}]")
            input_idx += 1

        # Build filter_complex string
        filter_str = ";".join(filter_parts) if filter_parts else ""
        amix_inputs = "".join(mix_inputs)
        filter_str += f";{amix_inputs}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0,volume=1.5"

        cmd.extend(["-filter_complex", filter_str])
        cmd.extend(["-t", f"{total_duration:.1f}"])
        cmd.extend(["-ac", "2", "-ar", "44100", output_path])

        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
        logger.info(f"RenderStage: Mixed audio track → {output_path}")
