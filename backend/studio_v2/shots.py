"""Shot Gallery（Phase 15.3-H / v1.1）：真实产物缩略图 + 元数据.

扫描 outputs/ 下 mp4，用 ffmpeg 提取首帧缩略图（缓存），返回 Shot Wall 数据。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

OUTPUT_DIRS = ["outputs/minimax_h3", "outputs/guixu2"]
THUMB_DIR = Path("storage/shot_thumbs")


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return "ffmpeg"


def _extract_thumb(video: Path, thumb: Path) -> bool:
    if thumb.exists() and thumb.stat().st_size > 0:
        return True
    thumb.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([_ffmpeg(), "-y", "-v", "error", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=160:-2", str(thumb)],
                       capture_output=True, timeout=30)
        return thumb.exists() and thumb.stat().st_size > 0
    except Exception:  # noqa: BLE001
        return False


def list_shots() -> dict:
    """扫描真实产物，返回 shot 列表（缩略图 web 路径）。"""
    shots = []
    for directory in OUTPUT_DIRS:
        root = Path(directory)
        if not root.exists():
            continue
        for video in sorted(root.glob("*.mp4")):
            thumb = THUMB_DIR / f"{video.stem}.png"
            ok = _extract_thumb(video, thumb)
            provider = "MiniMaxH3" if "MMH3" in video.stem or "SPEED" in video.stem or "SHOT" in video.stem or "LONG" in video.stem else "Wan2.2"
            shots.append({
                "id": video.stem,
                "path": str(video),
                "size_bytes": video.stat().st_size,
                "provider": provider,
                "thumb": f"/static/shots/{video.stem}.png" if ok else "",
                "duration_s": "15s" if provider == "MiniMaxH3" else "2s",
            })
    # 元数据（MiniMaxH3 镜头链）
    meta_path = Path("docs/minimax_3shot.json")
    return {"shots": shots, "total": len(shots)}
