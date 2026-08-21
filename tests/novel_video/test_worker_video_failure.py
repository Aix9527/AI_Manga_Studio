from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.novel_video.models import (
    AspectRatio, H3ReferencePackage, NovelVideoProject, ProductionMode, ProductionRun,
    RunStatus, ShotRecord, ShotStatus,
)
from backend.novel_video.repository import NovelVideoRepository
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.task_queue import TaskQueue
from backend.orchestration.worker import SSEBroadcaster, TaskRunner
from backend.production.comfy_adapter import ProductionError, ProductionErrorCode


def _paired_result(root: Path, prompt_id: str = "prompt-test"):
    from backend.novel_video.h3_provider import H3SegmentResult
    from backend.production.comfy_adapter import ComfyArtifact
    video, tail = root / f"{prompt_id}.mp4", root / f"{prompt_id}.png"
    video.write_bytes(b"video")
    tail.write_bytes(b"tail")
    return H3SegmentResult(prompt_id, video, tail, True, ComfyArtifact(video.name), {"media": {}, "sha256": {}})


class FailingRouter:
    async def generate(self, request):
        raise ProductionError(ProductionErrorCode.COMFY_OOM, "out of memory")


def _run(repo: NovelVideoRepository, run_id: str = "run-1") -> ProductionRun:
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    run = ProductionRun(
        id=run_id, project_id="project-1", chapter_indexes=[1], mode=ProductionMode.ONE_CLICK,
        created_at=timestamp, updated_at=timestamp,
    )
    repo.save_run(run)
    repo.update_run_status(run.id, RunStatus.PLANNING)
    repo.update_run_status(run.id, RunStatus.RENDERING)
    return repo.get_run(run.id)


def _package() -> H3ReferencePackage:
    return H3ReferencePackage(
        shot_id="shot-1", prompt_version="v1", prompt_text="move forward", base_seed=42,
        effective_seed=42, duration_seconds=5, legal_frame_count=124, width=1024, height=576,
        aspect_ratio=AspectRatio.LANDSCAPE, video_reference_asset_version_ids=[],
        audio_reference_asset_version_ids=[], workflow_version="h3-ref2va-v1",
    )


def _checkpoint(task_id="task-1", attempt_id="task-1:1"):
    package = _package()
    core = {
        "task_id": task_id, "run_id": "run-1", "shot_id": "shot-1", "attempt_id": attempt_id,
        "prompt": package.prompt_text, "negative_prompt": package.negative_prompt,
        "base_seed": package.base_seed, "effective_seed": package.effective_seed,
        "width": package.width, "height": package.height, "fps": package.fps,
        "duration_seconds": package.duration_seconds, "legal_frame_count": package.legal_frame_count,
        "aspect_ratio": package.aspect_ratio.value, "megapixel_profile": package.megapixel_profile,
        "inputs": [], "video_asset_ids": [], "audio_asset_ids": [], "models": {},
        "workflow_version": package.workflow_version, "output_video": "segment.mp4", "output_tail": "tail.png",
    }
    return {**core, "idempotency_hash": sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()}


@pytest.mark.asyncio
async def test_formal_worker_blocks_persists_evidence_and_reraises_video_failure(tmp_path):
    """Catch the formal novel-video worker swallowing a failed generation attempt."""
    from backend.orchestration.worker import FormalNovelVideoWorker

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    run = _run(repo)

    with pytest.raises(ProductionError) as error:
        await FormalNovelVideoWorker(repo, FailingRouter()).generate_segment(run.id, object())

    assert error.value.code is ProductionErrorCode.COMFY_OOM
    assert repo.get_run(run.id).status is RunStatus.BLOCKED
    event = repo.list_events(run.id)[0]
    assert event.event_type == "video_generation_blocked"
    assert event.payload["error_code"] == "COMFY_OOM"


