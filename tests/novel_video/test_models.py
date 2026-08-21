from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.novel_video.models import (
    AspectRatio,
    AssetVersion,
    H3ReferencePackage,
    NovelVideoProject,
    ProductionMode,
    ProductionRun,
    RunCommand,
    RunEvent,
    RunStatus,
    ShotRecord,
    ShotStatus,
    VisualStyle,
)


def test_project_defaults_are_local_h3_and_60_seconds(tmp_path: Path):
    project = NovelVideoProject(id="p1", name="璐嫾", root=tmp_path / "p1")

    assert project.mode is ProductionMode.ONE_CLICK
    assert project.style is VisualStyle.ANIME
    assert project.aspect_ratio is AspectRatio.LANDSCAPE
    assert project.target_duration_seconds == 60
    assert project.primary_video_engine == "minimax_h3_ref2va"
    assert project.allow_wan_fallback is False
    assert project.allow_cloud is False


def _h3_reference_package(**overrides) -> H3ReferencePackage:
    values = {
        "shot_id": "s1",
        "prompt_version": "v1",
        "prompt_text": "test",
        "base_seed": 42,
        "effective_seed": 42,
        "duration_seconds": 5,
        "fps": 24,
        "legal_frame_count": 124,
        "width": 864,
        "height": 480,
        "aspect_ratio": AspectRatio.LANDSCAPE,
        "video_reference_asset_version_ids": [],
        "audio_reference_asset_version_ids": [],
        "workflow_version": "h3-ref2va-v1",
    }
    values.update(overrides)
    return H3ReferencePackage(**values)


def test_h3_reference_package_rejects_illegal_frames():
    with pytest.raises(ValidationError):
        _h3_reference_package(legal_frame_count=120)


def test_h3_reference_package_requires_nearest_legal_frame_count():
    with pytest.raises(ValidationError, match="nearest legal"):
        _h3_reference_package(
            duration_seconds=6,
            legal_frame_count=158,
        )

    package = _h3_reference_package(duration_seconds=6, legal_frame_count=141)

    assert package.legal_frame_count == 141


def test_h3_reference_package_rejects_aspect_orientation_mismatch():
    with pytest.raises(ValidationError, match="aspect ratio"):
        _h3_reference_package(aspect_ratio=AspectRatio.PORTRAIT)


def test_h3_reference_package_rejects_dimensions_outside_multiple():
    with pytest.raises(ValidationError, match="divisible"):
        _h3_reference_package(width=850)


@pytest.mark.parametrize(
    ("field", "value"),
    [("megapixel_profile", 0), ("multiple", 0), ("actual_duration_seconds", 0)],
)
def test_h3_reference_package_rejects_non_positive_profiles(field, value):
    with pytest.raises(ValidationError):
        _h3_reference_package(**{field: value})


def test_h3_reference_package_limits_picture_references_to_three():
    with pytest.raises(ValidationError):
        _h3_reference_package(
            picture_asset_version_ids=["p1", "p2", "p3", "p4"]
        )


def test_h3_reference_package_requires_video_and_audio_reference_lists():
    values = _h3_reference_package().model_dump()
    values.pop("video_reference_asset_version_ids")
    values.pop("audio_reference_asset_version_ids")

    with pytest.raises(ValidationError):
        H3ReferencePackage.model_validate(values)


def test_domain_enums_preserve_the_public_wire_values():
    assert {member.value for member in ProductionMode} == {"one_click", "professional"}
    assert {member.value for member in VisualStyle} == {"anime", "live_action"}
    assert {member.value for member in AspectRatio} == {"16:9", "9:16"}
    assert {member.value for member in RunCommand} == {
        "start",
        "pause",
        "resume",
        "cancel",
        "retry",
    }
    assert {member.value for member in RunStatus} == {
        "draft",
        "planning",
        "awaiting_review",
        "rendering",
        "mixing",
        "validating",
        "paused",
        "interrupted",
        "blocked",
        "cancelled",
        "completed",
    }
    assert {member.value for member in ShotStatus} == {
        "draft",
        "locked",
        "queued",
        "running",
        "validating",
        "approved",
        "included",
        "failed",
        "blocked",
    }


def test_run_shot_asset_and_event_contracts_have_stable_defaults(tmp_path: Path):
    run = ProductionRun(
        id="r1",
        project_id="p1",
        chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
    )
    shot = ShotRecord(id="s1", run_id=run.id, chapter_id="c1", sequence=1)
    asset = AssetVersion(
        id="a1",
        project_id="p1",
        run_id=run.id,
        kind="video",
        path=tmp_path / "video.mp4",
        sha256="a" * 64,
    )
    event = RunEvent(run_id=run.id, event_type="run_created")

    assert run.status is RunStatus.DRAFT
    assert run.settings == {}
    assert shot.status is ShotStatus.DRAFT
    assert shot.plan == {}
    assert shot.reference_package is None
    assert asset.state == "candidate"
    assert asset.parent_id is None
    assert event.payload == {}
    assert run.created_at.tzinfo is not None
    assert shot.created_at.tzinfo is not None
    assert asset.created_at.tzinfo is not None
    assert event.created_at.tzinfo is not None


