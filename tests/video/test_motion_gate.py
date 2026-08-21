"""Motion gate tests — GPT P0: reject 定帧图 (static-frame videos)."""
import subprocess
from pathlib import Path

from backend.video.quality_gate import check_video_quality, compute_motion_metrics


def _ffmpeg() -> str:
    """Prefer imageio-ffmpeg (系统 PATH ffmpeg 缺 lavfi/解码支持)。"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _make_video(path: Path, lavfi_source: str) -> Path:
    cmd = [
        _ffmpeg(), "-y", "-f", "lavfi", "-i", lavfi_source,
        "-t", "2", "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return path


def test_static_video_is_detected_as_static_frame(tmp_path):
    video = _make_video(tmp_path / "static.mp4", "color=c=gray:s=128x128")

    metrics = compute_motion_metrics(video)
    assert metrics["frame_count"] >= 4
    assert metrics["mean_frame_diff"] < 0.3
    assert metrics["static_frame_ratio"] > 0.9

    report = check_video_quality(video)
    assert "static_video" in report.issues
    assert not report.passed
    assert report.static_frame_ratio > 0.4


def test_moving_video_has_real_motion(tmp_path):
    video = _make_video(tmp_path / "moving.mp4", "testsrc=s=128x128")

    metrics = compute_motion_metrics(video)
    assert metrics["frame_count"] >= 4
    assert metrics["mean_frame_diff"] >= 1.0
    assert metrics["static_frame_ratio"] <= 0.4

    report = check_video_quality(video)
    # The motion gate must NOT reject a genuinely moving clip as static
    assert "static_video" not in report.issues
