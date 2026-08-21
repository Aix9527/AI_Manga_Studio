import pytest
from pydantic import ValidationError

from backend.novel_video.h3_frames import derive_shot_seed, legal_h3_frames
from backend.novel_video.models import AspectRatio, H3ReferencePackage


@pytest.mark.parametrize(("seconds", "frames"), [(5, 124), (10, 243), (15, 362)])
def test_legal_h3_frames_selects_nearest_legal_frame_count(seconds, frames):
    assert legal_h3_frames(seconds) == frames
    assert (frames - 5) % 17 == 0


@pytest.mark.parametrize("seconds", [4.9, 15.1])
def test_legal_h3_frames_rejects_duration_outside_h3_range(seconds):
    with pytest.raises(ValueError, match="5-15 seconds"):
        legal_h3_frames(seconds)


def test_legal_h3_frames_rejects_non_h3_fps():
    with pytest.raises(ValueError, match="24 fps"):
        legal_h3_frames(5, fps=30)


def test_derive_shot_seed_is_stable_for_same_project_sequence():
    assert derive_shot_seed(20260812, 3) == derive_shot_seed(20260812, 3)
    assert derive_shot_seed(20260812, 3) == 20260814


def test_reference_package_uses_shared_h3_frame_math():
    values = {
        "shot_id": "s1",
        "prompt_version": "v1",
        "prompt_text": "hero turns toward the doorway",
        "base_seed": 42,
        "effective_seed": 42,
        "duration_seconds": 6,
        "legal_frame_count": 141,
        "width": 864,
        "height": 480,
        "aspect_ratio": AspectRatio.LANDSCAPE,
        "video_reference_asset_version_ids": [],
        "audio_reference_asset_version_ids": [],
        "workflow_version": "h3-ref2va-v1",
    }

    package = H3ReferencePackage(**values)

    assert package.legal_frame_count == legal_h3_frames(6)
    with pytest.raises(ValidationError, match="nearest legal"):
        H3ReferencePackage(**(values | {"legal_frame_count": 124}))
