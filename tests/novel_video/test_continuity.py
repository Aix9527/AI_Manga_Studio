from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.novel_video.continuity import ContinuityCompiler, ContinuityError
from backend.novel_video.models import AssetVersion, ShotRecord, ShotStatus


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _plan(**overrides):
    values = {
        "prompt": "The heroine steps through the ruined gate.",
        "negative_prompt": "deformation, duplicated limbs",
        "duration_seconds": 5,
        "width": 864,
        "height": 480,
        "aspect_ratio": "16:9",
        "megapixel_profile": 0.4,
        "multiple": 32,
        "base_seed": 20260812,
        "workflow_version": "h3-ref2va-v1",
        "model_registry_ids": {"video": "minimax-h3"},
        "character_reference_asset_version_ids": ["character-approved-v1"],
        "scene_reference_asset_version_ids": ["scene-approved-v1"],
        "video_reference_asset_version_ids": ["video-reference-v1"],
        "audio_reference_asset_version_ids": ["audio-reference-v1"],
        "inherit_tail": False,
    }
    values.update(overrides)
    return values


def _shot(
    shot_id: str,
    sequence: int,
    *,
    status: ShotStatus = ShotStatus.DRAFT,
    approved_tail_asset_id: str | None = None,
    **plan_overrides,
) -> ShotRecord:
    return ShotRecord(
        id=shot_id,
        run_id="run-1",
        chapter_id="chapter-1",
        sequence=sequence,
        status=status,
        plan=_plan(**plan_overrides),
        approved_tail_asset_id=approved_tail_asset_id,
        created_at=NOW,
        updated_at=NOW,
    )


def _asset(asset_id: str, state: str, tmp_path: Path) -> AssetVersion:
    return AssetVersion(
        id=asset_id,
        project_id="project-1",
        run_id="run-1",
        kind="image",
        state=state,
        path=tmp_path / f"{asset_id}.png",
        sha256="a" * 64,
        created_at=NOW,
    )


def test_compiler_requires_an_explicit_asset_registry():
    with pytest.raises(TypeError, match="asset_versions"):
        ContinuityCompiler()


def test_continuous_shot_uses_approved_tail_as_picture_1(tmp_path):
    compiler = ContinuityCompiler(
        [
            _asset("tail-approved-v1", "approved", tmp_path),
            _asset("character-approved-v1", "approved", tmp_path),
            _asset("scene-approved-v1", "approved", tmp_path),
            _asset("video-reference-v1", "approved", tmp_path),
            _asset("audio-reference-v1", "approved", tmp_path),
        ]
    )
    previous = _shot(
        "s1",
        1,
        status=ShotStatus.APPROVED,
        approved_tail_asset_id="tail-approved-v1",
    )
    current = _shot("s2", 2)

    package = compiler.compile(current, previous, continuity="same_action")

    assert package.picture_asset_version_ids[0] == "tail-approved-v1"
    assert "<Picture 1>" in package.prompt_text
    assert "不要重演" in package.prompt_text
    assert package.effective_seed == 20260813
    assert package.video_reference_asset_version_ids == ["video-reference-v1"]
    assert package.audio_reference_asset_version_ids == ["audio-reference-v1"]


@pytest.mark.parametrize("tail_state", ["unknown", "candidate", "rejected"])
def test_continuous_shot_rejects_an_unverified_previous_tail(tmp_path, tail_state):
    tail_id = f"tail-{tail_state}-v1"
    asset_versions = []
    if tail_state != "unknown":
        asset_versions.append(_asset(tail_id, tail_state, tmp_path))
    compiler = ContinuityCompiler(asset_versions)
    previous = _shot(
        "s1",
        1,
        status=ShotStatus.APPROVED,
        approved_tail_asset_id=tail_id,
    )

    with pytest.raises(ContinuityError, match="approved tail"):
        compiler.compile(_shot("s2", 2), previous, continuity="same_action")


