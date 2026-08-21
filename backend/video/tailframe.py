"""Tail-frame extraction and linking module for video continuity.

This module provides utilities for extracting frames (first, last, or at a
specific timestamp) from video files using FFmpeg, resizing/cropping images
with Pillow, and a :class:`TailFrameLinker` that maintains visual continuity
across a sequence of shots by carrying the tail (last) frame of one shot
forward as the start image of the next.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_ffmpeg_exe() -> str:
    """Return the path to the FFmpeg executable.

    Prefers the binary bundled with ``imageio-ffmpeg``; falls back to the
    system ``ffmpeg`` if the package is unavailable.
    """
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _default_output_path(stem: str, suffix: str, ext: str = "png") -> Path:
    """Build a default output path in the system temp directory.

    Args:
        stem: Base name derived from the source file.
        suffix: Descriptive suffix (e.g. ``"last_frame"``).
        ext: File extension without the leading dot.

    Returns:
        A :class:`Path` inside ``tempfile.gettempdir()``.
    """
    return Path(tempfile.gettempdir()) / f"{stem}_{suffix}.{ext}"


def _run_ffmpeg(cmd: list[str]) -> bool:
    """Run an FFmpeg command and return ``True`` on success.

    Wraps :func:`subprocess.run` with ``capture_output=True`` and a
    30-second timeout.  Any failure is logged and reported as ``False``
    so callers can apply fallback strategies.

    Args:
        cmd: Command as a list of arguments (including the binary path).

    Returns:
        ``True`` if FFmpeg exited with code 0, ``False`` otherwise.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timed out after 30s: %s", " ".join(cmd))
        return False
    except FileNotFoundError:
        logger.error("FFmpeg binary not found: %s", cmd[0])
        return False
    except Exception:
        logger.exception("FFmpeg invocation failed: %s", " ".join(cmd))
        return False

    if result.returncode != 0:
        stderr_tail = ""
        if result.stderr:
            stderr_tail = result.stderr[-500:].decode(
                "utf-8", errors="replace"
            )
        logger.error(
            "FFmpeg exited with code %d: %s",
            result.returncode,
            stderr_tail,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Frame extraction functions
# ---------------------------------------------------------------------------

def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe.

    Prefers a real ffprobe next to the selected ffmpeg binary; falls back
    to the system ``ffprobe`` (the imageio-ffmpeg bundle does not ship one,
    so ``replace("ffmpeg", "ffprobe")`` would point at a nonexistent file).
    """
    import shutil
    ffmpeg = _get_ffmpeg_exe()
    ffprobe = ""
    for cand in (
        Path(ffmpeg).with_name("ffprobe"),
        Path(ffmpeg).with_name("ffprobe.exe"),
        Path(ffmpeg).with_name("ffprobe-win-x86_64.exe"),
        Path(ffmpeg).with_name("ffprobe-win-x64.exe"),
    ):
        if cand.is_file():
            ffprobe = str(cand)
            break
    if not ffprobe:
        ffprobe = shutil.which("ffprobe") or "ffprobe"
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


def _is_black_frame(image_path: Path, threshold: int = 15) -> bool:
    """Check if an image is mostly black (indicating a bad extraction).

    Per GPT advice, a true black frame has BOTH low brightness AND low edge
    density. Night scenes have low brightness but high edge density (buildings,
    lights, silhouettes), so they should not be falsely classified as black.

    Args:
        image_path: Path to the image file.
        threshold: Average pixel value below which the frame is considered dark.

    Returns:
        True if the frame is a true black frame (dark + no edges), False otherwise.
    """
    try:
        from PIL import Image
        import numpy as np

        with Image.open(image_path) as img:
            arr = np.array(img.convert("L"), dtype=np.float32)
            mean_val = arr.mean()

            # Only check edge density if brightness is low
            if mean_val < threshold:
                # Check edge density: true black frames have almost no edges
                gx = np.abs(np.diff(arr, axis=1))
                gy = np.abs(np.diff(arr, axis=0))
                edge_density = max(
                    float(gx.mean()) if gx.size > 0 else 0.0,
                    float(gy.mean()) if gy.size > 0 else 0.0,
                )
                # Night scenes have edge_density > 2.0 (buildings, lights, etc.)
                # True black frames have edge_density < 0.5
                return edge_density < 0.5

            return False
    except Exception:
        return False  # If we can't check, assume it's not black


def extract_last_frame(
    video_path: Path,
    output_path: Path | None = None,
) -> Path | None:
    """Extract the last frame from a video file.

    Uses a three-tier extraction strategy for maximum reliability:

    1. **Precise timestamp seek**: Gets the video duration via ffprobe,
       then seeks to (duration - 0.05)s. This avoids the black-frame
       risk of ``-sseof -0.1`` while still being frame-accurate.

    2. **End-of-file seek** (``-sseof -0.1``): Works as a fallback
       when ffprobe duration is unavailable.

    3. **Select filter** (``select=eq(n,N-1)``): Last resort; may fail
       on videos with B-frames or variable FPS.

    After extraction, a black-frame check is performed. If the extracted
    frame is mostly black, the next method is tried automatically.

    Args:
        video_path: Path to the source video.
        output_path: Destination PNG path.  If ``None``, a path is
            generated in the system temp directory.

    Returns:
        The path to the extracted frame, or ``None`` on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        logger.error("Video file not found: %s", video_path)
        return None

    if output_path is None:
        output_path = _default_output_path(video_path.stem, "last_frame")
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _get_ffmpeg_exe()

    # Method 1: Precise timestamp seek (duration - 0.05s)
    duration = _get_video_duration(video_path)
    if duration > 0.1:
        seek_time = max(0, duration - 0.05)
        cmd = [
            ffmpeg,
            "-ss", f"{seek_time:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-y",
            str(output_path),
        ]
        if _run_ffmpeg(cmd) and output_path.exists() and not _is_black_frame(output_path):
            logger.debug(
                "Extracted last frame via precise seek (%.3fs): %s",
                seek_time, output_path,
            )
            return output_path
        logger.debug(
            "Precise seek failed or black frame for %s (duration=%.2fs)",
            video_path, duration,
        )

    # Method 2: End-of-file seek (-sseof -0.1)
    cmd = [
        ffmpeg,
        "-sseof", "-0.1",
        "-i", str(video_path),
        "-frames:v", "1",
        "-y",
        str(output_path),
    ]
    if _run_ffmpeg(cmd) and output_path.exists() and not _is_black_frame(output_path):
        logger.debug(
            "Extracted last frame via -sseof: %s", output_path
        )
        return output_path

    logger.debug(
        "-sseof failed or black frame; trying select filter for %s", video_path
    )

    # Method 3: Select the last frame by index
    cmd = [
        ffmpeg,
        "-i", str(video_path),
        "-vf", r"select=eq(n\,N-1)",
        "-frames:v", "1",
        "-y",
        str(output_path),
    ]
    if _run_ffmpeg(cmd) and output_path.exists() and not _is_black_frame(output_path):
        logger.debug(
            "Extracted last frame via select filter: %s", output_path
        )
        return output_path

    # Last resort: return whatever we got even if it might be black
    if output_path.exists():
        logger.warning(
            "Last frame extracted but may be black: %s", output_path
        )
        return output_path

    logger.error("Failed to extract last frame from %s", video_path)
    return None


def extract_first_frame(
    video_path: Path,
    output_path: Path | None = None,
) -> Path | None:
    """Extract the first frame from a video file.

    Decodes only a single frame (``-frames:v 1``) which makes this
    operation very fast regardless of video length.

    Args:
        video_path: Path to the source video.
        output_path: Destination PNG path.  If ``None``, a path is
            generated in the system temp directory.

    Returns:
        The path to the extracted frame, or ``None`` on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        logger.error("Video file not found: %s", video_path)
        return None

    if output_path is None:
        output_path = _default_output_path(video_path.stem, "first_frame")
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _get_ffmpeg_exe()

    cmd = [
        ffmpeg,
        "-i", str(video_path),
        "-frames:v", "1",
        "-y",
        str(output_path),
    ]
    if _run_ffmpeg(cmd) and output_path.exists():
        logger.debug("Extracted first frame: %s", output_path)
        return output_path

    logger.error("Failed to extract first frame from %s", video_path)
    return None


def extract_frame_at(
    video_path: Path,
    timestamp: float,
    output_path: Path | None = None,
) -> Path | None:
    """Extract a frame at a specific timestamp.

    Uses FFmpeg's ``-ss`` option placed *before* the input (``-i``) for
    fast keyframe-based seeking.

    Args:
        video_path: Path to the source video.
        timestamp: Position in seconds from the start of the video.
        output_path: Destination PNG path.  If ``None``, a path is
            generated in the system temp directory.

    Returns:
        The path to the extracted frame, or ``None`` on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        logger.error("Video file not found: %s", video_path)
        return None

    if output_path is None:
        output_path = _default_output_path(
            video_path.stem, f"frame_{timestamp:.2f}"
        )
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _get_ffmpeg_exe()

    cmd = [
        ffmpeg,
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-y",
        str(output_path),
    ]
    if _run_ffmpeg(cmd) and output_path.exists():
        logger.debug(
            "Extracted frame at %.2fs: %s", timestamp, output_path
        )
        return output_path

    logger.error(
        "Failed to extract frame at %.2fs from %s", timestamp, video_path
    )
    return None


# ---------------------------------------------------------------------------
# Image resizing
# ---------------------------------------------------------------------------

def resize_and_crop_image(
    image_path: Path,
    target_width: int,
    target_height: int,
    output_path: Path | None = None,
) -> Path | None:
    """Resize and center-crop an image to target dimensions.

    The image is first scaled (preserving aspect ratio) so that it fully
    *covers* the target dimensions, then the center portion is cropped to
    the exact target size.  LANCZOS resampling is used for high-quality
    downscaling.

    Args:
        image_path: Path to the source image.
        target_width: Desired width in pixels.
        target_height: Desired height in pixels.
        output_path: Destination path.  If ``None``, a path is generated
            in the system temp directory.

    Returns:
        The path to the resized image, or ``None`` on failure.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        logger.error("Image file not found: %s", image_path)
        return None

    if output_path is None:
        output_path = _default_output_path(
            image_path.stem, f"{target_width}x{target_height}"
        )
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(image_path) as img:
            orig_width, orig_height = img.size

            # Scale to cover the target dimensions.
            ratio = max(
                target_width / orig_width,
                target_height / orig_height,
            )
            new_width = round(orig_width * ratio)
            new_height = round(orig_height * ratio)
            resized = img.resize(
                (new_width, new_height), Image.Resampling.LANCZOS
            )

            # Center-crop to the exact target dimensions.
            left = (new_width - target_width) // 2
            top = (new_height - target_height) // 2
            cropped = resized.crop(
                (
                    left,
                    top,
                    left + target_width,
                    top + target_height,
                )
            )
            cropped.save(output_path)
    except Exception:
        logger.exception(
            "Failed to resize/crop %s to %dx%d",
            image_path,
            target_width,
            target_height,
        )
        return None

    logger.debug(
        "Resized %s to %dx%d: %s",
        image_path,
        target_width,
        target_height,
        output_path,
    )
    return output_path


# ---------------------------------------------------------------------------
# Tail-frame linker
# ---------------------------------------------------------------------------

class TailFrameLinker:
    """Manage tail-frame linking across a sequence of shots.

    The linker maintains a mapping of shot IDs to their tail (last) frames
    and preserves the order in which shots were registered.  When
    generating a new shot, :meth:`get_start_image` returns the *previous*
    shot's tail frame (if one exists) so that consecutive shots share
    visual continuity.

    Typical usage::

        linker = TailFrameLinker(work_dir=Path("tmp/frames"))

        for shot in shots:
            start_img = linker.get_start_image(shot.id, shot.keyframe)
            video = generate_video(start_img, ...)
            tail = extract_last_frame(video)
            linker.set_tail_frame(shot.id, tail)

        linker.clear()
    """

    def __init__(self, work_dir: Path) -> None:
        """Initialize the linker with a working directory.

        Args:
            work_dir: Directory for storing temporary frame files.
                Created automatically if it does not exist.
        """
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._tail_frames: dict[str, Path] = {}
        self._order: list[str] = []

    def get_tail_frame(self, shot_id: str) -> Path | None:
        """Return the tail frame stored for a shot.

        Args:
            shot_id: Identifier of the shot.

        Returns:
            Path to the tail frame, or ``None`` if no frame has been
            registered for this shot.
        """
        return self._tail_frames.get(shot_id)

    def set_tail_frame(self, shot_id: str, frame_path: Path) -> None:
        """Store a shot's tail frame.

        The first call for a given ``shot_id`` also appends it to the
        internal ordering list so that :meth:`get_start_image` can
        determine which shot came before.

        Args:
            shot_id: Identifier of the shot.
            frame_path: Path to the tail frame image.
        """
        if shot_id not in self._tail_frames:
            self._order.append(shot_id)
        self._tail_frames[shot_id] = Path(frame_path)

    def get_start_image(
        self, shot_id: str, original_keyframe: Path
    ) -> Path:
        """Get the start image for a shot.

        If the previous shot (in registration order) has a tail frame,
        that frame is returned to preserve visual continuity between
        consecutive shots.  Otherwise the ``original_keyframe`` is
        returned unchanged.

        The lookup follows two strategies:

        * If ``shot_id`` has already been registered, the shot immediately
          before it in the ordering is used.
        * If ``shot_id`` has **not** been registered yet (the common case,
          since :meth:`get_start_image` is typically called before
          :meth:`set_tail_frame`), the most recently registered shot's
          tail frame is used.

        Args:
            shot_id: Identifier of the shot being generated.
            original_keyframe: Fallback keyframe to use when no prior
                tail frame is available.

        Returns:
            Path to the start image -- either the previous shot's tail
            frame or ``original_keyframe``.
        """
        original_keyframe = Path(original_keyframe)

        prev_frame: Path | None = None

        if shot_id in self._order:
            idx = self._order.index(shot_id)
            if idx > 0:
                prev_id = self._order[idx - 1]
                prev_frame = self._tail_frames.get(prev_id)
        elif self._order:
            # shot_id not yet registered -- use the most recent tail frame.
            prev_id = self._order[-1]
            prev_frame = self._tail_frames.get(prev_id)

        if prev_frame is not None and prev_frame.exists():
            return prev_frame
        return original_keyframe

    def clear(self) -> None:
        """Clear all stored tail frames.

        Removes every shot-to-frame mapping and resets the ordering list.
        Files on disk are *not* deleted.
        """
        self._tail_frames.clear()
        self._order.clear()


# ---------------------------------------------------------------------------
# Handoff Frame Selector (GPT Round-1: 取代"机械取最后一帧")
# ---------------------------------------------------------------------------
#
# 最后一帧往往恰是质量最差的帧（motion blur / 半闭眼 / 姿势扭曲 / 压缩异常）。
# 改为从尾部 8-12 帧中按质量评分挑选最佳"交接帧"，供下一镜作为起始图。

HANDOFF_CANDIDATE_COUNT = 12

# 评分权重（GPT Round-2: identity 0.25 / anatomy 0.20 / pose 0.20 /
#                        sharpness 0.15 / exposure 0.10 / composition 0.10）
HANDOFF_SCORE_WEIGHTS = {
    "identity": 0.25,
    "anatomy": 0.20,
    "pose": 0.20,
    "sharpness": 0.15,
    "exposure": 0.10,
    "composition": 0.10,
}


def extract_tail_candidates(
    video_path: Path,
    work_dir: Path,
    count: int = HANDOFF_CANDIDATE_COUNT,
) -> list[Path]:
    """Extract the last ``count`` frames of a video into ``work_dir``.

    Uses ``-sseof``/``-ss`` seeking to the tail region, then decodes the
    remaining frames at 1fps sampling. Returns the ordered list of frame
    paths (oldest -> newest); empty on failure.
    """
    video_path = Path(video_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if not video_path.exists():
        logger.error("Handoff: video not found %s", video_path)
        return []

    duration = _get_video_duration(video_path)
    if duration <= 0:
        return []

    ffmpeg = _get_ffmpeg_exe()
    # 从尾部 (count/fps) 秒开始逐帧抽取；用 fps 上限防止抽帧过多
    tail_start = max(0.0, duration - (count + 2))
    out_pattern = str(work_dir / f"{video_path.stem}_tail_%03d.png")
    cmd = [
        ffmpeg, "-y", "-ss", f"{tail_start:.3f}", "-i", str(video_path),
        "-vf", "fps=1", "-frames:v", str(count + 2),
        "-q:v", "2", out_pattern,
    ]
    if not _run_ffmpeg(cmd):
        return []

    frames = sorted(work_dir.glob(f"{video_path.stem}_tail_*.png"))
    # 去掉起始黑帧、保留最后 count 帧
    frames = [f for f in frames if not _is_black_frame(f)][-count:]
    return frames


def _score_handoff_frame(image_path: Path) -> dict[str, float]:
    """Score a candidate handoff frame (GPT Round-2 weights).

    Returns 0-1 normalized scores: identity / anatomy / pose / sharpness /
    exposure / composition. ``pose`` is proxied by the balance of vertical
    edge mass (silhouette) in the center strip.
    """
    score = {"identity": 0.0, "anatomy": 0.0, "pose": 0.0,
             "sharpness": 0.0, "exposure": 0.0, "composition": 0.0,
             "total": 0.0}
    try:
        import numpy as np
        from PIL import Image

        with Image.open(image_path) as img:
            gray = np.array(img.convert("L"), dtype=np.float32)
        h, w = gray.shape
        if h == 0 or w == 0:
            return score

        # Laplacian variance -> sharpness (normalized)
        gy = np.diff(np.diff(gray, axis=0), axis=0)  # (h-2, w)
        gx = np.diff(np.diff(gray, axis=1), axis=1)  # (h, w-2)
        lap = np.abs(gy[:, :-2]) + np.abs(gx[:-2, :])
        score["sharpness"] = min(1.0, float(lap.mean()) / 12.0)

        # Center subject region (typical framing zone)
        y0, y1 = int(h * 0.25), int(h * 0.85)
        x0, x1 = int(w * 0.15), int(w * 0.85)
        center = gray[y0:y1, x0:x1]
        if center.size == 0:
            return score

        # anatomy: center texture richness (edges/contrast)
        edges = float(np.abs(np.diff(center, axis=1)).mean()) + \
                float(np.abs(np.diff(center, axis=0)).mean())
        score["anatomy"] = min(1.0, edges / 16.0)

        # pose proxy: vertical edge-mass balance in center strip.
        # 边缘质量在中心列带上的左右分布 → 动作姿态(挥剑/举手)会偏离中心。
        strip_w = max(1, int(w * 0.30))
        left = center[:, :strip_w]
        right = center[:, -strip_w:]
        l_edges = float(np.abs(np.diff(left, axis=1)).mean()) if left.shape[1] > 1 else 0.0
        r_edges = float(np.abs(np.diff(right, axis=1)).mean()) if right.shape[1] > 1 else 0.0
        # 姿态明显（左右不对称）时给高分，避免"无姿态"的居中空镜
        score["pose"] = min(1.0, abs(l_edges - r_edges) / 6.0)

        # exposure: penalize clipped/too-dark/too-bright
        mean = float(center.mean())
        if 40 <= mean <= 210:
            score["exposure"] = 1.0 - min(1.0, abs(mean - 125) / 125)
        else:
            score["exposure"] = 0.3

        # composition: edge balance across 3x3 grid (reward central density)
        third_h, third_w = h // 3, w // 3
        grid = np.zeros(9, dtype=np.float32)
        for r in range(3):
            for c in range(3):
                cell = gray[r * third_h:(r + 1) * third_h, c * third_w:(c + 1) * third_w]
                grid[r * 3 + c] = float(np.abs(np.diff(cell, axis=1)).mean()) if cell.shape[1] > 1 else 0.0
        total_edges = float(grid.sum()) + 1e-6
        center_density = grid[4] / total_edges
        score["composition"] = min(1.0, center_density * 3.0)

        # identity: low variance across frame corners (stable subject)
        score["identity"] = min(1.0, max(0.0, 1.0 - float(grid.std()) / (total_edges + 1e-6)))
    except Exception:
        logger.exception("Handoff frame scoring failed: %s", image_path)

    score["total"] = sum(
        HANDOFF_SCORE_WEIGHTS[k] * score.get(k, 0.0)
        for k in HANDOFF_SCORE_WEIGHTS
    )
    return score


# ---------------------------------------------------------------------------
# Handoff metadata（GPT Round-2: 状态连续 -> 下一镜 prompt 注入）
# ---------------------------------------------------------------------------

def write_handoff_metadata(
    handoff_frame: Path,
    shot_id: str,
    character: dict | None = None,
    camera: dict | None = None,
    output_path: Path | None = None,
) -> dict:
    """Persist handoff state so the next shot can continue from it.

    Saves ``handoff_metadata.json`` next to the handoff frame, and returns a
    "Continue from previous shot" prompt fragment for the next shot.

    Example::

        write_handoff_metadata(
            frame, "S01", character={"face_id": "su_wan_v3", "pose": "right_arm_forward"},
            camera={"shot": "medium", "axis": "180"},
        )
    """
    meta = {
        "frame": Path(handoff_frame).name,
        "character": character or {},
        "camera": camera or {},
    }
    out = Path(output_path) if output_path else Path(handoff_frame).with_name("handoff_metadata.json")
    try:
        import json
        out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to write handoff metadata: %s", out)

    frag = ["Continue from previous shot:"]
    for key, val in (character or {}).items():
        if key not in ("face_id",):
            frag.append(f"{key.replace('_', ' ')}: {val}")
    if camera:
        frag.append(f"camera axis: {camera.get('axis', 'same')}, shot: {camera.get('shot', 'same')}")
    if character:
        frag.append(f"same character identity: {character.get('face_id', '')}".rstrip())
    return {"metadata": meta, "continuation_prompt": " ".join(frag)}


def select_handoff_frame(
    video_path: Path,
    work_dir: Path,
    count: int = HANDOFF_CANDIDATE_COUNT,
) -> Path | None:
    """Select the best handoff (交接) frame from a video's tail region.

    Returns the path of the best-scoring frame, or ``None`` on failure.
    """
    candidates = extract_tail_candidates(video_path, work_dir, count=count)
    if not candidates:
        return None
    best: tuple[float, Path] | None = None
    for cand in candidates:
        score = _score_handoff_frame(cand)
        if best is None or score["total"] > best[0]:
            best = (score["total"], cand)
    if best is None:
        return None
    logger.info("Handoff selected %s (total=%.3f)", best[1].name, best[0])
    return best[1]


# ---------------------------------------------------------------------------
# Handoff Continuity Score（GPT Round-3C：放弃 phash 0.75 全图标准）
# ---------------------------------------------------------------------------
#
# phash 只适合"同一动作的连续镜头"，不适合动作链切镜（S01 蓄力 -> S02 冲刺 ->
# S03 击退 视觉差异本来就大）。Round-3 改为语义连续分：
#   continuity_score = 0.35 identity + 0.25 costume + 0.20 pose_direction
#                      + 0.10 lighting + 0.10 background
# 阈值：动作链 >=0.65 PASS；同一连续镜 >=0.80。
# phash 保留为 visual_similarity（辅助参考），不再作为硬门禁。

CONTINUITY_WEIGHTS = {
    "identity": 0.35,
    "costume": 0.25,
    "pose_direction": 0.20,
    "lighting": 0.10,
    "background": 0.10,
}


def _load_gray(image_path: Path) -> "np.ndarray | None":
    import numpy as np
    from PIL import Image
    try:
        with Image.open(image_path) as img:
            return np.array(img.convert("L"), dtype=np.float32)
    except Exception:
        return None


def _load_rgb(image_path: Path) -> "np.ndarray | None":
    import numpy as np
    from PIL import Image
    try:
        with Image.open(image_path) as img:
            return np.array(img.convert("RGB"), dtype=np.uint8)
    except Exception:
        return None


def _hist_corr(a_rgb, b_rgb, roi_a=None, roi_b=None) -> float:
    """HSV 直方图相关性（0-1）。roi = (x0, y0, x1, y1) 或 None 取全图。"""
    import cv2
    import numpy as np
    try:
        def crop(img, roi):
            if roi is None:
                return img
            x0, y0, x1, y1 = roi
            return img[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
        ha = crop(a_rgb, roi_a)
        hb = crop(b_rgb, roi_b)
        if ha.size == 0 or hb.size == 0:
            return 0.5
        h_a = cv2.calcHist([cv2.cvtColor(ha, cv2.COLOR_RGB2HSV)], [0, 1], None, [24, 24], [0, 180, 0, 256])
        h_b = cv2.calcHist([cv2.cvtColor(hb, cv2.COLOR_RGB2HSV)], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(h_a, h_a, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(h_b, h_b, 0, 1, cv2.NORM_MINMAX)
        return float(max(0.0, cv2.compareHist(h_a, h_b, cv2.HISTCMP_CORREL)))
    except Exception:
        return 0.5


def compute_continuity_score(prev_frame: Path, next_frame: Path) -> dict:
    """Compute GPT Round-3C Handoff Continuity Score between two frames.

    Args:
        prev_frame: 上一镜的 handoff 帧（结尾帧）。
        next_frame: 下一镜的首帧（起帧）。

    Returns dict with per-dimension scores + weighted ``continuity_score``
    + ``visual_similarity``（phash 汉明相似度，仅作参考）。
    """
    prev_frame, next_frame = Path(prev_frame), Path(next_frame)
    result = {k: 0.0 for k in CONTINUITY_WEIGHTS}
    result["continuity_score"] = 0.0
    result["visual_similarity"] = 0.0
    if not prev_frame.exists() or not next_frame.exists():
        return result

    pa = _load_rgb(prev_frame)
    na = _load_rgb(next_frame)
    pg = _load_gray(prev_frame)
    ng = _load_gray(next_frame)
    if pa is None or na is None or pg is None or ng is None:
        return result

    h, w = pg.shape

    # --- identity: 人脸区域直方图（无脸时用中心主体区）---
    try:
        from backend.video.face_report import _get_detector, _detect_faces
        import cv2
        det = _get_detector()
        faces_p = _detect_faces(det, cv2.cvtColor(pa, cv2.COLOR_RGB2BGR)) if det else []
        faces_n = _detect_faces(det, cv2.cvtColor(na, cv2.COLOR_RGB2BGR)) if det else []
        if faces_p and faces_n:
            _, xp, yp, wp, hp = max(faces_p, key=lambda f: f[0])
            _, xn, yn, wn, hn = max(faces_n, key=lambda f: f[0])
            result["identity"] = _hist_corr(
                pa, na,
                (int(xp), int(yp), int(xp + wp), int(yp + hp)),
                (int(xn), int(yn), int(xn + wn), int(yn + hn)),
            )
        else:
            # 无脸：中心主体带直方图（漫剧远景/背影常见）
            y0, y1, x0, x1 = int(h * 0.2), int(h * 0.9), int(w * 0.2), int(w * 0.8)
            result["identity"] = _hist_corr(pa, na, (x0, y0, x1, y1), (x0, y0, x1, y1))
    except Exception:
        result["identity"] = 0.5

    # --- costume: 全身/主体区域颜色一致性（去背景干扰：中心竖直带）---
    band_x0, band_x1 = int(w * 0.25), int(w * 0.75)
    result["costume"] = _hist_corr(pa, na, (band_x0, 0, band_x1, h), (band_x0, 0, band_x1, h))

    # --- pose_direction: 主体位置 + 朝向（边缘质心横向位移代理）---
    try:
        import numpy as np
        def edge_cx(gray):
            gx = np.abs(np.diff(gray, axis=1))
            gy = np.abs(np.diff(gray, axis=0))
            edges = np.zeros_like(gray)
            edges[:, :-1] += gx
            edges[:-1, :] += gy
            rows = np.arange(edges.shape[1], dtype=np.float32)
            total = float(edges.sum()) + 1e-6
            return float((edges.sum(axis=0) * rows).sum() / total) / w  # 0-1 归一化 x 质心
        cxp, cxn = edge_cx(pg), edge_cx(ng)
        # 位置越近越好；朝向差异由边缘分布相似度补充
        pos_sim = 1.0 - abs(cxp - cxn)
        edge_hist_p = _hist_corr(pa, na, (0, 0, w, h), (0, 0, w, h))
        result["pose_direction"] = float(max(0.0, min(1.0, 0.6 * pos_sim + 0.4 * edge_hist_p)))
    except Exception:
        result["pose_direction"] = 0.5

    # --- lighting: 亮度直方图相关性 ---
    try:
        import cv2
        import numpy as np
        lp = cv2.calcHist([pg.astype(np.uint8)], [0], None, [32], [0, 256])
        ln = cv2.calcHist([ng.astype(np.uint8)], [0], None, [32], [0, 256])
        cv2.normalize(lp, lp, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(ln, ln, 0, 1, cv2.NORM_MINMAX)
        result["lighting"] = float(max(0.0, cv2.compareHist(lp, ln, cv2.HISTCMP_CORREL)))
    except Exception:
        result["lighting"] = 0.5

    # --- background: 四角区域（主体外）一致性 ---
    qh, qw = h // 4, w // 4
    corners_p = (0, 0, qw, qh), (w - qw, 0, w, qh), (0, h - qh, qw, h), (w - qw, h - qh, w, h)
    try:
        bg_scores = [
            _hist_corr(pa, na, (x0, y0, x1, y1), (x0, y0, x1, y1))
            for (x0, y0, x1, y1) in corners_p
        ]
        result["background"] = float(sum(bg_scores) / len(bg_scores))
    except Exception:
        result["background"] = 0.5

    result["continuity_score"] = round(
        sum(CONTINUITY_WEIGHTS[k] * result[k] for k in CONTINUITY_WEIGHTS), 3
    )

    # visual_similarity: phash 汉明相似度（保留，仅参考，不作为门禁）
    try:
        from backend.production.keyframe_generator import KeyframeGenerator
        hp = KeyframeGenerator._perceptual_hash(prev_frame)
        hn = KeyframeGenerator._perceptual_hash(next_frame)
        if hp and hn:
            dist = KeyframeGenerator._hamming_distance(hp, hn)
            result["visual_similarity"] = round(1.0 - dist / 64.0, 3)
    except Exception:
        result["visual_similarity"] = 0.0

    return result


class HandoffFrameSelector:
    """Opaque handle around :func:`select_handoff_frame`.

    Exists so callers can keep a stable reference without re-importing
    helpers; also compatible with a ``TailFrameLinker``-style workflow:
    ``set_tail_frame`` will pick the best tail candidate automatically.
    """

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def select(self, video_path: Path) -> Path | None:
        """Pick the best handoff frame for ``video_path``."""
        return select_handoff_frame(video_path, self.work_dir)

    def set_tail_frame(self, shot_id: str, video_path: Path) -> Path | None:
        """Extract + store the best handoff frame for ``shot_id``."""
        best = self.select(video_path)
        if best is not None:
            logger.info("Handoff frame stored for %s: %s", shot_id, best)
        return best
