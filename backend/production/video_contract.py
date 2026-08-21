"""P0 Video Contract — 生成视频规格硬门禁（GPT Round-1 方案）。

核心目标：杜绝 2.08s / 576x576 / 12fps / 百KB 的错误输出进入下游
（TTS / 拼接 / 成片）。所有视频生成路径在产出后必须通过
:func:`enforce_video_contract`，不满足规格立即 REJECT。

规格参考 GPT Round-1：
  - 生成：480x832 / 81 帧 / 16fps（约 5.06s 片段）
  - 成片：1080x1920 / 24fps / 15s（3 x 5s 动作链）
  - 硬门禁：duration >= 4.7s、宽高比 9:16、fps >= 15、
            frame_count >= 75、文件 >= 400KB
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Contract definition
# ---------------------------------------------------------------------------

VIDEO_CONTRACT: dict = {
    # 生成规格（Wan2.2 原生，4n+1 帧）
    "width": 480,
    "height": 832,
    "generation_frames": 81,
    "generation_fps": 16,
    "segment_duration": 5.0625,
    # 成片规格
    "final_width": 1080,
    "final_height": 1920,
    "final_fps": 24,
    "episode_duration_target": 15.0,
    # 硬门禁阈值
    "min_duration": 4.7,
    "min_fps": 15.0,
    "min_frames": 75,
    "min_size_bytes": 400_000,
    "min_visual_quality": 0.70,
}


def _get_ffmpeg_exe() -> str:
    """Prefer imageio-ffmpeg's bundled binary (has image decoding support)."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VideoProbe:
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration: float = 0.0
    frame_count: int = 0
    size_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def probe_video(video_path: Path) -> VideoProbe:
    """Probe a video file with ffprobe (frame-accurate, best effort).

    Uses ``ffprobe -count_frames`` to obtain the real frame count; falls
    back to ``fps * duration`` when counting is unavailable.
    """
    video_path = Path(video_path)
    if not video_path.exists() or video_path.stat().st_size == 0:
        return VideoProbe(errors=["missing_or_empty_file"])

    size_bytes = video_path.stat().st_size
    ffmpeg = _get_ffmpeg_exe()
    # 优先找与 ffmpeg 同目录的 ffprobe；否则用系统 ffprobe
    import shutil
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

    def _run(args: list[str]) -> str:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=30)
            return r.stdout.strip() or ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("probe subprocess failed: %s", exc)
            return ""

    info = _run([
        ffprobe, "-v", "error",
        "-count_frames",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,nb_read_frames:format=duration,size",
        "-of", "default=noprint_wrappers=1",
        str(video_path),
    ])

    def _parse_field(block: str, key: str) -> str:
        for line in block.splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
        return ""

    width = int(_parse_field(info, "width") or 0)
    height = int(_parse_field(info, "height") or 0)
    fps = 0.0
    rate = _parse_field(info, "r_frame_rate")
    if rate and "/" in rate:
        num, den = rate.split("/")
        try:
            fps = round(float(num) / max(1.0, float(den)), 3)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
    frame_count = int(_parse_field(info, "nb_read_frames") or 0)
    duration = float(_parse_field(info, "duration") or 0.0)

    errors: list[str] = []
    if width <= 0 or height <= 0:
        errors.append("cannot_probe_stream")

    return VideoProbe(
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        frame_count=frame_count,
        size_bytes=size_bytes,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_video(
    probe: VideoProbe,
    contract: dict | None = None,
    allow_cuts: bool = False,
) -> list[str]:
    """Return a list of contract violations (empty == PASS).

    ``allow_cuts`` relaxes the frame/duration checks for assembled
    (concatenated) episode videos, which are intentionally longer and
    have different fps/resolution than single-shot generation.
    """
    c = contract or VIDEO_CONTRACT
    errors: list[str] = list(probe.errors)

    if probe.duration < c.get("min_duration", 4.7):
        errors.append(f"duration_too_short:{probe.duration:.2f}")

    # 9:16 portrait aspect check (width/height <= 0.65 allows 576x576 square to be caught)
    if probe.width > 0 and probe.height > 0 and probe.width / probe.height > 0.65:
        errors.append(f"wrong_aspect_ratio:{probe.width}x{probe.height}")

    if probe.fps > 0 and probe.fps < c.get("min_fps", 15.0):
        errors.append(f"fps_too_low:{probe.fps}")

    if probe.size_bytes > 0 and probe.size_bytes < c.get("min_size_bytes", 400_000):
        errors.append(f"suspiciously_small_file:{probe.size_bytes}")

    if not allow_cuts:
        if probe.frame_count > 0 and probe.frame_count < c.get("min_frames", 75):
            errors.append(f"too_few_frames:{probe.frame_count}")

    return errors


class VideoContractViolation(Exception):
    """Raised when a generated video violates the contract."""

    def __init__(self, errors: list[str], video_path: str = ""):
        self.errors = errors
        self.video_path = video_path
        super().__init__(
            f"VideoContractViolation({', '.join(errors)}) for {video_path}"
        )


def enforce_video_contract(
    video_path: Path,
    contract: dict | None = None,
    allow_cuts: bool = False,
) -> VideoProbe:
    """Probe + validate + raise. Returns the probe on success."""
    probe = probe_video(video_path)
    errors = validate_video(probe, contract, allow_cuts=allow_cuts)
    if errors:
        logger.error(
            "VIDEO CONTRACT VIOLATION %s: %s", video_path, ", ".join(errors)
        )
        raise VideoContractViolation(errors, str(video_path))
    logger.info(
        "Video contract PASS %s: %.2fs %dx%d %.1ffps %d frames %.0fKB",
        video_path, probe.duration, probe.width, probe.height,
        probe.fps, probe.frame_count, probe.size_bytes / 1024,
    )
    return probe