@pytest.mark.asyncio
async def test_formal_worker_persists_router_geometry_with_the_original_oom(tmp_path):
    """Catch durable formal failure evidence that loses the OOM geometry used to block the shot."""
    from backend.novel_video.h3_provider import H3SegmentRequest
    from backend.novel_video.video_router import NovelVideoRouter

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    run = _run(repo)
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter-1", sequence=1,
                              status=ShotStatus.DRAFT, created_at=timestamp, updated_at=timestamp))

    class OomH3:
        async def generate(self, request):
            raise ProductionError(ProductionErrorCode.COMFY_OOM, "out of memory")

    request = H3SegmentRequest(_package(), (), Path("segment.mp4"), Path("tail.png"))
    with pytest.raises(ProductionError):
        await __import__("backend.orchestration.worker", fromlist=["FormalNovelVideoWorker"]).FormalNovelVideoWorker(
            repo, NovelVideoRouter(h3=OomH3(), wan=None)
        ).generate_segment(run.id, request)

    event = repo.list_events(run.id)[0]
    geometry = event.payload["geometry"]
    assert geometry["original_size"] == {"width": 1024, "height": 576}
    assert geometry["downgraded_size"] == {"width": 864, "height": 480}
    assert geometry["actual_area"] <= geometry["target_area"]


def test_block_generation_failure_is_atomic_idempotent_and_owns_the_shot(tmp_path):
    """Catch split status/event writes or a retry that duplicates failure evidence."""
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    run = _run(repo)
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    shot = ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter-1", sequence=1,
                      status=ShotStatus.DRAFT, created_at=timestamp, updated_at=timestamp)
    repo.save_shot(shot)
    evidence = {"failure_key": "shot-1:oom:one", "error_code": "COMFY_OOM",
                "geometry": {"original_size": {"width": 1024, "height": 576}}}

    repo.block_generation_failure(run.id, shot_id=shot.id, evidence=evidence)
    repo.block_generation_failure(run.id, shot_id=shot.id, evidence=evidence)

    assert repo.get_run(run.id).status is RunStatus.BLOCKED
    assert repo.get_shot(shot.id).status is ShotStatus.BLOCKED
    events = repo.list_events(run.id)
    assert len(events) == 1
    assert events[0].payload["failure_key"] == "shot-1:oom:one"


def test_block_generation_failure_is_idempotent_under_concurrent_retries(tmp_path):
    """Catch two concurrent OOM handlers that each append a durable blocked event."""
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    run = _run(repo)
    evidence = {"failure_key": "shot-1:oom:concurrent", "error_code": "COMFY_OOM", "geometry": {}}

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: repo.block_generation_failure(run.id, shot_id=None, evidence=evidence), range(2)))

    assert repo.get_run(run.id).status is RunStatus.BLOCKED
    assert [event.event_type for event in repo.list_events(run.id)] == ["video_generation_blocked"]


@pytest.mark.asyncio
async def test_formal_worker_reraises_generation_error_when_failure_persistence_breaks(tmp_path, caplog):
    """Catch failure-recording outages that replace the original Comfy generation error."""
    from backend.orchestration.worker import FormalNovelVideoWorker

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    run = _run(repo)

    def broken_persistence(*args, **kwargs):
        raise RuntimeError("database unavailable")

    repo.block_generation_failure = broken_persistence
    with pytest.raises(ProductionError) as error:
        await FormalNovelVideoWorker(repo, FailingRouter()).generate_segment(run.id, object())

    assert error.value.code is ProductionErrorCode.COMFY_OOM
    assert "Could not persist formal novel-video failure" in caplog.text


@pytest.mark.asyncio
async def test_task_runner_routes_formal_payload_through_project_permissioned_router(tmp_path):
    """Catch formal payloads being sent through the legacy chain rather than the formal worker."""
    from backend.novel_video.h3_provider import H3SegmentRequest
    from backend.novel_video.video_router import NovelVideoRouter
    from backend.production.providers import MediaArtifact

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path, allow_wan_fallback=True)
    repo.create_project(project)
    run = _run(repo)
    package = _package()
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1,
                              status=ShotStatus.DRAFT, created_at=timestamp, updated_at=timestamp))
    received_permissions: list[bool] = []

    class SuccessfulH3:
        async def generate(self, request):
            return _paired_result(tmp_path)

    def router_factory(*, allow_wan_fallback: bool, project, payload):
        received_permissions.append(allow_wan_fallback)
        return NovelVideoRouter(h3=SuccessfulH3(), wan=None, allow_wan_fallback=allow_wan_fallback)

    queue = TaskQueue(root=tmp_path / "tasks")
    runner = TaskRunner(
        queue, SSEBroadcaster(),
        OrchestrationConfig(database_path=str(tmp_path / "db.sqlite"), project_root=str(tmp_path / "projects")),
        novel_video_repository=repo, formal_router_factory=router_factory,
    )
    task = queue.enqueue(
        "video_generation",
        {
            "formal_novel_video": True, "run_id": run.id,
            "package": package.model_dump(mode="json"), "picture_paths": ["approved-first.png"],
            "output_video": "segment.mp4", "output_tail": "segment-tail.png",
        },
        project_id=project.id,
    )

    await runner.execute_task(task)

    assert received_permissions == [True]
    assert queue.get(task.task_id).status == "completed"


