from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.novel_video.models import (
    AssetVersion,
    ProductionMode,
    RunCommand,
    RunStatus,
    H3ReferencePackage,
    AspectRatio,
)
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.schemas import ProjectCreateRequest
from backend.novel_video.service import NovelVideoService
from backend.novel_video.storage import AtomicAssetStore
from backend.orchestration.database import OrchestrationDatabase


@pytest.fixture
def service(tmp_path: Path) -> NovelVideoService:
    return NovelVideoService(
        repo=NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel.db"))),
        asset_store=AtomicAssetStore(),
        projects_root=tmp_path / "projects",
    )


@pytest.fixture
def project(service: NovelVideoService):
    return service.create_project(
        ProjectCreateRequest(
            id="p1",
            name="Test novel",
            width=864,
            height=480,
            target_duration_seconds=15,
            max_shots=3,
            base_seed=20260812,
        )
    )


@pytest.fixture
def source_txt(tmp_path: Path) -> Path:
    path = tmp_path / "source.txt"
    path.write_text(
        "第一章 沙漠\n银色机器人走过沙丘。它在夕阳下发现一株绿色植物。"
        "机器人小心靠近，叶片随风摇曳。\n",
        encoding="utf-8",
    )
    return path


def test_import_copies_source_and_records_hash(
    service: NovelVideoService, project, source_txt: Path
):
    result = service.import_source(project.id, source_txt)

    assert result.copied_path.is_file()
    assert result.copied_path != source_txt
    assert result.sha256 == sha256(source_txt.read_bytes()).hexdigest()
    assert result.copied_path.read_bytes() == source_txt.read_bytes()
    assert service.repo.get_project(project.id).source_asset_version_id == result.asset.id


def test_analyze_persists_immutable_chapter_plan(
    service: NovelVideoService, project, source_txt: Path
):
    service.import_source(project.id, source_txt)
    bundle = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)

    restored = service.get_chapter_plan(project.id, chapter_indexes=[1])

    assert restored == bundle
    assert all(shot.source_excerpt in source_txt.read_text(encoding="utf-8") for shot in restored.shots)


def test_professional_run_waits_after_story_assets(
    service: NovelVideoService, project, source_txt: Path
):
    service.import_source(project.id, source_txt)
    bundle = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)
    run = service.create_run(project.id, plan_id=bundle.plan_id, mode=ProductionMode.PROFESSIONAL)

    run = service.advance_until_gate(run.id)

    assert run.status is RunStatus.AWAITING_REVIEW
    assert run.review_gate == "character_scene_bibles"
    assert [shot.sequence for shot in service.repo.list_shots(run.id)] == [1, 2, 3]
    assert service.command(run.id, RunCommand.START).review_gate == "storyboard"
    assert service.command(run.id, RunCommand.START).status is RunStatus.RENDERING


def test_cancel_preserves_approved_assets(
    service: NovelVideoService, project, source_txt: Path
):
    service.import_source(project.id, source_txt)
    bundle = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)
    run = service.create_run(project.id, plan_id=bundle.plan_id)
    candidate_path = project.root / "shots" / "candidate.png"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_bytes(b"approved-tail")
    candidate = service.repo.append_asset(
        AssetVersion(
            id="candidate-tail",
            project_id=project.id,
            run_id=run.id,
            shot_id=service.repo.list_shots(run.id)[0].id,
            kind="tail",
            path=candidate_path,
            sha256=sha256(candidate_path.read_bytes()).hexdigest(),
        )
    )
    service.approve_asset(candidate.id)

    cancelled = service.command(run.id, RunCommand.CANCEL)

    assert cancelled.status is RunStatus.CANCELLED
    assert service.repo.list_assets(run.id, state="approved")


def test_project_schema_rejects_orientation_cloud_and_unsafe_ids():
    with pytest.raises(ValueError, match="orientation"):
        ProjectCreateRequest(id="project-1", name="x", width=480, height=864)
    with pytest.raises(ValueError, match="cloud"):
        ProjectCreateRequest(
            id="project-1", name="x", width=864, height=480,
            allow_cloud=False, cloud_provider="provider",
        )
    with pytest.raises(ValueError, match="safe"):
        ProjectCreateRequest(id="../project", name="x", width=864, height=480)


def test_replayed_source_import_is_concurrent_safe_and_returns_one_asset(
    service: NovelVideoService, project, source_txt: Path
):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _number: service.import_source(project.id, source_txt), range(4)))

    assert {result.asset.id for result in results} == {results[0].asset.id}
    assert len(service.repo.list_assets_for_project(project.id)) == 1


def test_new_source_or_parameters_produce_new_plan_versions_and_old_plan_cannot_run(
    service: NovelVideoService, project, source_txt: Path, tmp_path: Path
):
    service.import_source(project.id, source_txt)
    first = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)
    shorter = service.analyze(project.id, chapter_indexes=[1], target_seconds=10, max_shots=2)
    assert first.plan_id != shorter.plan_id
    assert service.get_chapter_plan(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3) == first
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("第一章 新章\n新的故事内容足够用于测试。", encoding="utf-8")
    service.import_source(project.id, replacement)
    with pytest.raises(ValueError, match="current immutable source"):
        service.create_run(project.id, plan_id=first.plan_id)


