"""
AI Manga Studio Pro V3 — Cinema Composer

将生成的视频片段按分镜顺序剪辑合成最终 MP4。
使用 FFmpeg 进行硬件加速编码。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ============================================================
# Data Classes
# ============================================================

@dataclass
class ComposeResult:
    """Final composition result."""

    output_path: str = ""
    duration_sec: float = 0.0
    clip_count: int = 0
    resolution: str = "1920x1080"
    fps: int = 24
    codec: str = "h264"
    file_size_mb: float = 0.0
    success: bool = False
    error: str = ""


# ============================================================
# FFmpeg Detection
# ============================================================

def _check_ffmpeg() -> Tuple[bool, str]:
    """Check if FFmpeg is available and return version."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            return True, version_line
        return False, "ffmpeg returned non-zero"
    except FileNotFoundError:
        return False, "ffmpeg not found in PATH"
    except Exception as e:
        return False, str(e)


def _detect_hw_encoder() -> str:
    """Detect available hardware encoder.

    Returns: "h264_nvenc" | "h264_amf" | "h264_qsv" | "libx264"
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        encoders = result.stdout
        if "h264_nvenc" in encoders:
            return "h264_nvenc"
        if "h264_amf" in encoders:
            return "h264_amf"
        if "h264_qsv" in encoders:
            return "h264_qsv"
    except Exception:
        pass
    return "libx264"


# ============================================================
# Cinema Composer
# ============================================================

class CinemaComposer:
    """将视频片段按分镜顺序剪辑合成最终 MP4。

    功能：
      1. 按 shot 顺序拼接视频片段
      2. 可选：场景切换过渡效果（crossfade）
      3. 可选：添加 BGM 背景音乐
      4. 输出 MP4

    使用方式：
        composer = CinemaComposer(output_dir="output")
        result = composer.compose(
            video_clips=["shot_01.mp4", "shot_02.mp4"],
            shot_list=shots,
            output_name="final_movie.mp4",
            bgm="background.mp3",
        )
    """

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # FFmpeg availability
        self._ffmpeg_ok, self._ffmpeg_version = _check_ffmpeg()
        self._hw_encoder = _detect_hw_encoder() if self._ffmpeg_ok else "libx264"

        if self._ffmpeg_ok:
            logger.info(
                f"CinemaComposer: FFmpeg {self._ffmpeg_version}, "
                f"encoder={self._hw_encoder}"
            )
        else:
            logger.warning(
                "CinemaComposer: FFmpeg not available. "
                "Install FFmpeg from https://ffmpeg.org/download.html"
            )

    # ── Public API ────────────────────────────────────────────

    def compose(
        self,
        video_clips: List[str],
        shot_list: Optional[List[Any]] = None,
        output_name: str = "final_movie.mp4",
        add_transitions: bool = True,
        bgm: Optional[str] = None,
        fps: int = 24,
        resolution: str = "1920x1080",
    ) -> ComposeResult:
        """合成最终影片。

        Args:
            video_clips: 视频文件路径列表（按 shot 顺序）。
            shot_list: Shot 对象列表（用于提取 duration 等元数据）。
            output_name: 输出文件名。
            add_transitions: 是否添加 crossfade 过渡。
            bgm: 背景音乐路径（可选）。
            fps: 输出帧率。
            resolution: 输出分辨率 "WxH"。

        Returns:
            ComposeResult with output path and metadata.
        """
        if not self._ffmpeg_ok:
            return ComposeResult(
                success=False,
                error="FFmpeg not available — install from https://ffmpeg.org/download.html",
            )

        # Filter valid clips
        valid_clips = [c for c in video_clips if c and os.path.isfile(c)]
        if not valid_clips:
            return ComposeResult(
                success=False,
                error="No valid video clips provided",
            )

        output_path = str(self.output_dir / output_name)

        try:
            if add_transitions and len(valid_clips) > 1:
                result = self._compose_with_transitions(
                    valid_clips, output_path, fps, resolution, bgm
                )
            else:
                result = self._compose_concat(
                    valid_clips, output_path, fps, resolution, bgm
                )
            return result
        except Exception as e:
            logger.error(f"CinemaComposer.compose failed: {e}")
            return ComposeResult(
                output_path=output_path,
                clip_count=len(valid_clips),
                success=False,
                error=str(e),
            )

    def compose_from_shots(
        self,
        shots: List[Any],
        video_map: Dict[str, str],
        output_name: str = "final_movie.mp4",
        **kwargs,
    ) -> ComposeResult:
        """从 Shot 对象和视频映射合成。

        Args:
            shots: Shot 对象列表。
            video_map: shot_id → video_path 映射。
            output_name: 输出文件名。
            **kwargs: 传递给 compose() 的其他参数。

        Returns:
            ComposeResult.
        """
        clips = []
        for shot in shots:
            shot_id = str(getattr(shot, "shot_id", ""))
            if shot_id in video_map:
                clips.append(video_map[shot_id])

        return self.compose(
            video_clips=clips,
            shot_list=shots,
            output_name=output_name,
            **kwargs,
        )

    # ── Internal: Composition Methods ─────────────────────────

    def _compose_concat(
        self,
        clips: List[str],
        output: str,
        fps: int,
        resolution: str,
        bgm: Optional[str] = None,
    ) -> ComposeResult:
        """Simple concat via FFmpeg concat demuxer."""
        # Build concat file
        concat_file = str(self.output_dir / "_concat_list.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for clip in clips:
                abs_path = os.path.abspath(clip).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", self._hw_encoder,
        ]

        # Hardware encoder-specific params
        if self._hw_encoder == "h264_nvenc":
            cmd.extend(["-preset", "p4", "-rc", "vbr", "-cq", "23"])
        elif self._hw_encoder == "libx264":
            cmd.extend(["-preset", "medium", "-crf", "23"])

        cmd.extend([
            "-r", str(fps),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ])

        # Add BGM if provided
        if bgm and os.path.isfile(bgm):
            cmd.extend([
                "-i", bgm,
                "-filter_complex", "[1:a]volume=0.3[bgm];[0:a][bgm]amix=inputs=2:duration=first",
                "-shortest",
            ])

        cmd.append(output)

        return self._run_ffmpeg(cmd, output, len(clips))

    def _compose_with_transitions(
        self,
        clips: List[str],
        output: str,
        fps: int,
        resolution: str,
        bgm: Optional[str] = None,
    ) -> ComposeResult:
        """Compose with crossfade transitions between clips.

        Uses xfade filter for smooth scene transitions.
        Transition duration: 0.5s (12 frames at 24fps).
        """
        transition_frames = max(1, int(fps * 0.5))  # 0.5s crossfade
        offset_frames = 0

        # Build complex filter for crossfade
        filter_parts = []

        # Scale each input
        for i in range(len(clips)):
            filter_parts.append(f"[{i}:v]scale={resolution},fps={fps},setpts=PTS-STARTPTS[v{i}]")
            filter_parts.append(f"[{i}:a]aresample=async=1[va{i}]")

        # Crossfade chain
        prev_v = "[v0]"
        prev_a = "[va0]"
        for i in range(1, len(clips)):
            if i == 0:
                continue
            offset_frames += 72  # assuming 3s per clip minus 0.5s overlap
            filter_parts.append(
                f"{prev_v}[v{i}]xfade=transition=fade:duration={transition_frames/fps}:"
                f"offset={offset_frames/fps}[vx{i}]"
            )
            filter_parts.append(
                f"{prev_a}[va{i}]acrossfade=d={transition_frames/fps}[ax{i}]"
            )
            prev_v = f"[vx{i}]"
            prev_a = f"[ax{i}]"

        filter_graph = ";".join(filter_parts)

        cmd = ["ffmpeg", "-y"]
        for clip in clips:
            cmd.extend(["-i", clip])
        cmd.extend([
            "-filter_complex", filter_graph,
            "-map", prev_v,
            "-map", prev_a,
            "-c:v", self._hw_encoder,
        ])

        if self._hw_encoder == "h264_nvenc":
            cmd.extend(["-preset", "p4", "-rc", "vbr", "-cq", "23"])
        elif self._hw_encoder == "libx264":
            cmd.extend(["-preset", "medium", "-crf", "23"])

        cmd.extend([
            "-r", str(fps),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ])

        # BGM
        if bgm and os.path.isfile(bgm):
            cmd.extend([
                "-i", bgm,
                "-filter_complex",
                filter_graph + f";[{prev_a}]volume=1.0[va];[{len(clips)}:a]volume=0.3[bgm];[va][bgm]amix=inputs=2:duration=first",
            ])

        cmd.append(output)

        return self._run_ffmpeg(cmd, output, len(clips))

    def _run_ffmpeg(
        self,
        cmd: List[str],
        output: str,
        clip_count: int,
    ) -> ComposeResult:
        """Execute FFmpeg command and return result."""
        logger.debug(f"FFmpeg: {' '.join(cmd[:8])}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min timeout
            )

            if result.returncode != 0:
                # Log stderr for debugging
                stderr_tail = result.stderr.split("\n")[-5:]
                logger.error(f"FFmpeg failed: {stderr_tail}")
                return ComposeResult(
                    output_path=output,
                    clip_count=clip_count,
                    success=False,
                    error=f"FFmpeg exit code {result.returncode}: {'; '.join(stderr_tail)}",
                )

            # Get output file info
            file_size = os.path.getsize(output) if os.path.isfile(output) else 0
            duration = self._probe_duration(output)

            logger.info(
                f"CinemaComposer: {clip_count} clips → {output} "
                f"({file_size / 1024 / 1024:.1f} MB, {duration:.1f}s)"
            )

            return ComposeResult(
                output_path=output,
                duration_sec=duration,
                clip_count=clip_count,
                codec=self._hw_encoder,
                file_size_mb=file_size / 1024 / 1024,
                success=True,
            )

        except subprocess.TimeoutExpired:
            return ComposeResult(
                output_path=output,
                clip_count=clip_count,
                success=False,
                error="FFmpeg timed out (10 min)",
            )

    def _probe_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    # ── Static Utilities ──────────────────────────────────────

    @staticmethod
    def build_clip_list_from_shots(
        shots: List[Any],
        video_map: Dict[str, str],
    ) -> List[Tuple[str, float]]:
        """Build ordered clip list from shots.

        Returns: List of (video_path, duration_sec) tuples.
        """
        clips = []
        for shot in shots:
            shot_id = str(getattr(shot, "shot_id", ""))
            if shot_id in video_map:
                duration = float(getattr(shot, "duration_sec", 3.0) or 3.0)
                clips.append((video_map[shot_id], duration))
        return clips

    @staticmethod
    def is_available() -> bool:
        """Check if FFmpeg is available."""
        ok, _ = _check_ffmpeg()
        return ok