@pytest.mark.asyncio
async def test_task_runner_overrides_factory_fallback_flag_with_project_policy(tmp_path):
    """Catch an injected factory enabling Wan even when this formal project forbids it."""
    from backend.novel_video.video_router import NovelVideoRouter
    from backend.production.providers import MediaArtifact

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path, allow_wan_fallback=False)
    repo.create_project(project)
    run = _run(repo)
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1,
                              status=ShotStatus.DRAFT, created_at=timestamp, updated_at=timestamp))
    captured = []

    class SuccessfulH3:
        async def generate(self, request):
            return _paired_result(tmp_path)

    def router_factory(**kwargs):
        router = NovelVideoRouter(h3=SuccessfulH3(), wan=None, allow_wan_fallback=True)
        captured.append(router)
        return router

    queue = TaskQueue(root=tmp_path / "tasks")
    runner = TaskRunner(
        queue, SSEBroadcaster(),
        OrchestrationConfig(database_path=str(tmp_path / "db.sqlite"), project_root=str(tmp_path / "projects")),
        novel_video_repository=repo, formal_router_factory=router_factory,
    )
    task = queue.enqueue(
        "video_generation",
        {"formal_novel_video": True, "run_id": run.id, "package": _package().model_dump(mode="json"),
         "picture_paths": ["approved-first.png"], "output_video": "segment.mp4", "output_tail": "tail.png"},
        project_id=project.id,
    )

    await runner.execute_task(task)

    assert captured[0].allow_wan_fallback is False


@pytest.mark.asyncio
async def test_formal_resume_uses_persisted_prompt_without_second_submission(tmp_path):
    """A crash after /prompt persists once; the next task waits that id instead of submitting again."""
    from backend.novel_video.video_router import NovelVideoRouter
    from backend.production.providers import MediaArtifact

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    run = _run(repo)
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1,
                              status=ShotStatus.DRAFT, created_at=timestamp, updated_at=timestamp))
    submissions: list[str] = []
    resumes: list[str] = []

    class CheckpointingH3:
        on_prompt_submitted = None
        task_binding = {}

        async def generate(self, request):
            submissions.append("prompt-1")
            checkpoint = _checkpoint(self.task_binding["task_id"], self.task_binding["attempt_id"])
            self.on_prompt_submitted("prompt-1", checkpoint)
            raise KeyboardInterrupt("simulated crash after prompt acceptance")

        async def resume(self, request, prompt_id):
            resumes.append(prompt_id)
            return _paired_result(tmp_path, prompt_id)

    def router_factory(**kwargs):
        return NovelVideoRouter(h3=CheckpointingH3(), wan=None)

    queue = TaskQueue(root=tmp_path / "tasks")
    runner = TaskRunner(queue, SSEBroadcaster(), OrchestrationConfig(database_path=str(tmp_path / "db.sqlite"), project_root=str(tmp_path / "projects")),
                        novel_video_repository=repo, formal_router_factory=router_factory)
    payload = {"formal_novel_video": True, "run_id": run.id, "package": _package().model_dump(mode="json"),
               "picture_paths": ["approved-first.png"], "output_video": "segment.mp4", "output_tail": "tail.png"}
    first = queue.enqueue("video_generation", payload, project_id=project.id)
    with pytest.raises(KeyboardInterrupt):
        await runner.execute_task(first)
    assert repo.get_run(run.id).comfy_prompt_id == "prompt-1"

    # Recovery owns the same durable task identity; creating a different task
    # for an accepted prompt must fail the canonical binding check.
    await runner.execute_task(first)

    assert submissions == ["prompt-1"]
    assert resumes == ["prompt-1"]
    assert queue.get(first.task_id).status == "completed"


