"""Frame interpolation module for extending AI-generated video duration.

Uses FFmpeg's minterpolate filter (or optionally RIFE via ComfyUI) to
double or triple the frame count of a generated video, effectively
extending a 2-second clip into a 4-6 second clip without re-running
the expensive Wan 2.1 inference.

Two modes:
  1. FFmpeg minterpolate - always available, moderate quality
  2. RIFE via ComfyUI - requires ComfyUI running, higher quality

The FFmpeg minterpolate approach is used as the default because it has
no additional dependencies and produces acceptable results for short
drama clips.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_ffmpeg_binary() -> str:
    """Return the FFmpeg binary path, preferring imageio-ffmpeg."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def interpolate_frames(
    input_path: Path,
    output_path: Path,
    target_fps: int = 24,
    multiplier: int = 2,
    mode: str = "auto",
) -> Path | None:
    """Double or triple the frame count of a video using FFmpeg minterpolate.

    Args:
        input_path: Source video file (e.g. 49 frames at 24fps = ~2s).
        output_path: Destination for the interpolated video.
        target_fps: Target output FPS (should match source for smoothness).
        multiplier: Frame multiplier (2 = double, 3 = triple).
        mode: minterpolate mode - "auto" (recommended) or "blend".

    Returns:
        Path to the interpolated video, or None on failure.

    Example:
        Input:  49 frames / 24fps = 2.04s
        Output (2x): 98 frames / 24fps = 4.08s
        Output (3x): 147 frames / 24fps = 6.12s
    """
    if not input_path.exists():
        logger.error("Frame interpolation: input video not found: %s", input_path)
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _get_ffmpeg_binary()

    # mi_mode=mif: motion interpolation, frame conversion
    # mc_mode=aobmc: advanced overlapped block motion compensation
    # me_mode=bidir: bidirectional motion estimation
    # me=epad: exhaustive padded search (better quality, slower)
    target_frame_rate = target_fps * multiplier

    # Use minterpolate to increase frame rate, then use setpts to slow down
    # the video to match the original duration multiplied by the factor.
    # This effectively creates "slow motion" with interpolated frames,
    # extending the visible duration.
    #
    # minterpolate doubles the frames by interpolating between existing ones.
    # setpts scales the timestamp so the video plays slower (longer duration).

    vf = (
        f"minterpolate="
        f"mi_mode=mif:"
        f"mc_mode=aobmc:"
        f"me_mode=bidir:"
        f"me=ehexbs:"
        f"mb_size=8:"
        f"vsbmc=1:"
        f"fps={target_frame_rate},"
        f"setpts={multiplier}.0*PTS,"
        f"fps={target_fps}"
    )

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-r", str(target_fps),
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes max
        )
        if result.returncode == 0 and output_path.exists():
            size = output_path.stat().st_size
            logger.info(
                "Frame interpolation: %s -> %s (%dx, %d KB)",
                input_path.name,
                output_path.name,
                multiplier,
                size // 1024,
            )
            return output_path

        logger.warning(
            "Frame interpolation minterpolate failed (rc=%d): %s",
            result.returncode,
            (result.stderr or "")[-500:],
        )
    except subprocess.TimeoutExpired:
        logger.warning("Frame interpolation timed out for %s", input_path)
    except Exception as exc:
        logger.warning("Frame interpolation error: %s", exc)

    # Fallback: simple frame duplication (lower quality but always works)
    logger.info("Falling back to simple frame duplication for %s", input_path)
    return _simple_frame_duplicate(input_path, output_path, multiplier, target_fps)


def _simple_frame_duplicate(
    input_path: Path,
    output_path: Path,
    multiplier: int,
    target_fps: int,
) -> Path | None:
    """Fallback: extend video by duplicating frames with setpts.

    This doesn't create new interpolated frames, but slows down the
    playback by stretching timestamps. Quality is lower but it always works.
    """
    ffmpeg = _get_ffmpeg_binary()

    vf = f"setpts={multiplier}.0*PTS,fps={target_fps}"

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-r", str(target_fps),
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and output_path.exists():
            logger.info(
                "Simple frame duplication: %s (%dx, %d KB)",
                output_path.name,
                multiplier,
                output_path.stat().st_size // 1024,
            )
            return output_path
        logger.warning(
            "Frame duplication failed: %s",
            (result.stderr or "")[-300:],
        )
    except Exception as exc:
        logger.warning("Frame duplication error: %s", exc)

    return None


def extend_video_duration(
    input_path: Path,
    output_path: Path | None = None,
    target_seconds: float = 6.0,
    source_fps: int = 24,
) -> Path:
    """Extend a short video clip to a target duration using frame interpolation.

    Calculates the required multiplier based on the source video's duration
    and the target duration, then applies frame interpolation.

    Args:
        input_path: Source video (typically ~2s from Wan2.1).
        output_path: Destination path. If None, overwrites the input.
        target_seconds: Desired output duration in seconds.
        source_fps: Source video FPS.

    Returns:
        Path to the extended video (may be the input if extension fails).
    """
    if output_path is None:
        output_path = input_path

    # Get source duration
    source_duration = _get_video_duration(input_path)
    if source_duration <= 0:
        source_duration = 2.0  # Default assumption

    # Calculate multiplier
    needed_multiplier = target_seconds / source_duration
    # Allow up to 15x for longer videos (2s * 15x = 30s per shot)
    multiplier = max(2, min(15, round(needed_multiplier)))

    logger.info(
        "Extending %s: %.1fs -> %.1fs (multiplier=%d)",
        input_path.name,
        source_duration,
        target_seconds,
        multiplier,
    )

    result = interpolate_frames(
        input_path=input_path,
        output_path=output_path,
        target_fps=source_fps,
        multiplier=multiplier,
    )

    if result is None:
        # If interpolation failed, return original
        logger.warning("Frame interpolation failed, keeping original video")
        return input_path

    return result


def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    ffmpeg = _get_ffmpeg_binary()
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet",
             "-show_entries", "format=duration",
             "-of", "csv=p=0",
             str(video_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (ValueError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return 0.0