@pytest.mark.parametrize("tail_state", ["unknown", "candidate", "rejected"])
def test_inherited_new_scene_rejects_an_unverified_previous_tail(tmp_path, tail_state):
    tail_id = f"tail-{tail_state}-v1"
    asset_versions = []
    if tail_state != "unknown":
        asset_versions.append(_asset(tail_id, tail_state, tmp_path))
    compiler = ContinuityCompiler(asset_versions)
    previous = _shot(
        "s1",
        1,
        status=ShotStatus.APPROVED,
        approved_tail_asset_id=tail_id,
    )

    with pytest.raises(ContinuityError, match="approved tail"):
        compiler.compile(
            _shot("s2", 2, inherit_tail=True),
            previous,
            continuity="same_character_new_scene",
        )


def test_references_keep_only_known_approved_asset_versions(tmp_path):
    compiler = ContinuityCompiler(
        [
            _asset("character-approved-v1", "approved", tmp_path),
            _asset("scene-approved-v1", "approved", tmp_path),
            _asset("video-reference-v1", "approved", tmp_path),
            _asset("audio-reference-v1", "approved", tmp_path),
            _asset("candidate-v1", "candidate", tmp_path),
            _asset("rejected-v1", "rejected", tmp_path),
        ]
    )
    current = _shot(
        "s2",
        2,
        character_reference_asset_version_ids=[
            "character-approved-v1",
            "unknown-v1",
            "candidate-v1",
            "rejected-v1",
        ],
        scene_reference_asset_version_ids=[
            "scene-approved-v1",
            "unknown-v1",
            "candidate-v1",
            "rejected-v1",
        ],
        video_reference_asset_version_ids=[
            "video-reference-v1",
            "unknown-v1",
            "candidate-v1",
            "rejected-v1",
        ],
        audio_reference_asset_version_ids=[
            "audio-reference-v1",
            "unknown-v1",
            "candidate-v1",
            "rejected-v1",
        ],
    )

    package = compiler.compile(current, None, continuity="location_jump")

    assert package.picture_asset_version_ids == [
        "character-approved-v1",
        "scene-approved-v1",
    ]
    assert package.video_reference_asset_version_ids == ["video-reference-v1"]
    assert package.audio_reference_asset_version_ids == ["audio-reference-v1"]


def test_time_jump_drops_previous_tail(tmp_path):
    compiler = ContinuityCompiler(
        [
            _asset("tail-approved-v1", "approved", tmp_path),
            _asset("character-approved-v1", "approved", tmp_path),
            _asset("scene-approved-v1", "approved", tmp_path),
        ]
    )
    previous = _shot(
        "s1",
        1,
        status=ShotStatus.APPROVED,
        approved_tail_asset_id="tail-approved-v1",
    )

    package = compiler.compile(_shot("s2", 2), previous, continuity="time_jump")

    assert "tail-approved-v1" not in package.picture_asset_version_ids
    assert package.picture_asset_version_ids == [
        "character-approved-v1",
        "scene-approved-v1",
    ]


def test_new_scene_can_inherit_tail_before_deduplicated_references(tmp_path):
    compiler = ContinuityCompiler(
        [
            _asset("tail-approved-v1", "approved", tmp_path),
            _asset("character-approved-v1", "approved", tmp_path),
            _asset("scene-approved-v1", "approved", tmp_path),
            _asset("rejected-v1", "rejected", tmp_path),
        ]
    )
    previous = _shot(
        "s1",
        1,
        status=ShotStatus.APPROVED,
        approved_tail_asset_id="tail-approved-v1",
    )
    current = _shot(
        "s2",
        2,
        inherit_tail=True,
        character_reference_asset_version_ids=["character-approved-v1", "tail-approved-v1"],
        scene_reference_asset_version_ids=["scene-approved-v1", "rejected-v1"],
    )

    package = compiler.compile(current, previous, continuity="same_character_new_scene")

    assert package.picture_asset_version_ids == [
        "tail-approved-v1",
        "character-approved-v1",
        "scene-approved-v1",
    ]


def test_locked_seed_wins_and_a_first_shot_has_no_tail(tmp_path):
    compiler = ContinuityCompiler(
        [
            _asset("character-approved-v1", "approved", tmp_path),
            _asset("scene-approved-v1", "approved", tmp_path),
        ]
    )
    current = _shot("s3", 3, locked_seed=99)

    package = compiler.compile(current, None, continuity="location_jump")

    assert package.effective_seed == 99
    assert package.picture_asset_version_ids == [
        "character-approved-v1",
        "scene-approved-v1",
    ]