def test_restart_recovers_same_running_formal_task_and_shot_scoped_prompt(tmp_path):
    """Queue restart keeps the task id and only its own shot may resume its prompt."""
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    run = _run(repo)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1))
    repo.save_shot(ShotRecord(id="shot-2", run_id=run.id, chapter_id="chapter", sequence=2))
    repo.record_generation_prompt(run.id, shot_id="shot-1", prompt_id="prompt-1", checkpoint=_checkpoint())
    queue = TaskQueue(root=tmp_path / "tasks")
    queued = queue.enqueue("video_generation", {"formal_novel_video": True, "run_id": run.id, "package": _package().model_dump(mode="json")}, project_id=project.id)
    assert queue.claim_next("crashed-worker")[0].status == "running"

    restarted = TaskQueue(root=tmp_path / "tasks")
    recovered = restarted.recover_orphaned_formal_tasks()

    assert [task.task_id for task in recovered] == [queued.task_id]
    assert restarted.claim_next("recovery-worker")[0].task_id == queued.task_id
    assert repo.get_generation_prompt(run.id, "shot-1") == "prompt-1"
    assert repo.get_generation_prompt(run.id, "shot-2") is None


def test_same_prompt_replay_rejects_changed_canonical_binding(tmp_path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    run = _run(repo)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1))
    original = _checkpoint()
    repo.record_generation_prompt(run.id, shot_id="shot-1", prompt_id="prompt-1", checkpoint=original)
    changed = _checkpoint()
    changed["width"] = 832
    core = {key: value for key, value in changed.items() if key != "idempotency_hash"}
    changed["idempotency_hash"] = sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()

    with pytest.raises(Exception, match="binding changed"):
        repo.record_generation_prompt(run.id, shot_id="shot-1", prompt_id="prompt-1", checkpoint=changed)


def test_generation_success_exact_replay_is_one_pair_one_event(tmp_path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    run = _run(repo)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1))
    repo.mark_generation_started(run.id, "shot-1")
    video, tail = tmp_path / "video.mp4", tmp_path / "tail.png"
    video.write_bytes(b"video"); tail.write_bytes(b"tail")

    first = repo.record_generation_success(run.id, shot_id="shot-1", video_path=video, tail_path=tail, prompt_id="prompt-1", metadata={})
    replay = repo.record_generation_success(run.id, shot_id="shot-1", video_path=video, tail_path=tail, prompt_id="prompt-1", metadata={})

    assert [asset.id for asset in replay] == [asset.id for asset in first]
    assert [event.event_type for event in repo.list_events(run.id)] == ["video_generation_succeeded"]
    assert repo.get_shot("shot-1").current_attempt == 1


