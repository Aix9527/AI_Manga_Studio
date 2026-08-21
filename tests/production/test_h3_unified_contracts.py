from pathlib import Path

import pytest

from backend.production.h3_unified.contracts import (
    H3AudioRole,
    H3ImageRole,
    H3Mode,
    H3ReferenceBundle,
    H3UnifiedOptions,
    H3VideoRole,
)
from backend.production.h3_unified.reference_bundle import build_reference_bundle


def test_reference_bundle_orders_nine_semantic_image_slots():
    bundle = build_reference_bundle(
        image_roles={
            H3ImageRole.STORYBOARD: "refs/storyboard.png",
            H3ImageRole.CHARACTER_IDENTITY: "refs/hero.png",
            H3ImageRole.LIGHTING: "refs/light.png",
            H3ImageRole.LOCATION: "refs/location.png",
            H3ImageRole.COSTUME: "refs/costume.png",
            H3ImageRole.PROP: "refs/prop.png",
            H3ImageRole.EXPRESSION: "refs/expression.png",
            H3ImageRole.STYLE: "refs/style.png",
            H3ImageRole.SECONDARY_CHARACTER: "refs/rival.png",
        }
    )

    assert [item.role for item in bundle.images] == list(H3ImageRole)
    assert [item.path for item in bundle.images] == [
        "refs/hero.png",
        "refs/rival.png",
        "refs/location.png",
        "refs/costume.png",
        "refs/prop.png",
        "refs/expression.png",
        "refs/style.png",
        "refs/light.png",
        "refs/storyboard.png",
    ]


def test_reference_bundle_deduplicates_paths_by_highest_priority_role():
    bundle = build_reference_bundle(
        image_roles={
            H3ImageRole.CHARACTER_IDENTITY: r"D:\refs\hero.png",
            H3ImageRole.SECONDARY_CHARACTER: "D:/refs/hero.png",
            H3ImageRole.LOCATION: Path("refs/location.png"),
        }
    )

    assert len(bundle.images) == 2
    assert bundle.images[0].role is H3ImageRole.CHARACTER_IDENTITY
    assert bundle.images[0].path == r"D:\refs\hero.png"
    assert bundle.images[1].role is H3ImageRole.LOCATION


def test_reference_bundle_enforces_kind_and_combined_limits():
    with pytest.raises(ValueError, match="at most 3 reference videos"):
        H3ReferenceBundle(
            videos=tuple(
                build_reference_bundle(
                    videos={role: f"refs/video-{index}.mp4" for index, role in enumerate(H3VideoRole)}
                ).videos
            )
            + (build_reference_bundle(videos={H3VideoRole.ACTION_RHYTHM: "refs/extra.mp4"}).videos[0],)
        )

    bundle = build_reference_bundle(
        image_roles={role: f"refs/{role.name}.png" for role in H3ImageRole},
        videos={role: f"refs/{role.name}.mp4" for role in H3VideoRole},
    )
    assert bundle.total_files == 12

    with pytest.raises(ValueError, match="at most 12 reference files"):
        H3ReferenceBundle(
            images=bundle.images,
            videos=bundle.videos,
            audios=(build_reference_bundle(audios={H3AudioRole.PROTAGONIST_VOICE: "refs/voice.wav"}).audios[0],),
        )


def test_unified_options_validate_five_mode_required_inputs():
    empty = H3ReferenceBundle()
    refs = build_reference_bundle(
        image_roles={H3ImageRole.CHARACTER_IDENTITY: "refs/hero.png"}
    )

    H3UnifiedOptions(mode=H3Mode.T2VA).validate_inputs("", "", empty)
    H3UnifiedOptions(mode=H3Mode.I2VA).validate_inputs("first.png", "", empty)
    H3UnifiedOptions(mode=H3Mode.FL2VA).validate_inputs("first.png", "last.png", empty)
    H3UnifiedOptions(mode=H3Mode.L2VA).validate_inputs("", "last.png", empty)
    H3UnifiedOptions(mode=H3Mode.REF2VA).validate_inputs("", "", refs)

    with pytest.raises(ValueError, match="I2VA requires first_frame"):
        H3UnifiedOptions(mode=H3Mode.I2VA).validate_inputs("", "", empty)
    with pytest.raises(ValueError, match="FL2VA requires first_frame and last_frame"):
        H3UnifiedOptions(mode=H3Mode.FL2VA).validate_inputs("first.png", "", empty)
    with pytest.raises(ValueError, match="L2VA requires last_frame"):
        H3UnifiedOptions(mode=H3Mode.L2VA).validate_inputs("", "", empty)
    with pytest.raises(ValueError, match="Ref2VA requires at least one reference"):
        H3UnifiedOptions(mode=H3Mode.REF2VA).validate_inputs("", "", empty)


def test_reference_bundle_to_dict_is_json_safe_and_preserves_roles():
    bundle = build_reference_bundle(
        image_roles={H3ImageRole.CHARACTER_IDENTITY: Path("refs/hero.png")},
        videos={H3VideoRole.CAMERA_EDITING: Path("refs/camera.mp4")},
        audios={H3AudioRole.NARRATOR_VOICE: Path("refs/narrator.wav")},
    )

    payload = bundle.to_dict()

    assert payload == {
        "images": [
            {"kind": "image", "role": "character_identity", "path": "refs/hero.png", "include_audio": False, "duration_seconds": 0.0}
        ],
        "videos": [
            {"kind": "video", "role": "camera_editing", "path": "refs/camera.mp4", "include_audio": False, "duration_seconds": 0.0}
        ],
        "audios": [
            {"kind": "audio", "role": "narrator_voice", "path": "refs/narrator.wav", "include_audio": False, "duration_seconds": 0.0}
        ],
    }
