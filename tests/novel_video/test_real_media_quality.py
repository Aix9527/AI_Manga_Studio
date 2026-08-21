from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.novel_video.h3_provider import H3Ref2VASegmentProvider
from backend.production.comfy_adapter import ProductionError


def _media(path: Path, video_source: str, audio_source: str) -> Path:
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", video_source,
        "-f", "lavfi", "-i", audio_source, "-t", "2.2", "-c:v", "mpeg4",
        "-c:a", "aac", "-shortest", str(path),
    ], check=True, capture_output=True)
    return path


def test_real_moving_audible_media_passes(tmp_path):
    path = _media(tmp_path / "good.mp4", "testsrc2=s=320x192:r=24", "sine=frequency=880:sample_rate=44100")
    evidence = H3Ref2VASegmentProvider._validate_decoded_quality(path)
    assert evidence["black"] is False and evidence["frozen"] is False
    assert evidence["max_volume_db"] > -50


@pytest.mark.parametrize(
    ("name", "video", "audio", "flag"),
    [
        ("black", "color=black:s=320x192:r=24", "sine=frequency=880:sample_rate=44100", "black"),
        ("frozen", "color=red:s=320x192:r=24", "sine=frequency=880:sample_rate=44100", "frozen"),
        ("silent", "testsrc2=s=320x192:r=24", "anullsrc=r=44100:cl=stereo", "silent"),
    ],
)
def test_real_bad_media_fails_its_hard_gate(tmp_path, name, video, audio, flag):
    path = _media(tmp_path / f"{name}.mp4", video, audio)
    with pytest.raises(ProductionError) as error:
        H3Ref2VASegmentProvider._validate_decoded_quality(path)
    if flag == "silent":
        assert error.value.details["max_volume_db"] <= -50
    else:
        assert error.value.details[flag] is True