def test_killed_task_process_recovers_same_task_and_resumes_prompt_once(tmp_path):
    """Exercise the queue, DB checkpoint and OS process boundary together."""
    db_path, queue_root = tmp_path / "novel-video.db", tmp_path / "tasks"
    repo = NovelVideoRepository(OrchestrationDatabase(str(db_path)))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    run = _run(repo)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1))
    queue = TaskQueue(root=queue_root)
    payload = {"formal_novel_video": True, "run_id": run.id, "package": _package().model_dump(mode="json"),
               "picture_paths": [], "output_video": "segment.mp4", "output_tail": "tail.png"}
    queued = queue.enqueue("video_generation", payload, project_id=project.id)
    submit_log = tmp_path / "submits.log"
    script = r'''
import asyncio, json, sys
from hashlib import sha256
from pathlib import Path
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.video_router import NovelVideoRouter
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.task_queue import TaskQueue
from backend.orchestration.worker import TaskRunner, SSEBroadcaster
from backend.orchestration.config import OrchestrationConfig
class H3:
    on_prompt_submitted=None
    task_binding={}
    async def generate(self, request):
        p=request.package
        core={"prompt":p.prompt_text,"negative_prompt":p.negative_prompt,"base_seed":p.base_seed,"effective_seed":p.effective_seed,"width":p.width,"height":p.height,"fps":p.fps,"duration_seconds":p.duration_seconds,"legal_frame_count":p.legal_frame_count,"aspect_ratio":p.aspect_ratio.value,"megapixel_profile":p.megapixel_profile,"inputs":[],"video_asset_ids":[],"audio_asset_ids":[],"models":dict(p.model_registry_ids),"workflow_version":p.workflow_version,"output_video":str(request.output_video),"output_tail":str(request.output_tail),**self.task_binding}
        core["idempotency_hash"]=sha256(json.dumps(core,sort_keys=True).encode()).hexdigest()
        Path(sys.argv[3]).write_text("submit\n",encoding="utf-8")
        self.on_prompt_submitted("prompt-killed",core)
        print("ACCEPTED",flush=True)
        await asyncio.sleep(60)
def factory(**kwargs): return NovelVideoRouter(H3(),None)
async def main():
 q=TaskQueue(root=sys.argv[2]); task=q.claim_next("killed-worker",1)[0]
 repo=NovelVideoRepository(OrchestrationDatabase(sys.argv[1]))
 runner=TaskRunner(q,SSEBroadcaster(),OrchestrationConfig(),workdir=str(Path(sys.argv[2]).parent/"locks"),novel_video_repository=repo,formal_router_factory=factory)
 await runner.execute_task(task)
asyncio.run(main())
'''
    process = subprocess.Popen([sys.executable, "-c", script, str(db_path), str(queue_root), str(submit_log)], cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stdout is not None and process.stdout.readline().strip() == "ACCEPTED"
    process.kill(); process.wait(timeout=10)

    restarted = TaskQueue(root=queue_root)
    assert [task.task_id for task in restarted.recover_orphaned_formal_tasks()] == [queued.task_id]
    claimed = restarted.claim_next("restart-worker", 1)[0]
    resumes = []
    class ResumeH3:
        on_prompt_submitted = None
        task_binding = {}
        async def generate(self, request):
            submit_log.write_text(submit_log.read_text() + "unexpected-submit\n")
            raise AssertionError("recovery submitted a second prompt")
        async def resume(self, request, prompt_id, checkpoint=None):
            resumes.append(prompt_id)
            return _paired_result(tmp_path, prompt_id)
    def resume_factory(**kwargs):
        from backend.novel_video.video_router import NovelVideoRouter
        return NovelVideoRouter(ResumeH3(), None)
    runner = TaskRunner(restarted, SSEBroadcaster(), OrchestrationConfig(), workdir=tmp_path / "locks",
                        novel_video_repository=repo, formal_router_factory=resume_factory)
    import asyncio
    asyncio.run(runner.execute_task(claimed))

    assert submit_log.read_text().splitlines() == ["submit"]
    assert resumes == ["prompt-killed"]
    assert restarted.get(queued.task_id).status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,path",
    [
        (RunStatus.DRAFT, []),
        (RunStatus.PLANNING, [RunStatus.PLANNING]),
        (RunStatus.AWAITING_REVIEW, [RunStatus.PLANNING, RunStatus.AWAITING_REVIEW]),
        (RunStatus.PAUSED, [RunStatus.PLANNING, RunStatus.RENDERING, RunStatus.PAUSED]),
        (RunStatus.INTERRUPTED, [RunStatus.PLANNING, RunStatus.INTERRUPTED]),
        (RunStatus.MIXING, [RunStatus.PLANNING, RunStatus.RENDERING, RunStatus.MIXING]),
        (RunStatus.VALIDATING, [RunStatus.PLANNING, RunStatus.RENDERING, RunStatus.MIXING, RunStatus.VALIDATING]),
    ],
)
async def test_task_runner_rejects_non_rendering_formal_run_before_lock_or_provider(tmp_path, status, path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    repo.save_run(ProductionRun(id="run-1", project_id=project.id, chapter_indexes=[1], mode=ProductionMode.ONE_CLICK,
                                created_at=timestamp, updated_at=timestamp))
    for target in path:
        repo.update_run_status("run-1", target)
    repo.save_shot(ShotRecord(id="shot-1", run_id="run-1", chapter_id="chapter", sequence=1))
    queue = TaskQueue(root=tmp_path / "tasks")
    factory_calls = []

    def forbidden_factory(**kwargs):
        factory_calls.append(kwargs)
        raise AssertionError("provider factory must not run for a non-rendering formal run")

    class ForbiddenLock:
        def acquire(self, key):
            raise AssertionError("locks must not be acquired for a non-rendering formal run")

    runner = TaskRunner(queue, SSEBroadcaster(), OrchestrationConfig(), novel_video_repository=repo,
                        formal_router_factory=forbidden_factory)
    runner.lease_lock = ForbiddenLock()
    task = queue.enqueue(
        "video_generation",
        {"formal_novel_video": True, "run_id": "run-1", "package": _package().model_dump(mode="json"),
         "picture_paths": [], "output_video": "segment.mp4", "output_tail": "tail.png"},
        project_id=project.id,
    )

    with pytest.raises(ValueError, match="rendering"):
        await runner.execute_task(task)

    assert repo.get_run("run-1").status is status
    assert repo.get_shot("shot-1").status is ShotStatus.DRAFT
    assert repo.list_events("run-1") == []
    assert factory_calls == []
    assert queue.get(task.task_id).status != "completed"


def test_process_crash_after_success_writeback_recovers_without_second_generation(tmp_path):
    """DB success followed by process death is queue-completed by exact attempt replay."""
    db_path, queue_root = tmp_path / "novel-video.db", tmp_path / "tasks"
    repo = NovelVideoRepository(OrchestrationDatabase(str(db_path)))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    run = _run(repo)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1))
    queue = TaskQueue(root=queue_root)
    payload = {"formal_novel_video": True, "run_id": run.id, "package": _package().model_dump(mode="json"),
               "picture_paths": [], "output_video": "segment.mp4", "output_tail": "tail.png"}
    queued = queue.enqueue("video_generation", payload, project_id=project.id)
    submit_log, writeback_marker = tmp_path / "submits.log", tmp_path / "writeback.marker"
    script = r'''
import asyncio, os, sys
from pathlib import Path
from backend.novel_video.h3_provider import H3SegmentResult
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.video_router import NovelVideoRouter
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.task_queue import TaskQueue
from backend.orchestration.worker import SSEBroadcaster, TaskRunner
from backend.production.comfy_adapter import ComfyArtifact
class H3:
    on_prompt_submitted=None
    task_binding={}
    async def generate(self, request):
        Path(sys.argv[3]).write_text("submit\n", encoding="utf-8")
        request.output_video.parent.mkdir(parents=True, exist_ok=True)
        request.output_video.write_bytes(b"video")
        request.output_tail.write_bytes(b"tail")
        return H3SegmentResult("prompt-success", request.output_video, request.output_tail, True,
                               ComfyArtifact(request.output_video.name), {"media": {}, "sha256": {}})
def factory(**kwargs): return NovelVideoRouter(H3(), None)
async def main():
    q=TaskQueue(root=sys.argv[2]); task=q.claim_next("crashed-after-db",1)[0]
    repo=NovelVideoRepository(OrchestrationDatabase(sys.argv[1]))
    runner=TaskRunner(q,SSEBroadcaster(),OrchestrationConfig(),workdir=str(Path(sys.argv[2]).parent/"locks"),
                      novel_video_repository=repo,formal_router_factory=factory)
    def die_before_queue_complete(*args, **kwargs):
        Path(sys.argv[4]).write_text("db-success", encoding="utf-8")
        os._exit(73)
    q.complete=die_before_queue_complete
    await runner.execute_task(task)
asyncio.run(main())
'''
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(db_path), str(queue_root), str(submit_log), str(writeback_marker)],
        cwd=Path(__file__).resolve().parents[2],
    )
    process.wait(timeout=20)
    assert process.returncode == 73
    assert writeback_marker.read_text(encoding="utf-8") == "db-success"

    restarted = TaskQueue(root=queue_root)
    assert [task.task_id for task in restarted.recover_orphaned_formal_tasks()] == [queued.task_id]
    claimed = restarted.claim_next("recovery-worker", 1)[0]
    factory_calls = []
    def forbidden_factory(**kwargs):
        factory_calls.append(kwargs)
        raise AssertionError("an already-committed formal attempt must not resubmit")
    runner = TaskRunner(restarted, SSEBroadcaster(), OrchestrationConfig(), workdir=tmp_path / "locks",
                        novel_video_repository=repo, formal_router_factory=forbidden_factory)
    import asyncio
    asyncio.run(runner.execute_task(claimed))

    assert submit_log.read_text(encoding="utf-8").splitlines() == ["submit"]
    assert factory_calls == []
    assert restarted.get(queued.task_id).status == "completed"
    assert repo.get_run(run.id).status is RunStatus.RENDERING
    assert repo.get_shot("shot-1").status is ShotStatus.VALIDATING
    events = repo.list_events(run.id)
    assert [event.event_type for event in events] == ["video_generation_succeeded"]
    with repo.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM novel_video_assets WHERE run_id = ?", (run.id,)).fetchone()[0] == 2