def test_approval_is_idempotent_and_rejects_video_as_tail(
    service: NovelVideoService, project, source_txt: Path
):
    service.import_source(project.id, source_txt)
    bundle = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)
    run = service.create_run(project.id, plan_id=bundle.plan_id)
    shot = service.repo.list_shots(run.id)[0]
    video_path = project.root / "shots" / "candidate.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"candidate-video")
    candidate = service.repo.append_asset(AssetVersion(
        id="candidate-video", project_id=project.id, run_id=run.id, shot_id=shot.id,
        kind="video", path=video_path, sha256=sha256(video_path.read_bytes()).hexdigest(),
    ))
    with pytest.raises(ValueError, match="tail"):
        service.approve_asset(candidate.id, approve_tail=True)
    approved = service.approve_asset(candidate.id)
    assert service.approve_asset(candidate.id) == approved
    assert service.repo.get_shot(shot.id).approved_video_asset_id == approved.id


def test_replacement_invalidates_only_cross_run_packages_that_reference_old_asset(
    service: NovelVideoService, project, source_txt: Path
):
    service.import_source(project.id, source_txt)
    bundle = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)
    first_run = service.create_run(project.id, plan_id=bundle.plan_id)
    source_shot = service.repo.list_shots(first_run.id)[0]
    candidate_path = project.root / "shots" / "tail-a.png"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_bytes(b"tail-a")
    first_candidate = service.repo.append_asset(AssetVersion(
        id="tail-a", project_id=project.id, run_id=first_run.id, shot_id=source_shot.id,
        kind="tail", path=candidate_path, sha256=sha256(candidate_path.read_bytes()).hexdigest(),
    ))
    old_tail = service.approve_asset(first_candidate.id)
    second_run = service.create_run(project.id, plan_id=bundle.plan_id)
    dependent, unrelated = service.repo.list_shots(second_run.id)[:2]
    package = H3ReferencePackage(
        shot_id=dependent.id, prompt_version="v1", prompt_text="continue", base_seed=1,
        effective_seed=1, duration_seconds=5, legal_frame_count=124, width=864, height=480,
        aspect_ratio=AspectRatio.LANDSCAPE, picture_asset_version_ids=[old_tail.id],
        video_reference_asset_version_ids=[], audio_reference_asset_version_ids=[],
        workflow_version="workflow", model_registry_ids={},
    )
    service.repo.save_shot(dependent.model_copy(update={"reference_package": package}))
    candidate_b_path = project.root / "shots" / "tail-b.png"
    candidate_b_path.write_bytes(b"tail-b")
    candidate_b = service.repo.append_asset(AssetVersion(
        id="tail-b", project_id=project.id, run_id=first_run.id, shot_id=source_shot.id,
        kind="tail", path=candidate_b_path, sha256=sha256(candidate_b_path.read_bytes()).hexdigest(),
    ))

    service.approve_asset(candidate_b.id)

    assert service.repo.get_shot(dependent.id).reference_package is None
    assert service.repo.get_shot(unrelated.id).reference_package == unrelated.reference_package


def test_approval_database_failure_removes_unregistered_staged_file(
    service: NovelVideoService, project, source_txt: Path, monkeypatch
):
    service.import_source(project.id, source_txt)
    bundle = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)
    run = service.create_run(project.id, plan_id=bundle.plan_id)
    shot = service.repo.list_shots(run.id)[0]
    path = project.root / "shots" / "candidate-failure.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"tail")
    candidate = service.repo.append_asset(AssetVersion(
        id="candidate-failure", project_id=project.id, run_id=run.id, shot_id=shot.id,
        kind="tail", path=path, sha256=sha256(path.read_bytes()).hexdigest(),
    ))
    monkeypatch.setattr(service.repo, "approve_candidate_asset", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database fail")))

    with pytest.raises(RuntimeError, match="database fail"):
        service.approve_asset(candidate.id)

    assert not list((project.root / "shots" / shot.id / "approved").glob("*"))


def test_approval_rejects_candidate_mutated_between_capture_and_transaction(
    service: NovelVideoService, project, source_txt: Path, monkeypatch
):
    service.import_source(project.id, source_txt)
    bundle = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)
    run = service.create_run(project.id, plan_id=bundle.plan_id)
    shot = service.repo.list_shots(run.id)[0]
    path = project.root / "shots" / "candidate-race.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"captured-tail")
    candidate = service.repo.append_asset(AssetVersion(
        id="candidate-race", project_id=project.id, run_id=run.id, shot_id=shot.id,
        kind="tail", path=path, sha256=sha256(path.read_bytes()).hexdigest(),
    ))
    original = service.repo.approve_candidate_asset

    def mutate_before_transaction(*args, **kwargs):
        path.write_bytes(b"mutated-after-capture")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.repo, "approve_candidate_asset", mutate_before_transaction)
    with pytest.raises(ValueError, match="candidate asset file"):
        service.approve_asset(candidate.id)

    assert service.repo.list_assets(run.id, state="approved") == []
    assert service.repo.get_shot(shot.id).approved_tail_asset_id is None


def test_create_run_requires_and_binds_exact_immutable_plan_id(
    service: NovelVideoService, project, source_txt: Path
):
    service.import_source(project.id, source_txt)
    long_plan = service.analyze(project.id, chapter_indexes=[1], target_seconds=15, max_shots=3)
    short_plan = service.analyze(project.id, chapter_indexes=[1], target_seconds=10, max_shots=2)
    with pytest.raises(TypeError):
        service.create_run(project.id, chapter_indexes=[1])

    run = service.create_run(project.id, plan_id=short_plan.plan_id)

    assert run.chapter_indexes == [1]
    assert run.settings["chapter_plan_id"] == short_plan.plan_id
    assert run.settings["chapter_plan_id"] != long_plan.plan_id
