from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from backend.novel_video.models import (
    AspectRatio,
    AssetVersion,
    H3ReferencePackage,
    NovelVideoProject,
    ProductionMode,
    ProductionRun,
    RunEvent,
    RunStatus,
    ShotRecord,
    ShotStatus,
)
from backend.novel_video.repository import NovelVideoRepository
from backend.orchestration.database import OrchestrationDatabase


@pytest.fixture
def repo(tmp_path: Path) -> NovelVideoRepository:
    return NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))


@pytest.fixture
def project(tmp_path: Path) -> NovelVideoProject:
    return NovelVideoProject(
        id="p1",
        name="Novel",
        root=tmp_path / "project",
        created_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


@pytest.fixture
def run() -> ProductionRun:
    return ProductionRun(
        id="r1",
        project_id="p1",
        chapter_indexes=[1, 2],
        mode=ProductionMode.ONE_CLICK,
        created_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


@pytest.fixture
def shot() -> ShotRecord:
    return ShotRecord(
        id="s1",
        run_id="r1",
        chapter_id="c1",
        sequence=1,
        plan={"camera": "close-up"},
        created_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


def asset(
    asset_id: str,
    path: Path,
    *,
    state: str = "candidate",
    parent_id: str | None = None,
    contents: bytes | None = None,
    digest: str | None = None,
) -> AssetVersion:
    if contents is None:
        contents = f"video-{asset_id}".encode("utf-8")
    if not path.exists():
        path.write_bytes(contents)
    return AssetVersion(
        id=asset_id,
        project_id="p1",
        run_id="r1",
        shot_id="s1",
        parent_id=parent_id,
        kind="video",
        state=state,
        path=path,
        sha256=digest or sha256(path.read_bytes()).hexdigest(),
        created_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


def test_run_and_shot_round_trip(repo, project, run, shot):
    repo.create_project(project)
    repo.save_run(run)
    repo.save_shot(shot)

    stored_project = repo.get_project(project.id)
    stored_run = repo.get_run(run.id)
    stored_shot = repo.list_shots(run.id)[0]

    assert stored_project.root == project.root
    assert stored_project.created_at == project.created_at
    assert stored_run.project_id == project.id
    assert stored_run.mode is ProductionMode.ONE_CLICK
    assert stored_run.created_at == run.created_at
    assert stored_shot.id == shot.id
    assert stored_shot.plan == {"camera": "close-up"}


def test_complete_h3_reference_package_round_trips_with_shot(repo, run, shot):
    reference_package = H3ReferencePackage(
        shot_id=shot.id,
        prompt_version="prompt-v3",
        prompt_text="hero crosses the rain-soaked bridge",
        negative_prompt="deformation, duplicate limbs",
        base_seed=20260812,
        effective_seed=20260814,
        duration_seconds=6,
        fps=24,
        legal_frame_count=141,
        width=864,
        height=480,
        aspect_ratio=AspectRatio.LANDSCAPE,
        megapixel_profile=0.4,
        multiple=32,
        picture_asset_version_ids=["picture-v1"],
        video_reference_asset_version_ids=["video-v1", "tail-v2"],
        audio_reference_asset_version_ids=["voice-v4"],
        workflow_version="h3-ref2va-v4",
        model_registry_ids={"video": "minimax-h3-v1"},
        continuity_reason="approved tail-to-head bridge",
        actual_duration_seconds=5.875,
    )
    complete_shot = shot.model_copy(update={"reference_package": reference_package})
    repo.save_run(run)
    repo.save_shot(complete_shot)

    stored = repo.get_shot(complete_shot.id)

    assert stored == complete_shot
    assert stored.reference_package == reference_package


def test_approved_asset_is_never_updated_in_place(repo, project, run, shot, tmp_path):
    repo.create_project(project)
    repo.save_run(run)
    repo.save_shot(shot)

    first = repo.append_asset(asset("a1", tmp_path / "take1.mp4", state="approved"))
    second = repo.append_asset(
        asset("a2", tmp_path / "take2.mp4", parent_id=first.id)
    )

    assert first.id != second.id
    assert repo.get_asset(first.id).state == "approved"
    assert repo.get_asset(second.id).parent_id == first.id
    with pytest.raises(ValueError, match="already exists"):
        repo.append_asset(first)


@pytest.mark.parametrize("contents", [None, b""])
def test_append_asset_rejects_missing_or_empty_file(repo, tmp_path, contents):
    path = tmp_path / "missing-or-empty.mp4"
    if contents is not None:
        path.write_bytes(contents)
    candidate = AssetVersion(
        id="a1",
        project_id="p1",
        run_id="r1",
        kind="video",
        path=path,
        sha256=sha256(b"").hexdigest(),
    )

    with pytest.raises(ValueError, match="missing or empty"):
        repo.append_asset(candidate)


def test_append_asset_rejects_hash_mismatch(repo, tmp_path):
    path = tmp_path / "take.mp4"
    path.write_bytes(b"real-video")
    candidate = asset("a1", path, digest=sha256(b"different-video").hexdigest())

    with pytest.raises(ValueError, match="SHA-256 does not match"):
        repo.append_asset(candidate)


def test_append_asset_rejects_path_registered_by_another_asset(repo, project, run, shot, tmp_path):
    repo.create_project(project)
    repo.save_run(run)
    repo.save_shot(shot)
    path = tmp_path / "take.mp4"
    first = asset("a1", path)
    second = asset("a2", path)
    repo.append_asset(first)

    with pytest.raises(ValueError, match="path .* already registered"):
        repo.append_asset(second)

    assert repo.get_asset(first.id) == first


def test_append_asset_rejects_cross_project_run_or_shot_ownership(repo, project, run, shot, tmp_path):
    repo.create_project(project)
    repo.save_run(run)
    repo.save_shot(shot)
    wrong_project = asset("wrong-project", tmp_path / "wrong-project.mp4")
    wrong_run = asset("wrong-run", tmp_path / "wrong-run.mp4").model_copy(update={"run_id": "missing-run"})
    wrong_shot = asset("wrong-shot", tmp_path / "wrong-shot.mp4").model_copy(update={"shot_id": "missing-shot"})

    with pytest.raises(ValueError, match="project"):
        repo.append_asset(wrong_project.model_copy(update={"project_id": "missing-project"}))
    with pytest.raises(ValueError, match="run"):
        repo.append_asset(wrong_run)
    with pytest.raises(ValueError, match="shot"):
        repo.append_asset(wrong_shot)


def test_status_updates_only_allow_explicit_transitions(repo, project, run, shot):
    repo.create_project(project)
    repo.save_run(run)
    repo.save_shot(shot)

    updated_run = repo.update_run_status(run.id, RunStatus.PLANNING)
    updated_shot = repo.update_shot_status(shot.id, ShotStatus.LOCKED)

    assert updated_run.status is RunStatus.PLANNING
    assert updated_shot.status is ShotStatus.LOCKED
    with pytest.raises(ValueError, match="illegal run status transition"):
        repo.update_run_status(run.id, RunStatus.COMPLETED)
    with pytest.raises(ValueError, match="illegal shot status transition"):
        repo.update_shot_status(shot.id, ShotStatus.APPROVED)


def test_save_run_and_shot_reject_illegal_direct_replacements(repo, run, shot):
    repo.save_run(run)
    repo.save_shot(shot)

    with pytest.raises(ValueError, match="illegal run status transition"):
        repo.save_run(run.model_copy(update={"status": RunStatus.COMPLETED}))
    with pytest.raises(ValueError, match="illegal shot status transition"):
        repo.save_shot(shot.model_copy(update={"status": ShotStatus.APPROVED}))


def test_new_run_and_shot_must_start_in_draft(repo, run, shot):
    with pytest.raises(ValueError, match="new run must start in draft"):
        repo.save_run(run.model_copy(update={"status": RunStatus.RENDERING}))
    with pytest.raises(ValueError, match="new shot must start in draft"):
        repo.save_shot(shot.model_copy(update={"status": ShotStatus.RUNNING}))


class _ZeroRowCursor:
    rowcount = 0


class _StaleCASConnection:
    def __init__(self, connection, database):
        self._connection = connection
        self._database = database

    def execute(self, statement, parameters=()):
        normalized = " ".join(statement.split())
        if (
            self._database.simulate_stale_run_update
            and normalized.startswith("UPDATE novel_video_runs")
            and "AND status" in normalized
        ):
            return _ZeroRowCursor()
        return self._connection.execute(statement, parameters)


class _StaleCASDatabase(OrchestrationDatabase):
    simulate_stale_run_update = False

    @contextmanager
    def transaction(self, *, immediate: bool = False):
        with super().transaction(immediate=immediate) as connection:
            yield _StaleCASConnection(connection, self)


def test_simulated_stale_second_writer_cannot_commit_transition(tmp_path, run):
    database = _StaleCASDatabase(str(tmp_path / "stale-writer.db"))
    repo = NovelVideoRepository(database)
    repo.save_run(run)
    database.simulate_stale_run_update = True

    with pytest.raises(RuntimeError, match="concurrent run transition"):
        repo.save_run(run.model_copy(update={"status": RunStatus.PLANNING}))

    assert repo.get_run(run.id).status is RunStatus.DRAFT


def test_event_round_trip_assigns_database_sequence(repo, project, run):
    repo.create_project(project)
    repo.save_run(run)

    stored = repo.append_event(
        RunEvent(
            run_id=run.id,
            event_type="run_created",
            payload={"source": "novel.txt"},
            created_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        )
    )

    assert stored.sequence == 1
    assert repo.list_events(run.id) == [stored]


def test_lease_and_expiry_round_trip_and_active_lease_query(repo, run):
    now = datetime(2026, 8, 12, 1, tzinfo=timezone.utc)
    expires_at = datetime(2026, 8, 12, 2, tzinfo=timezone.utc)
    leased = run.model_copy(
        update={"lease_id": "lease-live", "lease_expires_at": expires_at}
    )

    repo.save_run(leased)

    assert repo.get_run(leased.id) == leased
    assert repo.active_lease_ids(now) == {"lease-live"}
    assert repo.active_lease_ids(expires_at) == set()
