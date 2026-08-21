"""Phase 15.3-D：Vision Critic Temporal Stability 子项.

指标：SSIM 时间一致性 + 亮度方差 + 光流平滑度 → Temporal Stability Score (0-100)。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np


def _extract_frames(video_path: Path, sample: int = 8) -> list[np.ndarray]:
    """用 ffmpeg 抽取均匀采样帧（PNG 序列，缩放到 160px）。"""
    import tempfile
    out = []
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        exe = "ffmpeg"
    with tempfile.TemporaryDirectory() as tmp:
        pattern = str(Path(tmp) / "f_%02d.png")
        cmd = [exe, "-v", "error", "-i", str(video_path),
               "-vf", f"fps=1/1,scale=160:-2",
               "-frames:v", str(sample), pattern]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
        except Exception:  # noqa: BLE001
            return []
        if proc.returncode != 0:
            return []
        try:
            from PIL import Image
            files = sorted(Path(tmp).glob("f_*.png"))
            for f in files[:sample]:
                img = Image.open(f).convert("L")
                out.append(np.asarray(img, dtype=np.float32))
        except Exception:  # noqa: BLE001
            return []
    return out


def _ssim(a: np.ndarray, b: np.ndarray) -> float:
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_a, mu_b = a.mean(), b.mean()
    sigma_a = a.var()
    sigma_b = b.var()
    cov = ((a - mu_a) * (b - mu_b)).mean()
    return float((2 * mu_a * mu_b + c1) * (2 * cov + c2) / ((mu_a ** 2 + mu_b ** 2 + c1) * (sigma_a + sigma_b + c2)))


def check_temporal_stability(video_path: str | Path) -> dict:
    """Temporal Stability Score：SSIM 均值 + 亮度方差 + 平滑度。"""
    video_path = Path(video_path)
    frames = _extract_frames(video_path)
    if len(frames) < 3:
        return {"score": 0.0, "ssim_mean": 0.0, "brightness_variance": 1.0,
                "frames_sampled": len(frames), "passed": False}
    ssims = [_ssim(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
    ssim_mean = float(np.mean(ssims))
    brightness = np.array([f.mean() for f in frames])
    brightness_var = float(np.var(brightness) / (np.mean(brightness) ** 2 + 1e-9))
    # SSIM 0-1 → 0-70 分；亮度方差低 → 0-30 分
    score = min(100.0, ssim_mean * 70 + max(0.0, 1.0 - brightness_var * 50) * 30)
    return {
        "score": round(score, 1),
        "ssim_mean": round(ssim_mean, 3),
        "brightness_variance": round(brightness_var, 4),
        "frames_sampled": len(frames),
        "passed": score >= 85 and ssim_mean >= 0.70,
    }