@pytest.mark.asyncio
async def test_formal_worker_rejects_unpaired_media_artifact(tmp_path):
    """Legacy MediaArtifact cannot falsely complete a formal run."""
    from backend.orchestration.worker import FormalNovelVideoWorker
    from backend.production.providers import MediaArtifact

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    run = _run(repo)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1))
    class LegacyRouter:
        async def generate(self, request):
            return MediaArtifact(path=tmp_path / "legacy.mp4", kind="video")
    with pytest.raises(TypeError):
        await FormalNovelVideoWorker(repo, LegacyRouter()).generate_segment(run.id, type("Request", (), {"package": _package()})())
    assert repo.get_run(run.id).status is RunStatus.BLOCKED
    assert repo.get_shot("shot-1").status is ShotStatus.BLOCKED
    assert [event.event_type for event in repo.list_events(run.id)] == ["video_generation_blocked"]


@pytest.mark.asyncio
async def test_formal_worker_missing_paired_file_blocks_atomically_and_does_not_complete(tmp_path):
    from backend.novel_video.h3_provider import H3SegmentResult
    from backend.orchestration.worker import FormalNovelVideoWorker
    from backend.production.comfy_adapter import ComfyArtifact

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    run = _run(repo)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1))
    tail = tmp_path / "tail.png"
    tail.write_bytes(b"tail")

    class MissingVideoRouter:
        async def generate(self, request):
            return H3SegmentResult("prompt-1", tmp_path / "missing.mp4", tail, True, ComfyArtifact("missing.mp4"), {})

    with pytest.raises(ValueError, match="incomplete"):
        await FormalNovelVideoWorker(repo, MissingVideoRouter()).generate_segment(
            run.id, type("Request", (), {"package": _package()})()
        )

    assert repo.get_run(run.id).status is RunStatus.BLOCKED
    assert repo.get_shot("shot-1").status is ShotStatus.BLOCKED
    events = repo.list_events(run.id)
    assert len(events) == 1 and events[0].event_type == "video_generation_blocked"


