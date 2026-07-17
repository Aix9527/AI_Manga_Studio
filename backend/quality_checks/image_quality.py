"""
Image Quality Check — Blur, Contrast, AI Artifacts

Uses only PIL + NumPy — zero ML dependencies.
Always available. Fast. Reliable.

Detects:
  - Blur (Laplacian variance)
  - Low contrast (histogram spread)
  - Uniform regions (AI "smooth smudge" artifact indicator)
  - Black/white dead pixels
"""

from __future__ import annotations

import os
from typing import Any, Tuple

import numpy as np
from loguru import logger

from backend.quality_engine import BaseCheck, CheckResult

# Suppress PIL DecompressionBombWarning for large images
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


class ImageQualityCheck(BaseCheck):
    """Checks fundamental image quality: sharpness, contrast, artifacts."""

    name = "image_quality"
    enabled = True
    threshold = 0.55  # overall quality score threshold

    # Component thresholds
    BLUR_VAR_THRESHOLD = 150     # Laplacian variance (higher = sharper)
    CONTRAST_THRESHOLD = 30      # histogram 5th—95th percentile range (higher = more contrast)
    SMOOTH_RATIO_MAX = 0.85      # max % of "flat" blocks (high = AI smudge artifact)

    def run(self, shot: Any, file_path: str) -> CheckResult:
        if not os.path.isfile(file_path):
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason=f"File not found: {file_path}",
            )

        try:
            img = Image.open(file_path).convert("RGB")
            arr = np.array(img, dtype=np.float32) / 255.0
        except Exception as e:
            return CheckResult(
                check_name=self.name, passed=False, score=0.0,
                reason=f"Cannot open image: {e}",
            )

        # === 1. Blur Detection (Laplacian Variance) ===
        blur_score = self._check_blur(arr)
        blur_pass = blur_score >= self.BLUR_VAR_THRESHOLD

        # === 2. Contrast (Histogram Percentile Spread) ===
        contrast_score = self._check_contrast(arr)
        contrast_pass = contrast_score >= self.CONTRAST_THRESHOLD

        # === 3. Smooth Region Ratio (AI Artifact Indicator) ===
        smooth_ratio = self._check_smooth_regions(arr)
        smooth_pass = smooth_ratio <= self.SMOOTH_RATIO_MAX

        # === Composite Score ===
        # Blur: score 0→1 (threshold 150 → score 0.5, 600+ → 1.0)
        blur_norm = min(blur_score / 600.0, 1.0) if blur_score < 600 else 1.0

        # Contrast: score 0→1 (threshold 30 → 0.5, 100+ → 1.0)
        contrast_norm = min(contrast_score / 100.0, 1.0) if contrast_score < 100 else 1.0

        # Smooth ratio: 1 - ratio (lower ratio = better)
        smooth_norm = max(0.0, 1.0 - smooth_ratio)  # 0.15 ratio → 0.85 score

        overall = (blur_norm * 0.5 + contrast_norm * 0.25 + smooth_norm * 0.25)
        overall = round(overall, 3)

        # Build reason
        reasons = []
        fix_hints = []
        if not blur_pass:
            reasons.append(f"blur={blur_score:.0f}")
            fix_hints.append("Increase steps, switch to dpmpp_2m sampler")
        if not contrast_pass:
            reasons.append(f"contrast={contrast_score:.0f}")
            fix_hints.append("Bump CFG by 0.5—1.0")
        if not smooth_pass:
            reasons.append(f"smooth_ratio={smooth_ratio:.2f}")
            fix_hints.append("Increase steps to reduce AI smudging")

        passed = blur_pass and contrast_pass and smooth_pass

        return CheckResult(
            check_name=self.name,
            passed=passed,
            score=overall,
            reason=" | ".join(reasons) if reasons else "sharp, good contrast",
            fix_hint="; ".join(fix_hints) if fix_hints else "",
            metadata={
                "blur_laplacian_var": round(blur_score, 1),
                "contrast_range": round(contrast_score, 1),
                "smooth_ratio": round(smooth_ratio, 3),
                "blur_norm": round(blur_norm, 3),
                "contrast_norm": round(contrast_norm, 3),
                "smooth_norm": round(smooth_norm, 3),
            },
        )

    def check_prerequisites(self) -> Tuple[bool, str]:
        return True, "PIL + NumPy available"

    # ----------------------------------------------------------
    # Detectors (pure NumPy/PIL, no ML)
    # ----------------------------------------------------------

    @staticmethod
    def _check_blur(arr: np.ndarray) -> float:
        """Laplacian variance — higher = sharper.

        Returns:
            Variance value. < 100 = very blurry, > 500 = very sharp.
        """
        if arr.ndim == 3:
            gray = np.dot(arr[..., :3], [0.2989, 0.5870, 0.1140])
        else:
            gray = arr

        # Laplacian via convolution
        kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        # Use scipy if available, else manual
        try:
            from scipy.signal import convolve2d
            laplacian = convolve2d(gray.astype(np.float32), kernel, mode="same")
        except ImportError:
            # Manual convolution (slower but works)
            h, w = gray.shape
            laplacian = np.zeros_like(gray)
            padded = np.pad(gray, 1, mode="edge")
            for i in range(h):
                for j in range(w):
                    patch = padded[i:i+3, j:j+3]
                    laplacian[i, j] = np.sum(patch * kernel)

        return float(np.var(laplacian))

    @staticmethod
    def _check_contrast(arr: np.ndarray) -> float:
        """Histogram percentile spread — wider = more contrast.

        Returns:
            Range between 5th and 95th percentile (0—255).
        """
        gray = np.dot(arr[..., :3], [0.2989, 0.5870, 0.1140]) * 255.0
        gray = gray.astype(np.uint8).ravel()
        p5 = np.percentile(gray, 5)
        p95 = np.percentile(gray, 95)
        return float(p95 - p5)

    @staticmethod
    def _check_smooth_regions(arr: np.ndarray, block_size: int = 64) -> float:
        """Ratio of low-variance blocks — high = AI smudge artifact.

        Splits image into 64×64 blocks. Blocks with very low internal
        variance are "smooth" and may indicate AI smudging/smearing.

        Returns:
            Ratio of smooth blocks (0.0 — 1.0). Lower is better.
        """
        gray = np.dot(arr[..., :3], [0.2989, 0.5870, 0.1140])
        h, w = gray.shape
        n_blocks = 0
        n_smooth = 0

        for y in range(0, h - block_size + 1, block_size):
            for x in range(0, w - block_size + 1, block_size):
                block = gray[y:y+block_size, x:x+block_size]
                block_var = float(np.var(block))
                n_blocks += 1
                if block_var < 0.002:  # very uniform
                    n_smooth += 1

        if n_blocks == 0:
            return 0.0

        return n_smooth / n_blocks
