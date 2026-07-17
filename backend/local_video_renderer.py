"""Small local video renderer used as a deterministic fallback.

The production path should use ComfyUI I2V. When the local ComfyUI install is
missing the required video nodes or models, this module still produces a real
MP4 from first and last frames so the pipeline can hand back a playable file
and a clear warning instead of a fake success.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import imageio.v2 as imageio
from PIL import Image


def _load_rgb(path: str, size: tuple[int, int] | None = None) -> Image.Image:
    image = Image.open(path).convert("RGB")
    if size and image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image


def create_interpolated_video(
    first_frame: str,
    last_frame: str,
    output_path: str,
    duration: float = 3.0,
    fps: int = 24,
) -> str:
    """Create an MP4 by crossfading between first and last frame images."""
    if not os.path.isfile(first_frame):
        raise FileNotFoundError(f"First frame not found: {first_frame}")
    if not os.path.isfile(last_frame):
        raise FileNotFoundError(f"Last frame not found: {last_frame}")

    fps = max(1, int(fps))
    frame_count = max(2, int(max(duration, 0.1) * fps))

    first = _load_rgb(first_frame)
    last = _load_rgb(last_frame, first.size)

    frames: List[object] = []
    for i in range(frame_count):
        alpha = i / (frame_count - 1)
        blended = Image.blend(first, last, alpha)
        frames.append(blended)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(str(output), frames, fps=fps, codec="libx264", quality=8, macro_block_size=16)
    return str(output)
