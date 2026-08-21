import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fastapi import FastAPI

from backend import main
from backend.novel_video.models import (
    AspectRatio, H3ReferencePackage, NovelVideoProject, ProductionMode, ProductionRun, RunStatus, ShotRecord,
    ShotStatus,
)
from backend.novel_video.repository import NovelVideoRepository
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.task_queue import TaskQueue


def _save_run(
    repository: NovelVideoRepository,
    run_id: str,
    status: RunStatus,
    *,
    prompt_id: str | None = None,
    lease_id: str | None = None,
    lease_expires_at: datetime | None = None,
) -> None:
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    repository.save_run(
        ProductionRun(
            id=run_id,
            project_id="project-1",
            chapter_indexes=[1],
            mode=ProductionMode.ONE_CLICK,
            comfy_prompt_id=prompt_id,
            lease_id=lease_id,
            lease_expires_at=lease_expires_at,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    paths = {
        RunStatus.RENDERING: [RunStatus.PLANNING, RunStatus.RENDERING],
        RunStatus.CANCELLED: [RunStatus.CANCELLED],
    }
    for next_status in paths[status]:
        repository.update_run_status(run_id, next_status)


def _seed_repository(tmp_path) -> NovelVideoRepository:
    database_path = tmp_path / "storage" / "orchestrator.db"
    return NovelVideoRepository(OrchestrationDatabase(str(database_path)))


def _disable_worker_threads(monkeypatch):
    lifecycle_calls = []
    monkeypatch.setattr(
        main.OrchestratorWorker, "start", lambda self: lifecycle_calls.append("start")
    )
    monkeypatch.setattr(
        main.OrchestratorWorker, "stop", lambda self: lifecycle_calls.append("stop")
    )
    return lifecycle_calls


def test_lifespan_reconciles_prompt_lease_and_stale_runs_before_worker_start(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    repository = _seed_repository(tmp_path)
    _save_run(
        repository,
        "prompt-live",
        RunStatus.RENDERING,
        prompt_id="prompt-123",
    )
    _save_run(
        repository,
        "lease-live",
        RunStatus.RENDERING,
        lease_id="lease-123",
        lease_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    _save_run(repository, "stale", RunStatus.RENDERING)
    _save_run(
        repository,
        "historical",
        RunStatus.CANCELLED,
        prompt_id="historical-prompt",
    )
    prompt_queries = []

    async def fetch_active_prompts():
        prompt_queries.append("queried")
        return {"prompt-123"}, True

    monkeypatch.setattr(main, "fetch_active_comfy_prompt_ids", fetch_active_prompts)
    lifecycle_calls = _disable_worker_threads(monkeypatch)
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            recovered = app.state.novel_video_repo
            assert recovered.get_run("prompt-live").status is RunStatus.RENDERING
            assert recovered.get_run("lease-live").status is RunStatus.RENDERING
            assert recovered.get_run("stale").status is RunStatus.INTERRUPTED
            assert recovered.get_run("historical").status is RunStatus.CANCELLED
            assert lifecycle_calls == ["start"]

    asyncio.run(exercise_lifespan())

    assert prompt_queries == ["queried"]
    assert lifecycle_calls == ["start", "stop"]


def test_terminal_historical_prompt_does_not_trigger_queue_probe(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    repository = _seed_repository(tmp_path)
    _save_run(
        repository,
        "historical",
        RunStatus.CANCELLED,
        prompt_id="historical-prompt",
    )

    async def fail_if_queried():
        raise AssertionError("terminal historical prompts must not query ComfyUI")

    monkeypatch.setattr(main, "fetch_active_comfy_prompt_ids", fail_if_queried)
    lifecycle_calls = _disable_worker_threads(monkeypatch)
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            assert lifecycle_calls == ["start"]
            assert (
                app.state.novel_video_repo.get_run("historical").status
                is RunStatus.CANCELLED
            )

    asyncio.run(exercise_lifespan())


def test_lifespan_unknown_queue_state_preserves_prompted_run_and_starts_worker(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.chdir(tmp_path)
    repository = _seed_repository(tmp_path)
    _save_run(
        repository,
        "prompt-unknown",
        RunStatus.RENDERING,
        prompt_id="prompt-unknown",
    )

    async def unknown_queue_state():
        return set(), False

    monkeypatch.setattr(main, "fetch_active_comfy_prompt_ids", unknown_queue_state)
    lifecycle_calls = _disable_worker_threads(monkeypatch)
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            assert (
                app.state.novel_video_repo.get_run("prompt-unknown").status
                is RunStatus.RENDERING
            )
            assert lifecycle_calls == ["start"]

    asyncio.run(exercise_lifespan())

    assert "queue state is unknown" in caplog.text


def _formal_package() -> H3ReferencePackage:
    return H3ReferencePackage(
        shot_id="shot-1", prompt_version="v1", prompt_text="move", base_seed=42,
        effective_seed=42, duration_seconds=5, legal_frame_count=124,
        width=1024, height=576, aspect_ratio=AspectRatio.LANDSCAPE,
        video_reference_asset_version_ids=[], audio_reference_asset_version_ids=[],
        workflow_version="h3-ref2va-v1",
    )


def _seed_crashed_formal_task(tmp_path: Path, repository: NovelVideoRepository):
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repository.create_project(project)
    _save_run(repository, "formal-crash", RunStatus.RENDERING)
    repository.save_shot(ShotRecord(id="shot-1", run_id="formal-crash", chapter_id="chapter", sequence=1))
    queue = TaskQueue(root=tmp_path / "storage" / "tasks")
    task = queue.enqueue(
        "video_generation",
        {"formal_novel_video": True, "run_id": "formal-crash", "package": _formal_package().model_dump(mode="json"),
         "picture_paths": [], "output_video": "segment.mp4", "output_tail": "tail.png"},
        project_id=project.id,
    )
    claimed = queue.claim_next("crashed-worker", 1)[0]
    return project, task, claimed


def test_lifespan_adopts_exact_committed_success_before_stale_run_reconciliation(
    tmp_path, monkeypatch
):
    """Restart the real app boundary after DB success but before queue completion."""
    monkeypatch.chdir(tmp_path)
    repository = _seed_repository(tmp_path)
    project, task, claimed = _seed_crashed_formal_task(tmp_path, repository)
    repository.mark_generation_started("formal-crash", "shot-1")
    output_root = tmp_path / "outputs" / "formal"
    output_root.mkdir(parents=True)
    video, tail = output_root / "segment.mp4", output_root / "tail.png"
    video.write_bytes(b"video"); tail.write_bytes(b"tail")
    identity = {
        "task_id": task.task_id, "run_id": "formal-crash", "shot_id": "shot-1",
        "attempt_id": claimed.checkpoint["formal_generation_attempt_id"],
    }
    repository.record_generation_success(
        "formal-crash", shot_id="shot-1", video_path=video, tail_path=tail,
        prompt_id="prompt-success", metadata={}, generation_identity=identity,
    )
    forbidden_calls = []

    def forbidden_factory(**kwargs):
        forbidden_calls.append(kwargs)
        raise AssertionError("committed success must not construct preflight/provider/router")

    monkeypatch.setattr(main, "build_formal_novel_video_router_factory", lambda repo: forbidden_factory)
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            recovered = app.state.novel_video_repo
            assert app.state.task_queue.get(task.task_id).status == "completed"
            assert recovered.get_run("formal-crash").status is RunStatus.RENDERING
            assert recovered.get_shot("shot-1").status is ShotStatus.VALIDATING
            assert [event.event_type for event in recovered.list_events("formal-crash")] == ["video_generation_succeeded"]
            with recovered.database.connect() as connection:
                assert connection.execute(
                    "SELECT COUNT(*) FROM novel_video_assets WHERE run_id = ?", ("formal-crash",)
                ).fetchone()[0] == 2

    asyncio.run(exercise_lifespan())
    assert forbidden_calls == []


def test_lifespan_never_generates_an_uncommitted_task_after_run_is_interrupted(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    repository = _seed_repository(tmp_path)
    _, task, _ = _seed_crashed_formal_task(tmp_path, repository)
    forbidden_calls = []

    def forbidden_factory(**kwargs):
        forbidden_calls.append(kwargs)
        raise AssertionError("interrupted formal run must not reach provider construction")

    monkeypatch.setattr(main, "build_formal_novel_video_router_factory", lambda repo: forbidden_factory)
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            for _ in range(100):
                if app.state.task_queue.get(task.task_id).status == "failed":
                    break
                await asyncio.sleep(0.02)
            assert app.state.task_queue.get(task.task_id).status == "failed"
            assert app.state.novel_video_repo.get_run("formal-crash").status is RunStatus.INTERRUPTED

    asyncio.run(exercise_lifespan())
    assert forbidden_calls == []


def test_lifespan_does_not_preserve_a_run_with_another_uncommitted_recovered_task(
    tmp_path, monkeypatch
):
    """One exact success cannot authorize another crashed shot to generate."""
    monkeypatch.chdir(tmp_path)
    repository = _seed_repository(tmp_path)
    project, committed_task, committed_claim = _seed_crashed_formal_task(tmp_path, repository)
    repository.mark_generation_started("formal-crash", "shot-1")
    output_root = tmp_path / "outputs" / "formal"
    output_root.mkdir(parents=True)
    video, tail = output_root / "segment.mp4", output_root / "tail.png"
    video.write_bytes(b"video"); tail.write_bytes(b"tail")
    repository.record_generation_success(
        "formal-crash", shot_id="shot-1", video_path=video, tail_path=tail,
        prompt_id="prompt-success", metadata={}, generation_identity={
            "task_id": committed_task.task_id, "run_id": "formal-crash", "shot_id": "shot-1",
            "attempt_id": committed_claim.checkpoint["formal_generation_attempt_id"],
        },
    )
    repository.save_shot(ShotRecord(id="shot-2", run_id="formal-crash", chapter_id="chapter", sequence=2))
    queue = TaskQueue(root=tmp_path / "storage" / "tasks")
    second_package = _formal_package().model_copy(update={"shot_id": "shot-2"})
    unresolved = queue.enqueue(
        "video_generation",
        {"formal_novel_video": True, "run_id": "formal-crash", "package": second_package.model_dump(mode="json"),
         "picture_paths": [], "output_video": "segment-2.mp4", "output_tail": "tail-2.png"},
        project_id=project.id,
    )
    queue.claim_next("crashed-worker-2", 1)
    forbidden_calls = []

    def forbidden_factory(**kwargs):
        forbidden_calls.append(kwargs)
        raise AssertionError("an unresolved sibling task must not inherit replay authority")

    monkeypatch.setattr(main, "build_formal_novel_video_router_factory", lambda repo: forbidden_factory)
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            for _ in range(100):
                if app.state.task_queue.get(unresolved.task_id).status == "failed":
                    break
                await asyncio.sleep(0.02)
            assert app.state.task_queue.get(committed_task.task_id).status == "completed"
            assert app.state.task_queue.get(unresolved.task_id).status == "failed"
            assert app.state.novel_video_repo.get_run("formal-crash").status is RunStatus.INTERRUPTED

    asyncio.run(exercise_lifespan())
    assert forbidden_calls == []


def test_lifespan_injects_real_formal_router_factory_and_executes_a_formal_payload(
    tmp_path, monkeypatch
):
    """Catch app startup that leaves formal payloads without the production router dependencies."""
    from backend.novel_video.h3_provider import H3SegmentResult
    from backend.production.comfy_adapter import ComfyArtifact

    monkeypatch.chdir(tmp_path)
    _disable_worker_threads(monkeypatch)
    generated = []
    created = []

    class FakeH3Provider:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created.append(self)

        async def generate(self, request):
            generated.append(request)
            video, tail = tmp_path / "segment.mp4", tmp_path / "tail.png"
            video.write_bytes(b"video"); tail.write_bytes(b"tail")
            return H3SegmentResult("prompt-1", video, tail, True, ComfyArtifact("segment.mp4"), {"media": {}, "sha256": {}})

    monkeypatch.setattr("backend.novel_video.h3_provider.H3Ref2VASegmentProvider", FakeH3Provider)
    monkeypatch.setattr("backend.production.workflow_templates.WorkflowTemplate.load", lambda path: object())
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            repo = app.state.novel_video_repo
            assert app.state.task_runner.novel_video_repository is repo
            assert app.state.task_runner.formal_router_factory is not None
            assert created == []
            project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path, allow_wan_fallback=False)
            repo.create_project(project)
            _save_run(repo, "formal-run", RunStatus.RENDERING)
            repo.save_shot(ShotRecord(id="shot-1", run_id="formal-run", chapter_id="chapter", sequence=1))
            package = H3ReferencePackage(
                shot_id="shot-1", prompt_version="v1", prompt_text="move", base_seed=42,
                effective_seed=42, duration_seconds=5, legal_frame_count=124, width=1024, height=576,
                aspect_ratio=AspectRatio.LANDSCAPE, video_reference_asset_version_ids=[],
                audio_reference_asset_version_ids=[], workflow_version="h3-ref2va-v1",
            )
            task = app.state.task_queue.enqueue(
                "video_generation",
                {"formal_novel_video": True, "run_id": "formal-run", "package": package.model_dump(mode="json"),
                 "picture_paths": ["approved.png"], "output_video": "segment.mp4", "output_tail": "tail.png"},
                project_id=project.id,
            )
            await app.state.task_runner.execute_task(task)
            assert app.state.task_queue.get(task.task_id).status == "completed"
            assert len(generated) == 1
            assert created[0].kwargs["asset_resolver"]("missing") is None

    asyncio.run(exercise_lifespan())


def test_lifespan_formal_execution_fails_closed_when_wan_cannot_publish_formal_lineage(
    tmp_path, monkeypatch
):
    """Formal Wan is disabled until it can atomically publish video/tail lineage."""
    from backend.production.comfy_adapter import ProductionError, ProductionErrorCode
    from backend.production.providers import MediaArtifact, VideoRequest

    monkeypatch.chdir(tmp_path)
    _disable_worker_threads(monkeypatch)
    wan_requests = []

    class FailingH3Provider:
        def __init__(self, **kwargs):
            pass

        async def generate(self, request):
            raise ProductionError(ProductionErrorCode.COMFY_EXECUTION_FAILED, "provider unavailable")

    class FakeWanProvider:
        def __init__(self, **kwargs):
            pass

        async def generate(self, request):
            wan_requests.append(request)
            return MediaArtifact(path=tmp_path / "wan.mp4", kind="video")

    monkeypatch.setattr("backend.novel_video.h3_provider.H3Ref2VASegmentProvider", FailingH3Provider)
    monkeypatch.setattr("backend.production.comfy_video.WanVideoProvider", FakeWanProvider)
    monkeypatch.setattr("backend.production.workflow_templates.WorkflowTemplate.load", lambda path: object())
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            repo = app.state.novel_video_repo
            project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path, allow_wan_fallback=True)
            repo.create_project(project)
            _save_run(repo, "formal-wan", RunStatus.RENDERING)
            repo.save_shot(ShotRecord(id="shot-1", run_id="formal-wan", chapter_id="chapter", sequence=1))
            package = H3ReferencePackage(
                shot_id="shot-1", prompt_version="v1", prompt_text="move", negative_prompt="blur",
                base_seed=42, effective_seed=77, duration_seconds=5, legal_frame_count=124,
                width=1024, height=576, aspect_ratio=AspectRatio.LANDSCAPE,
                video_reference_asset_version_ids=[], audio_reference_asset_version_ids=[],
                workflow_version="h3-ref2va-v1",
            )
            task = app.state.task_queue.enqueue(
                "video_generation",
                {"formal_novel_video": True, "run_id": "formal-wan", "package": package.model_dump(mode="json"),
                 "picture_paths": ["approved.png"], "output_video": "segment.mp4", "output_tail": "tail.png"},
                project_id=project.id,
            )
            with pytest.raises(ProductionError):
                await app.state.task_runner.execute_task(task)

    asyncio.run(exercise_lifespan())

    assert wan_requests == []


def test_lifespan_formal_wan_route_rejects_authoritative_reference_failure(tmp_path, monkeypatch):
    """Catch the app-level formal path allowing Wan to bypass an H3 approval/integrity rejection."""
    from backend.production.comfy_adapter import ProductionError, ProductionErrorCode
    from backend.production.providers import MediaArtifact

    monkeypatch.chdir(tmp_path)
    _disable_worker_threads(monkeypatch)
    wan_calls = []

    class RejectingH3Provider:
        def __init__(self, **kwargs):
            pass

        async def generate(self, request):
            raise ProductionError(ProductionErrorCode.MEDIA_VALIDATION_FAILED, "unapproved reference")

    class FakeWanProvider:
        def __init__(self, **kwargs):
            pass

        async def generate(self, request):
            wan_calls.append(request)
            return MediaArtifact(path=tmp_path / "wan.mp4", kind="video")

    monkeypatch.setattr("backend.novel_video.h3_provider.H3Ref2VASegmentProvider", RejectingH3Provider)
    monkeypatch.setattr("backend.production.comfy_video.WanVideoProvider", FakeWanProvider)
    monkeypatch.setattr("backend.production.workflow_templates.WorkflowTemplate.load", lambda path: object())
    app = FastAPI()

    async def exercise_lifespan():
        async with main.lifespan(app):
            repo = app.state.novel_video_repo
            project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path, allow_wan_fallback=True)
            repo.create_project(project)
            _save_run(repo, "formal-rejected", RunStatus.RENDERING)
            repo.save_shot(ShotRecord(id="shot-1", run_id="formal-rejected", chapter_id="chapter", sequence=1))
            package = H3ReferencePackage(
                shot_id="shot-1", prompt_version="v1", prompt_text="move", base_seed=42,
                effective_seed=42, duration_seconds=5, legal_frame_count=124, width=1024, height=576,
                aspect_ratio=AspectRatio.LANDSCAPE, video_reference_asset_version_ids=[],
                audio_reference_asset_version_ids=[], workflow_version="h3-ref2va-v1",
            )
            task = app.state.task_queue.enqueue(
                "video_generation",
                {"formal_novel_video": True, "run_id": "formal-rejected", "package": package.model_dump(mode="json"),
                 "picture_paths": ["unapproved.png"], "output_video": "segment.mp4", "output_tail": "tail.png"},
                project_id=project.id,
            )
            with pytest.raises(ProductionError) as error:
                await app.state.task_runner.execute_task(task)
            assert error.value.code is ProductionErrorCode.MEDIA_VALIDATION_FAILED

    asyncio.run(exercise_lifespan())
    assert wan_calls == []