@pytest.mark.asyncio
async def test_formal_success_records_candidate_video_and_tail_without_auto_approval(tmp_path):
    """Catch a formal success that leaves no lineage or incorrectly exposes its tail as approved."""
    from backend.novel_video.h3_provider import H3SegmentResult
    from backend.orchestration.worker import FormalNovelVideoWorker
    from backend.production.comfy_adapter import ComfyArtifact

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    project = NovelVideoProject(id="project-1", name="Novel", root=tmp_path)
    repo.create_project(project)
    run = _run(repo)
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    repo.save_shot(ShotRecord(id="shot-1", run_id=run.id, chapter_id="chapter", sequence=1,
                              status=ShotStatus.DRAFT, created_at=timestamp, updated_at=timestamp))
    video, tail = tmp_path / "video.mp4", tmp_path / "tail.png"
    video.write_bytes(b"video"); tail.write_bytes(b"tail")

    class SuccessRouter:
        async def generate(self, request):
            return H3SegmentResult("prompt-1", video, tail, True, ComfyArtifact("video.mp4"),
                                   {"media": {"video": {"width": 1024}, "audio": {"codec": "aac"}}, "sha256": {}})

    result = await FormalNovelVideoWorker(repo, SuccessRouter()).generate_segment(run.id, type("Request", (), {"package": _package()})())

    assert result.video_path == video
    events = repo.list_events(run.id)
    assert events[-1].event_type == "video_generation_succeeded"
    video_asset = repo.get_asset(events[-1].payload["video_asset_id"])
    tail_asset = repo.get_asset(events[-1].payload["tail_asset_id"])
    assert (video_asset.state, tail_asset.state) == ("candidate", "candidate")
    assert repo.get_shot("shot-1").approved_tail_asset_id is None