@pytest.mark.parametrize("sha256", ["A" * 64, "a" * 63])
def test_asset_version_rejects_non_lowercase_64_character_sha256(
    tmp_path: Path, sha256: str
):
    with pytest.raises(ValidationError):
        AssetVersion(
            id="a1",
            project_id="p1",
            run_id="r1",
            kind="video",
            path=tmp_path / "video.mp4",
            sha256=sha256,
        )


def test_asset_version_is_immutable_after_creation(tmp_path: Path):
    asset = AssetVersion(
        id="a1",
        project_id="p1",
        run_id="r1",
        kind="video",
        path=tmp_path / "video.mp4",
        sha256="a" * 64,
    )

    with pytest.raises(ValidationError) as exc_info:
        asset.id = "a2"

    assert exc_info.value.errors()[0]["type"] == "frozen_instance"


def test_asset_metadata_is_deeply_immutable_and_round_trips_deterministically(tmp_path: Path):
    asset = AssetVersion(
        id="a1",
        project_id="p1",
        run_id="r1",
        kind="video",
        path=tmp_path / "video.mp4",
        sha256="a" * 64,
        metadata={
            "nested": {"labels": ["hero", "night"]},
            "tags": {"approved", "master"},
        },
    )

    with pytest.raises(TypeError):
        asset.metadata["new"] = "value"
    with pytest.raises(TypeError):
        asset.metadata["nested"]["labels"][0] = "villain"
    with pytest.raises(AttributeError):
        asset.metadata["tags"].add("mutated")

    encoded = asset.model_dump_json()
    restored = AssetVersion.model_validate_json(encoded)

    assert restored == asset
    assert restored.model_dump_json() == encoded


def _project_with_timestamps(tmp_path: Path, **timestamps: datetime) -> NovelVideoProject:
    return NovelVideoProject(id="p1", name="璐嫾", root=tmp_path / "p1", **timestamps)


def _run_with_timestamps(tmp_path: Path, **timestamps: datetime) -> ProductionRun:
    return ProductionRun(
        id="r1",
        project_id="p1",
        chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
        **timestamps,
    )


def _shot_with_timestamps(tmp_path: Path, **timestamps: datetime) -> ShotRecord:
    return ShotRecord(
        id="s1", run_id="r1", chapter_id="c1", sequence=1, **timestamps
    )


def _asset_with_timestamps(tmp_path: Path, **timestamps: datetime) -> AssetVersion:
    return AssetVersion(
        id="a1",
        project_id="p1",
        run_id="r1",
        kind="video",
        path=tmp_path / "video.mp4",
        sha256="a" * 64,
        **timestamps,
    )


def _event_with_timestamps(tmp_path: Path, **timestamps: datetime) -> RunEvent:
    return RunEvent(run_id="r1", event_type="run_created", **timestamps)


@pytest.mark.parametrize(
    "factory",
    [
        _project_with_timestamps,
        _run_with_timestamps,
        _shot_with_timestamps,
        _asset_with_timestamps,
        _event_with_timestamps,
    ],
)
@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 8, 12, 9, 30),
        datetime(2026, 8, 12, 9, 30, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_models_reject_naive_and_non_utc_created_at(
    tmp_path: Path, factory, timestamp: datetime
):
    with pytest.raises(ValidationError):
        factory(tmp_path, created_at=timestamp)


@pytest.mark.parametrize(
    "factory",
    [_project_with_timestamps, _run_with_timestamps, _shot_with_timestamps],
)
@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 8, 12, 9, 30),
        datetime(2026, 8, 12, 9, 30, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_models_reject_naive_and_non_utc_updated_at(
    tmp_path: Path, factory, timestamp: datetime
):
    with pytest.raises(ValidationError):
        factory(tmp_path, updated_at=timestamp)


@pytest.mark.parametrize(
    "factory",
    [
        _project_with_timestamps,
        _run_with_timestamps,
        _shot_with_timestamps,
        _asset_with_timestamps,
        _event_with_timestamps,
    ],
)
def test_models_accept_explicit_utc_created_at(tmp_path: Path, factory):
    utc_timestamp = datetime(2026, 8, 12, 1, 30, tzinfo=timezone.utc)

    model = factory(tmp_path, created_at=utc_timestamp)

    assert model.created_at == utc_timestamp


@pytest.mark.parametrize(
    "lease_expires_at",
    [
        datetime(2026, 8, 12, 9, 30),
        datetime(2026, 8, 12, 9, 30, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_production_run_rejects_non_utc_lease_expiry(lease_expires_at: datetime):
    with pytest.raises(ValidationError):
        ProductionRun(
            id="r1",
            project_id="p1",
            chapter_indexes=[1],
            mode=ProductionMode.ONE_CLICK,
            lease_id="lease-1",
            lease_expires_at=lease_expires_at,
        )


def test_production_run_accepts_utc_lease_expiry():
    lease_expires_at = datetime(2026, 8, 12, 10, tzinfo=timezone.utc)

    run = ProductionRun(
        id="r1",
        project_id="p1",
        chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
        lease_id="lease-1",
        lease_expires_at=lease_expires_at,
    )

    assert run.lease_expires_at == lease_expires_at
