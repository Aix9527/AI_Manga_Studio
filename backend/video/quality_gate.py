"""Video Quality Gate module for detecting mosaic/noise in generated videos.

Per GPT optimization advice (v2), this module uses a **multi-indicator
fusion** approach instead of a single FFT metric. The Mosaic Score is
calculated as:

    mosaic_score = 0.4 * fft_high_freq_ratio
                 + 0.3 * block_artifact_variance
                 + 0.3 * edge_repetition_ratio

Additionally, a **Block Artifact Detection** algorithm checks for 8×8
block boundary discontinuities (a hallmark of JPEG/AI compression
artifacts that produce mosaic patterns).

Key improvements over v1:
  - Multi-indicator fusion reduces false positives (rain, sparks, leaves
    have high FFT but are NOT mosaic)
  - Block boundary analysis catches structural mosaic patterns
  - Edge repetition detection catches tiling/blocky patterns
  - Temporal consistency uses SSIM-style comparison (not just MSE)

Quality checks performed:
  1. Mosaic Score (multi-indicator fusion)
  2. Block Artifact Detection (8×8 block boundaries)
  3. Temporal consistency (SSIM-style)
  4. Brightness/luminance
  5. Color distribution
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FrameQuality:
    """Quality metrics for a single frame."""
    frame_index: int
    brightness: float = 0.0
    contrast: float = 0.0
    edge_density: float = 0.0
    high_freq_ratio: float = 0.0  # FFT high-frequency energy ratio
    block_artifact_score: float = 0.0  # 8x8 block boundary discontinuity
    edge_repetition_ratio: float = 0.0  # Repeated edge patterns (tiling)
    mosaic_score: float = 0.0  # Fused mosaic score (0-1, higher = worse)
    is_mosaic: bool = False
    is_too_dark: bool = False
    is_too_bright: bool = False
    score: float = 0.0  # 0-100, higher is better


@dataclass
class QualityReport:
    """Quality assessment report for a generated video."""
    video_path: str
    total_frames_checked: int = 0
    frames: list[FrameQuality] = field(default_factory=list)
    temporal_consistency: float = 0.0  # 0-1, higher is better
    overall_score: float = 0.0  # 0-100
    passed: bool = False
    failure_reasons: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    suggested_steps: int | None = None
    suggested_cfg: float | None = None
    suggested_denoise: float | None = None
    issues: list[str] = field(default_factory=list)  # GPT v2: structured issues
    # GPT P0: motion metrics — 定帧图检测
    mean_frame_diff: float = 0.0  # 平均相邻采样帧像素差
    static_frame_ratio: float = 1.0  # 静态帧占比 (0-1, 越高越像定帧图)
    motion_score: float = 0.0  # Farneback 光流平均幅度
    # GPT Phase-2: motion curve 质量 — 抖动/闪烁检测
    motion_std: float = 0.0  # 相邻帧差序列的标准差
    motion_cv: float = 0.0  # 变异系数 std/mean（越高越像随机闪烁）
    subject_visibility: float = 0.0  # 0-1，主体可见度（雾/暗部/失焦惩罚）

    @property
    def verdict(self) -> str:
        """Human-readable verdict."""
        if self.passed:
            return f"PASS (score: {self.overall_score:.1f}/100)"
        return f"FAIL (score: {self.overall_score:.1f}/100): {', '.join(self.failure_reasons)}"


def _get_ffmpeg_exe() -> str:
    """Return the FFmpeg binary path, preferring imageio-ffmpeg."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _extract_sample_frames(
    video_path: Path,
    output_dir: Path,
    num_frames: int = 5,
    skip_start: float = 0.0,
    skip_end: float = 0.0,
) -> list[Path]:
    """Extract evenly-spaced sample frames from a video for analysis.

    ``skip_start`` / ``skip_end`` (seconds) move the sampling window away from
    intentional black title cards (intro/outro), so those design elements are
    not misreported as mosaic frames.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _get_ffmpeg_exe()
    duration = _get_video_duration(video_path)
    if duration <= 0:
        duration = 2.0

    lo = min(skip_start, duration - 0.5)
    hi = max(lo, duration - skip_end)
    span = max(0.1, hi - lo)

    timestamps = []
    if num_frames == 1:
        timestamps = [lo + span / 2]
    else:
        interval = span / (num_frames + 1)
        timestamps = [lo + interval * (i + 1) for i in range(num_frames)]

    frame_paths = []
    for i, ts in enumerate(timestamps):
        frame_path = output_dir / f"frame_{i:03d}.png"
        cmd = [
            ffmpeg, "-ss", f"{ts:.3f}",
            "-i", str(video_path),
            "-frames:v", "1", "-y", str(frame_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode == 0 and frame_path.exists():
                frame_paths.append(frame_path)
        except Exception:
            pass
    return frame_paths


def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    ffmpeg = _get_ffmpeg_exe()
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (ValueError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Multi-indicator mosaic detection (GPT v2)
# ---------------------------------------------------------------------------

def _compute_fft_high_freq(gray: np.ndarray) -> float:
    """Compute the high-frequency energy ratio using FFT.

    High ratio indicates lots of fine detail/noise, but NOT necessarily
    mosaic — rain, sparks, and leaves also produce high FFT values.
    This is why it's only 40% of the final mosaic score.
    """
    h, w = gray.shape
    if h < 8 or w < 8:
        return 0.0

    try:
        import numpy as np
        f_transform = np.fft.fft2(gray)
        f_shift = np.fft.fftshift(f_transform)
        magnitude = np.abs(f_shift)

        cy, cx = h // 2, w // 2
        radius = min(h, w) // 8

        y, x = np.ogrid[:h, :w]
        low_freq_mask = (y - cy) ** 2 + (x - cx) ** 2 <= radius ** 2

        low_freq_energy = magnitude[low_freq_mask].sum()
        total_energy = magnitude.sum()

        if total_energy > 0:
            high_freq_energy = total_energy - low_freq_energy
            return float(high_freq_energy / total_energy)
    except Exception:
        pass
    return 0.0


def _compute_block_artifact_score(gray: np.ndarray, block_size: int = 8) -> float:
    """Detect block boundary discontinuities (JPEG/AI mosaic artifacts).

    Mosaic patterns produce sharp discontinuities at block boundaries
    (typically 8×8 or 16×16). This function measures the variance of
    pixel differences at block edges vs. within blocks.

    High score = blocky artifacts present = likely mosaic.
    Low score = smooth transitions = natural image.

    Args:
        gray: Grayscale image as numpy array.
        block_size: Expected block size (8 for JPEG-style artifacts).

    Returns:
        Block artifact score (0-1, higher = more blocky).
    """
    h, w = gray.shape
    if h < block_size * 2 or w < block_size * 2:
        return 0.0

    try:
        import numpy as np

        # Compute gradient at block boundaries
        # Horizontal boundaries (every block_size rows)
        h_boundary_diffs = []
        for y in range(block_size, h - block_size, block_size):
            diff = np.abs(gray[y, :] - gray[y - 1, :])
            h_boundary_diffs.append(float(diff.mean()))

        # Vertical boundaries (every block_size columns)
        v_boundary_diffs = []
        for x in range(block_size, w - block_size, block_size):
            diff = np.abs(gray[:, x] - gray[:, x - 1])
            v_boundary_diffs.append(float(diff.mean()))

        # Within-block gradients (for comparison)
        within_diffs = []
        for y in range(0, h - 1, block_size // 2):
            for x in range(0, w - 1, block_size // 2):
                if y + 1 < h and x + 1 < w:
                    within_diffs.append(
                        float(np.abs(gray[y, x] - gray[y + 1, x]))
                    )

        if not h_boundary_diffs or not v_boundary_diffs or not within_diffs:
            return 0.0

        boundary_mean = np.mean(h_boundary_diffs + v_boundary_diffs)
        within_mean = np.mean(within_diffs)

        if within_mean > 0:
            ratio = boundary_mean / within_mean
            # Ratio > 1.5 means boundaries are significantly stronger
            # than within-block content → blocky artifacts
            return float(min(1.0, max(0.0, (ratio - 1.0) / 1.5)))
        return 0.0
    except Exception:
        return 0.0


def _compute_edge_repetition(gray: np.ndarray) -> float:
    """Detect repeated edge patterns (tiling/blocky mosaic).

    Mosaic patterns often produce regularly repeating edge structures.
    This function measures the autocorrelation of edge positions to
    detect such repetition.

    High score = repeated patterns = likely mosaic.
    Low score = natural, varied edges = natural image.
    """
    h, w = gray.shape
    if h < 16 or w < 16:
        return 0.0

    try:
        import numpy as np

        # Compute edge map (simple gradient)
        gx = np.abs(np.diff(gray, axis=1))
        gy = np.abs(np.diff(gray, axis=0))

        # Pad to same size
        gx_pad = np.zeros_like(gray)
        gy_pad = np.zeros_like(gray)
        gx_pad[:, :w-1] = gx
        gy_pad[:h-1, :] = gy

        edges = gx_pad + gy_pad

        # Downsample for autocorrelation (faster)
        step = max(1, min(h, w) // 64)
        edges_small = edges[::step, ::step]

        # Compute autocorrelation via FFT
        f_edges = np.fft.fft2(edges_small)
        autocorr = np.abs(np.fft.ifft2(f_edges * np.conj(f_edges)))
        autocorr = np.fft.fftshift(autocorr)

        # Find peaks (excluding center)
        center_y, center_x = autocorr.shape[0] // 2, autocorr.shape[1] // 2
        total_energy = autocorr.sum()

        if total_energy <= 0:
            return 0.0

        # Check for periodic peaks (non-center high values)
        # Mask out center region
        y, x = np.ogrid[:autocorr.shape[0], :autocorr.shape[1]]
        center_mask = (y - center_y) ** 2 + (x - center_x) ** 2 <= 4
        non_center = autocorr.copy()
        non_center[center_mask] = 0

        # Find the maximum non-center peak
        max_peak = float(non_center.max())
        center_peak = float(autocorr[center_y, center_x])

        if center_peak > 0:
            # High ratio means strong repeating pattern
            ratio = max_peak / center_peak
            return float(min(1.0, ratio * 2.0))
        return 0.0
    except Exception:
        return 0.0


def _analyze_frame(frame_path: Path, frame_index: int) -> FrameQuality:
    """Analyze a single frame for quality metrics using multi-indicator fusion.

    Per GPT v2, the mosaic detection uses three complementary indicators:
    1. FFT high-frequency ratio (40%) — catches noise/fine detail
    2. Block artifact score (30%) — catches 8x8 boundary discontinuities
    3. Edge repetition ratio (30%) — catches tiling/repeating patterns

    A frame is classified as mosaic only when the fused score exceeds
    the threshold, reducing false positives from natural high-freq content.
    """
    fq = FrameQuality(frame_index=frame_index)

    try:
        import numpy as np
        from PIL import Image

        with Image.open(frame_path) as img:
            gray = np.array(img.convert("L"), dtype=np.float32)

        h, w = gray.shape

        # Brightness
        fq.brightness = float(gray.mean())
        if fq.brightness < 15:
            fq.is_too_dark = True
        elif fq.brightness > 240:
            fq.is_too_bright = True

        # Contrast
        fq.contrast = float(gray.std())

        # Edge density
        gx = np.abs(np.diff(gray, axis=1))
        gy = np.abs(np.diff(gray, axis=0))
        edges = np.concatenate([
            gx.mean(axis=0) if gx.size > 0 else np.array([0]),
            gy.mean(axis=1) if gy.size > 0 else np.array([0]),
        ])
        fq.edge_density = float(edges.mean())

        # === Multi-indicator mosaic detection (GPT v2) ===
        # 1. FFT high-frequency ratio (40% weight)
        fq.high_freq_ratio = _compute_fft_high_freq(gray)

        # 2. Block artifact score (30% weight) — 8x8 block boundaries
        fq.block_artifact_score = _compute_block_artifact_score(gray, block_size=8)

        # 3. Edge repetition ratio (30% weight) — tiling detection
        fq.edge_repetition_ratio = _compute_edge_repetition(gray)

        # Fused mosaic score
        fq.mosaic_score = (
            0.4 * fq.high_freq_ratio
            + 0.3 * fq.block_artifact_score
            + 0.3 * fq.edge_repetition_ratio
        )

        # Mosaic threshold: 0.6 (lowered from 0.85 to catch more, but
        # multi-indicator fusion prevents false positives)
        # Require real 8x8 block-boundary evidence; pure high-FFT detail /
        # directional edges on sharp anime frames are not mosaic.
        if fq.mosaic_score > 0.6 and fq.block_artifact_score > 0.25:
            fq.is_mosaic = True

        # Compute frame score (0-100)
        score = 50.0
        if not fq.is_mosaic:
            score += 20
        if not fq.is_too_dark and not fq.is_too_bright:
            score += 10
        if fq.contrast > 20:
            score += 10
        if fq.edge_density > 5:
            score += 10
        # Bonus for low block artifacts
        if fq.block_artifact_score < 0.2:
            score += 5
        # Penalty for high mosaic score (even if below threshold)
        score -= min(8.0, fq.mosaic_score * 15)
        fq.score = max(0, min(100, score))

    except Exception as exc:
        logger.warning("Frame analysis failed for %s: %s", frame_path, exc)
        fq.score = 50.0

    return fq


def _compute_temporal_consistency(frame_paths: list[Path]) -> float:
    """Compute temporal consistency using SSIM-style comparison.

    Per GPT v2, plain MSE can be misleading for camera motion scenes.
    This implementation uses a structure-based comparison that is more
    robust to global motion while still detecting flickering.
    """
    if len(frame_paths) < 2:
        return 1.0

    try:
        import numpy as np
        from PIL import Image

        similarities = []
        prev_arr = None

        for fp in frame_paths:
            with Image.open(fp) as img:
                arr = np.array(img.convert("L"), dtype=np.float32)
                # Downsample for faster comparison
                if arr.shape[0] > 256 or arr.shape[1] > 256:
                    step_y = arr.shape[0] // 256
                    step_x = arr.shape[1] // 256
                    if step_y > 0 and step_x > 0:
                        arr = arr[::step_y, ::step_x]

                if prev_arr is not None and arr.shape == prev_arr.shape:
                    # SSIM-style: compare structure (not just pixel values)
                    # Compute local statistics
                    mu1, mu2 = prev_arr.mean(), arr.mean()
                    sigma1, sigma2 = prev_arr.std(), arr.std()

                    # Structural similarity
                    numerator = 2 * mu1 * mu2 + 1.0
                    denominator = mu1 ** 2 + mu2 ** 2 + 1.0
                    luminance_sim = numerator / denominator

                    # Contrast similarity
                    c_num = 2 * sigma1 * sigma2 + 1.0
                    c_den = sigma1 ** 2 + sigma2 ** 2 + 1.0
                    contrast_sim = c_num / c_den

                    # Structure: correlation coefficient
                    diff1 = prev_arr - mu1
                    diff2 = arr - mu2
                    cov = (diff1 * diff2).mean()
                    structure_sim = cov / (sigma1 * sigma2 + 1e-8)

                    # Combined SSIM
                    ssim = luminance_sim * contrast_sim * abs(structure_sim)
                    similarities.append(float(ssim))

                prev_arr = arr

        if similarities:
            return float(np.mean(similarities))
        return 1.0

    except Exception as exc:
        logger.warning("Temporal consistency computation failed: %s", exc)
        return 0.5


# ---------------------------------------------------------------------------
# Motion gate (GPT P0): 检测"定帧图"式伪视频
# ---------------------------------------------------------------------------

# 相邻采样帧视为"静态"的像素差阈值（256px 宽、约 6fps 采样）
STATIC_FRAME_DIFF_THRESHOLD = 0.5
# 静态帧占比上限：超过 40% 判为定帧图（GPT 建议 static_ratio < 40%）
STATIC_RATIO_LIMIT = 0.40
# 平均帧差下限：低于该值基本无运动
MIN_MEAN_FRAME_DIFF = 0.30
# 光流运动分下限（secondary signal）
MIN_MOTION_SCORE = 0.15
# GPT Phase-2: 运动曲线抖动门禁（防"闪烁/脉冲"式伪运动）
FLICKER_MIN_MEAN_DIFF = 10.0  # 平均帧差高于此值才可能判闪烁
FLICKER_MAX_MOTION_CV = 0.65  # 变异系数超过此值判为随机抖动


def _read_sample_frames(
    video_path: Path,
    max_frames: int = 40,
    sample_rate: float = 6.0,
    target_width: int = 256,
) -> list["np.ndarray"]:
    """Read evenly time-sampled grayscale frames (float32, downscaled).

    Sampling by wall-clock time (~6 fps) keeps the motion metric meaningful
    even after minterpolate/setpts duration changes.
    """
    try:
        import imageio.v2 as imageio
        import numpy as np
    except Exception as exc:
        logger.warning("Motion gate unavailable (numpy/imageio): %s", exc)
        return []

    try:
        reader = imageio.get_reader(str(video_path))
        raw: list[np.ndarray] = []
        for frame in reader:
            arr = np.asarray(frame)
            if arr.ndim == 3 and arr.shape[2] >= 3:
                arr = arr.mean(axis=2)
            elif arr.ndim == 3:
                arr = arr[..., 0]
            raw.append(arr.astype(np.float32))
        reader.close()
    except Exception as exc:
        logger.warning("Motion gate frame read failed for %s: %s", video_path, exc)
        return []

    if not raw:
        return []
    if len(raw) == 1:
        return [raw[0]]

    # Evenly sample ~sample_rate fps, capped at max_frames
    fps_est = max(len(raw) / 2.0, sample_rate * 2.0)
    count = max(4, min(max_frames, int(round(len(raw) / max(1.0, fps_est / sample_rate)))))
    count = min(count, len(raw))
    indices = [int(round(i * (len(raw) - 1) / (count - 1))) for i in range(count)]
    indices = sorted(set(indices))
    selected = [raw[i] for i in indices]

    # Downscale to a consistent width so thresholds are resolution-independent
    try:
        from PIL import Image
        out = []
        for f in selected:
            h, w = f.shape
            new_w = target_width
            new_h = max(1, int(round(h * new_w / w)))
            img = Image.fromarray(f.astype(np.uint8)).convert("L")
            out.append(np.asarray(img.resize((new_w, new_h), Image.Resampling.BILINEAR), dtype=np.float32))
        return out
    except Exception:
        return selected


def compute_motion_metrics(
    video_path: Path,
) -> dict[str, float]:
    """Compute frame-difference / static-ratio / optical-flow metrics.

    Returns:
        dict with ``mean_frame_diff``, ``static_frame_ratio``,
        ``motion_score`` and ``frame_count``. Metrics stay 0 on failure so
        the gate fails closed (a video that cannot be analyzed is rejected
        by the caller).
    """
    try:
        import numpy as np
    except Exception as exc:
        logger.warning("Motion gate unavailable (numpy): %s", exc)
        return {"mean_frame_diff": 0.0, "static_frame_ratio": 1.0, "motion_score": 0.0, "frame_count": 0.0}

    frames = _read_sample_frames(Path(video_path))
    result = {"mean_frame_diff": 0.0, "static_frame_ratio": 1.0, "motion_score": 0.0, "motion_std": 0.0, "motion_cv": 0.0, "frame_count": float(len(frames))}
    if len(frames) < 2:
        return result

    diffs = []
    for i in range(len(frames) - 1):
        diffs.append(float(np.abs(frames[i + 1] - frames[i]).mean()))
    mean_diff = float(np.mean(diffs))
    static_ratio = float(np.mean([1.0 if d < STATIC_FRAME_DIFF_THRESHOLD else 0.0 for d in diffs]))
    result["mean_frame_diff"] = mean_diff
    result["static_frame_ratio"] = static_ratio
    result["motion_std"] = float(np.std(diffs))
    result["motion_cv"] = float(np.std(diffs) / max(mean_diff, 1e-6))

    # Optical flow (secondary signal; skip gracefully when cv2 is missing)
    try:
        import cv2
        small_width = 160
        small = []
        for f in frames:
            h, w = f.shape
            new_h = max(1, int(round(h * small_width / w)))
            small.append(cv2.resize(f, (small_width, new_h), interpolation=cv2.INTER_AREA).astype(np.float32))
        magnitudes = []
        for i in range(len(small) - 1):
            flow = cv2.calcOpticalFlowFarneback(
                small[i], small[i + 1], None,
                0.5, 3, 15, 3, 5, 1.2, 0,
            )
            magnitudes.append(float(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean()))
        if magnitudes:
            result["motion_score"] = float(np.mean(magnitudes))
    except Exception as exc:
        logger.debug("Optical flow skipped: %s", exc)

    return result



def _compute_subject_visibility(frame_path: Path) -> float:
    """Heuristic 0-1 score for subject visibility (fog/dark/blur penalty)."""
    try:
        import numpy as np
        from PIL import Image
        with Image.open(frame_path) as img:
            gray = np.array(img.convert("L"), dtype=np.float32)
        h, w = gray.shape
        # Central subject region (typical framing zone)
        y0, y1 = int(h * 0.2), int(h * 0.8)
        x0, x1 = int(w * 0.2), int(w * 0.8)
        center = gray[y0:y1, x0:x1]
        if center.size == 0:
            return 0.5
        mean = float(center.mean())
        contrast = float(center.std())
        edges = float(np.abs(np.diff(center, axis=1)).mean()) if center.shape[1] > 1 else 0.0
        bright = min(1.0, mean / 80.0)
        c_score = min(1.0, contrast / 35.0)
        e_score = min(1.0, edges / 8.0)
        return float(max(0.0, min(1.0, 0.4 * c_score + 0.4 * e_score + 0.2 * bright)))
    except Exception:  # noqa: BLE001
        return 0.5


def check_video_quality(
    video_path: Path,
    strict: bool = False,
    skip_start_seconds: float = 0.0,
    skip_end_seconds: float = 0.0,
    allow_cuts: bool = False,
) -> QualityReport:
    """Run quality checks on a generated video using multi-indicator fusion.

    Per GPT v2, uses Mosaic Score = 0.4*FFT + 0.3*block_variance + 0.3*edge_repeat
    instead of single FFT threshold. This reduces false positives from natural
    high-frequency content (rain, sparks, leaves) while still catching true
    AI-generated mosaic patterns.

    Args:
        video_path: Path to the generated video file.
        strict: If True, use stricter thresholds.
        skip_start_seconds: Seconds to skip from the start (e.g. black intro).
        skip_end_seconds: Seconds to skip from the end (e.g. title card).

    Returns:
        QualityReport with multi-indicator assessment.
    """
    video_path = Path(video_path)
    report = QualityReport(video_path=str(video_path))

    if not video_path.exists():
        report.failure_reasons.append("Video file not found")
        report.recommendations.append("Re-generate the video")
        report.issues.append("missing_file")
        return report

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dir = Path(tmpdir)
        frame_paths = _extract_sample_frames(video_path, tmp_dir, num_frames=5, skip_start=skip_start_seconds, skip_end=skip_end_seconds)

        if not frame_paths:
            report.failure_reasons.append("Could not extract any frames for analysis")
            report.recommendations.append("Check video file integrity")
            report.issues.append("corrupt_video")
            return report

        report.total_frames_checked = len(frame_paths)

        mosaic_count = 0
        dark_count = 0
        bright_count = 0
        block_artifact_count = 0
        score_sum = 0.0
        vis_scores: list[float] = []

        for i, fp in enumerate(frame_paths):
            fq = _analyze_frame(fp, i)
            report.frames.append(fq)
            score_sum += fq.score
            vis_scores.append(_compute_subject_visibility(fp))
            if fq.is_mosaic:
                mosaic_count += 1
            if fq.is_too_dark:
                dark_count += 1
            if fq.is_too_bright:
                bright_count += 1
            if fq.block_artifact_score > 0.5:
                block_artifact_count += 1

        report.temporal_consistency = _compute_temporal_consistency(frame_paths)
        report.subject_visibility = round(sum(vis_scores) / len(vis_scores), 3) if vis_scores else 0.0

    # GPT P0: motion gate — 拒绝定帧图/伪视频
    motion = compute_motion_metrics(video_path)
    report.mean_frame_diff = motion["mean_frame_diff"]
    report.static_frame_ratio = motion["static_frame_ratio"]
    report.motion_score = motion["motion_score"]
    report.motion_std = motion.get("motion_std", 0.0)
    report.motion_cv = motion.get("motion_cv", 0.0)
    if motion["frame_count"] < 2:
        report.failure_reasons.append("Cannot analyze video motion (frame extraction failed)")
        report.recommendations.append("Check the video file; it may be corrupt or a still image")
        report.issues.append("motion_unanalyzable")
    elif report.static_frame_ratio > STATIC_RATIO_LIMIT or report.mean_frame_diff < MIN_MEAN_FRAME_DIFF:
        report.failure_reasons.append(
            f"Static-frame video (定帧图): mean_frame_diff={report.mean_frame_diff:.3f}, "
            f"static_ratio={report.static_frame_ratio:.0%}"
        )
        report.recommendations.append("Increase denoise to the shot's motion profile (0.55-0.65)")
        report.recommendations.append("Increase generated frames (81+ instead of 49)")
        report.recommendations.append("Add Action/Camera/Motion semantics to the prompt; ban 'static image/still frame'")
        report.suggested_denoise = 0.60
        report.suggested_steps = 40
        report.issues.append("static_video")
    elif report.mean_frame_diff < 1.0:
        report.issues.append("low_motion")
        report.recommendations.append("Bump motion level (e.g. 人物动作/镜头运动 profile) for more movement")
        if report.suggested_denoise is None:
            report.suggested_denoise = 0.55
    elif (
        report.mean_frame_diff > FLICKER_MIN_MEAN_DIFF
        and report.motion_cv > FLICKER_MAX_MOTION_CV
    ):
        if not allow_cuts:
            report.failure_reasons.append(
                f"Flicker-like motion curve (闪烁/抖动): mean_frame_diff={report.mean_frame_diff:.1f}, "
                f"motion_cv={report.motion_cv:.2f}"
            )
            report.recommendations.append("Reduce camera shake / urgent motion tokens in the prompt")
            report.recommendations.append("Re-generate with a medium motion profile for stability")
            report.issues.append("flicker_motion_curve")
    if report.motion_score < MIN_MOTION_SCORE and report.motion_score > 0.0:
        report.issues.append("low_motion_flow")

    # Overall score
    report.overall_score = score_sum / len(report.frames) if report.frames else 0

    # Adjust score based on temporal consistency
    if report.temporal_consistency < 0.3:
        report.overall_score *= 0.7
        report.issues.append("flickering")
    elif report.temporal_consistency < 0.5:
        report.overall_score *= 0.85
        report.issues.append("motion_blur")

    # Determine pass/fail with multi-indicator analysis
    mosaic_ratio = mosaic_count / report.total_frames_checked
    dark_ratio = dark_count / report.total_frames_checked
    block_ratio = block_artifact_count / report.total_frames_checked

    mosaic_threshold = 0.4 if strict else 0.6
    block_threshold = 0.5 if strict else 0.6
    score_threshold = 70 if strict else 50

    # Mosaic detection (multi-indicator)
    if mosaic_ratio >= mosaic_threshold:
        report.failure_reasons.append(
            f"Mosaic detected in {mosaic_count}/{report.total_frames_checked} frames "
            f"({mosaic_ratio:.0%}) — multi-indicator score"
        )
        report.recommendations.append("Reduce denoise strength (try 0.40-0.45)")
        report.recommendations.append("Increase steps to 35-40 for better convergence")
        report.suggested_denoise = 0.40
        report.suggested_steps = 35
        report.issues.append("mosaic")

    # Block artifact detection
    if block_ratio >= block_threshold:
        report.failure_reasons.append(
            f"Block artifacts in {block_artifact_count}/{report.total_frames_checked} frames "
            f"({block_ratio:.0%}) — 8x8 boundary analysis"
        )
        report.recommendations.append("Increase resolution to 576x1024 or use super-resolution")
        report.issues.append("block_artifact")

    # GPT v2 severity gate: per-frame block score warning/fail
    max_block = max((fq.block_artifact_score for fq in report.frames), default=0.0)
    if strict and max_block > 0.45:
        report.failure_reasons.append(
            f"Block artifact severity too high (max {max_block:.2f} > 0.45)"
        )
        report.recommendations.append("Apply deblock + hqdn3d post-processing or regenerate at 576x1024")
        report.issues.append("block_artifacts")
    elif max_block > 0.25:
        report.issues.append("block_warning")

    # Subject visibility gate (GPT v1.2): fail <0.60, warning 0.60-0.75
    # Local heuristic calibration: clear references ~0.7+, fog-heavy <0.40
    if strict and report.subject_visibility < 0.40:
        report.failure_reasons.append(
            f"Subject visibility too low ({report.subject_visibility:.2f} < 0.40)"
        )
        report.recommendations.append("Reduce foreground fog/smoke, add clear readable silhouette constraint")
        report.issues.append("subject_visibility_fail")
    elif report.subject_visibility < 0.55:
        report.issues.append("subject_visibility_warning")

    # Dark/bright detection
    if dark_ratio >= 0.5:
        report.failure_reasons.append(
            f"Too dark: {dark_count}/{report.total_frames_checked} frames"
        )
        report.recommendations.append("Add brightness to prompt (well-lit, bright)")
        report.issues.append("too_dark")

    # Temporal consistency
    if report.temporal_consistency < 0.3:
        report.failure_reasons.append(
            f"Poor temporal consistency ({report.temporal_consistency:.2f}) — SSIM"
        )
        report.recommendations.append("Reduce motion intensity in prompt")
        report.suggested_cfg = 2.5  # Lower CFG for more stability

    # Score threshold
    if report.overall_score < score_threshold and not report.failure_reasons:
        report.failure_reasons.append(
            f"Overall quality score too low ({report.overall_score:.1f} < {score_threshold})"
        )
        report.recommendations.append("Re-generate with adjusted parameters")
        report.issues.append("low_quality")

    report.passed = len(report.failure_reasons) == 0

    if report.passed:
        logger.info(
            "Video Quality Gate v2 PASSED: %s (score: %.1f, mosaic: %d/%d, block: %d/%d, "
            "consistency: %.2f, motion: diff=%.3f static=%.0f%% flow=%.3f)",
            video_path.name,
            report.overall_score,
            mosaic_count, report.total_frames_checked,
            block_artifact_count, report.total_frames_checked,
            report.temporal_consistency,
            report.mean_frame_diff,
            report.static_frame_ratio * 100,
            report.motion_score,
        )
    else:
        logger.warning(
            "Video Quality Gate v2 FAILED: %s (%s) issues: %s",
            video_path.name,
            report.verdict,
            ", ".join(report.issues),
        )

    return report
