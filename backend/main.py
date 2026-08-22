from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.service import JobService
from backend.orchestration.task_queue import TaskQueue
from backend.orchestration.worker import OrchestratorWorker, StageExecutor, SSEBroadcaster, TaskRunner
from backend.novel_video.recovery import (
    RECONCILIATION_ACTIVE_STATUSES,
    RunReconciler,
    fetch_active_comfy_prompt_ids,
)
from backend.novel_video.h3_provider import reconcile_emergency_prompt_journals
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.service import NovelVideoService
from backend.novel_video.runner import NovelVideoRunner
from backend.novel_video.provider_factory import build_formal_novel_video_router_factory
from backend.novel_video.routes import NovelVideoIngressLimitMiddleware, ProxyNonceCache
from backend.novel_video.capability import remove_desktop_capability, write_desktop_capability
from backend.migration.scanner import ProjectScanner
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.service import WorkspaceService
from backend.workspace import routes as workspace_router
from backend.routes import jobs as jobs_router
from backend.routes import uploads as uploads_router
from backend.routes import projects as projects_router
from backend.characters import routes as characters_router
from backend.story import routes as story_router
from backend.pipeline import routes as pipeline_router
from backend.routes import vision as vision_router
from backend.routes import creator as creator_router
from backend.routes import history as history_router
from backend.director.evolution import routes as evolution_router
from backend.director import adaptive_routes as adaptive_router_api
from backend.orchestration import adaptive_routes as adaptive_dispatcher_api
from backend.director import arena_runner_routes as arena_runner_api
from backend.director import council_routes as council_api
from backend.governance import routes as governance_api
from backend.story.episode import routes as episode_api
from backend.characters.bible_v2 import routes as character_bible_api
from backend.world import routes as world_api
from backend.shot_dna import routes as shot_dna_api
from backend.agents import intelligence_routes as intelligence_api
from backend.prompt_intelligence import routes as prompt_intelligence_api
from backend.production import readiness_routes as readiness_matrix_api
from backend.feedback import routes as feedback_api
from backend.multi_project import routes as multi_project_api
from backend.prompt_os import routes as prompt_os_api
from backend.production_intelligence import routes as production_intelligence_api
from backend.team import routes as team_api
from backend.knowledge_graph import routes as knowledge_graph_api
from backend.digital_twin import routes as digital_twin_api
from backend.command_center import routes as command_center_api
from backend.producer_agent import routes as producer_agent_api
from backend.production_pilot import routes as production_pilot_api
from backend.prompt_library import routes as prompt_library_api
from backend.production_v1 import routes as production_v1_api
from backend.creative import routes as creative_api
from backend.studio_v2 import routes as v1_phases_api
from backend.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    orchestrator_path = Path("storage/orchestrator.db")
    orchestrator_path.parent.mkdir(parents=True, exist_ok=True)

    db = OrchestrationDatabase(str(orchestrator_path))
    novel_video_repo = NovelVideoRepository(db)
    projects_root = Path("projects")
    novel_video_service = NovelVideoService(
        repo=novel_video_repo,
        projects_root=projects_root,
    )
    # Keep this local capability in process memory; it is never returned by an
    # API, written to project records, or logged.  Desktop callers receive it
    # through their local launcher bridge, while tests may inject a fixed map.
    capability = os.environ.get("AI_MANGA_NOVEL_VIDEO_CAPABILITY") or secrets.token_urlsafe(32)
    proxy_secret = os.environ.get("AI_MANGA_NOVEL_PROXY_SECRET") or secrets.token_urlsafe(48)
    app.state.novel_video_capabilities = {capability: "desktop"}
    app.state.novel_video_sessions = {}
    app.state.novel_video_proxy_secret = proxy_secret
    app.state.novel_video_proxy_nonces = ProxyNonceCache()
    app.state.novel_video_allowed_origins = _local_ui_origins()
    app.state.novel_video_capability_file = write_desktop_capability(
        Path("storage") / "runtime", capability
    )
    from backend.production.comfy_adapter import ComfyUIAdapter
    try:
        await reconcile_emergency_prompt_journals(
            [Path(project.root) for project in novel_video_repo.list_projects()],
            novel_video_repo,
            lambda: ComfyUIAdapter(base_url="http://127.0.0.1:8188"),
        )
    except BaseException:
        novel_video_repo.close()
        remove_desktop_capability(getattr(app.state, "novel_video_capability_file", None))
        raise
    config = OrchestrationConfig()
    repo = JobRepository(db, projects_root=projects_root)
    workspace_repo = WorkspaceRepository(db, projects_root=projects_root)
    project_scanner = ProjectScanner(str(projects_root))
    broadcaster = SSEBroadcaster()
    executor = StageExecutor(repo, broadcaster, config)
    service = JobService(db, repo, broadcaster, config)
    workspace_service = WorkspaceService(
        db, workspace_repo, project_scanner, broadcaster,
        projects_root=projects_root, job_service=service,
    )
    task_queue = TaskQueue(root="storage/tasks")
    task_runner = TaskRunner(
        task_queue, broadcaster, config, workdir="storage/chains",
        novel_video_repository=novel_video_repo,
        formal_router_factory=build_formal_novel_video_router_factory(novel_video_repo),
    )
    # A crash can happen after the atomic DB success but before queue.complete.
    # Adopt those exact authenticated pairs first, while the owning run still
    # has its pre-crash state.  Uncommitted tasks remain queued for the normal
    # interrupted-state gate and can never submit during startup recovery.
    recovered_tasks = task_queue.recover_orphaned_formal_tasks()
    replayed_run_ids: set[str] = set()
    unresolved_run_ids: set[str] = set()
    for recovered_task in recovered_tasks:
        recovered_run_id = str((recovered_task.payload or {}).get("run_id", ""))
        try:
            replayed_run_id = task_runner.recover_committed_formal_success(recovered_task)
            if replayed_run_id:
                replayed_run_ids.add(replayed_run_id)
            elif recovered_run_id:
                unresolved_run_ids.add(recovered_run_id)
        except Exception:
            # Authentication failure is not success.  Leave the task queued;
            # generic reconciliation will interrupt the run and the worker's
            # state gate will fail it closed without provider construction.
            if recovered_run_id:
                unresolved_run_ids.add(recovered_run_id)
    prompted_runs_exist = any(
        run.status in RECONCILIATION_ACTIVE_STATUSES and run.comfy_prompt_id
        for run in novel_video_repo.list_runs()
    )
    if prompted_runs_exist:
        active_prompt_ids, prompt_query_succeeded = await fetch_active_comfy_prompt_ids()
    else:
        active_prompt_ids, prompt_query_succeeded = set(), True
    RunReconciler(
        novel_video_repo,
        active_prompt_ids=active_prompt_ids,
        active_lease_ids=novel_video_repo.active_lease_ids(
            datetime.now(timezone.utc)
        ),
        prompt_query_succeeded=prompt_query_succeeded,
        # Preserve a run only when every recovered task belonging to it was an
        # exact committed success.  One unresolved sibling must still force
        # the run through the interrupted-state fail-closed gate.
        preserved_run_ids=replayed_run_ids - unresolved_run_ids,
    ).reconcile()
    worker = OrchestratorWorker(
        db, repo, executor, broadcaster, config,
        workspace_repo=workspace_repo,
        task_queue=task_queue,
        task_runner=task_runner,
    )
    # The scheduler only enqueues; TaskRunner remains the sole ComfyUI/GPU
    # executor and retains prompt recovery plus global locking authority.
    novel_video_runner = NovelVideoRunner(
        service=novel_video_service,
        task_queue=task_queue,
    )
    novel_video_service.attach_runner(novel_video_runner)

    app.state.orchestration_db = db
    app.state.novel_video_repo = novel_video_repo
    app.state.novel_video_service = novel_video_service
    app.state.config = config
    app.state.repo = repo
    app.state.workspace_repo = workspace_repo
    app.state.project_scanner = project_scanner
    app.state.broadcaster = broadcaster
    app.state.job_service = service
    app.state.workspace_service = workspace_service
    app.state.worker = worker
    app.state.task_queue = task_queue
    app.state.task_runner = task_runner
    app.state.novel_video_runner = novel_video_runner

    try:
        worker.start()
        novel_video_runner.start()
    except BaseException:
        novel_video_repo.close()
        remove_desktop_capability(getattr(app.state, "novel_video_capability_file", None))
        raise
    try:
        yield
    finally:
        await novel_video_runner.stop()
        quiesced = worker.stop()
        if quiesced is False:
            # Closing the shared SQLite repository while TaskRunner still owns
            # an accepted prompt risks a daemon write-after-close. Keep it
            # available for its checkpoint and make shutdown failure explicit.
            remove_desktop_capability(getattr(app.state, "novel_video_capability_file", None))
            raise RuntimeError("formal task worker did not quiesce before repository shutdown")
        novel_video_repo.close()
        remove_desktop_capability(getattr(app.state, "novel_video_capability_file", None))


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Manga Studio v0.8",
        version="0.8.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_local_ui_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID", "X-Novel-Video-Capability"],
    )
    app.add_middleware(NovelVideoIngressLimitMiddleware)

    # Legacy V5 routes
    app.include_router(jobs_router.router)
    app.include_router(uploads_router.router)
    app.include_router(projects_router.router)
    app.include_router(workspace_router.router)

    # v0.5 Phase 1-4 routes
    app.include_router(characters_router.router)
    app.include_router(story_router.router)
    app.include_router(pipeline_router.router)

    # Sprint 7.1: Vision Intelligence Layer
    app.include_router(vision_router.router)

    # AI Creator Studio
    app.include_router(creator_router.router)

    # History Management (clear/reset)
    app.include_router(history_router.router)

    # Phase 12.2 Director Evolution Center
    app.include_router(evolution_router.router)

    # Phase 12.6 Adaptive Director Router
    app.include_router(adaptive_router_api.router)

    # Phase 12.7-A Adaptive Dispatcher
    app.include_router(adaptive_dispatcher_api.router)

    # Phase 12.7-B Real Director Arena Runner
    app.include_router(arena_runner_api.router)

    # Phase 12.8 Director Council
    app.include_router(council_api.router)

    # Phase 12.9-A Production Governance
    app.include_router(governance_api.router)
    app.include_router(episode_api.router)
    app.include_router(character_bible_api.router)
    app.include_router(world_api.router)
    app.include_router(shot_dna_api.router)
    app.include_router(intelligence_api.router)
    app.include_router(prompt_intelligence_api.router)
    app.include_router(readiness_matrix_api.router)
    app.include_router(feedback_api.router)
    app.include_router(multi_project_api.router)

    # Phase 13.6 Prompt OS
    app.include_router(prompt_os_api.router)

    # Phase 13.5-B Production Intelligence
    app.include_router(production_intelligence_api.router)
    app.include_router(team_api.router)
    app.include_router(knowledge_graph_api.router)
    app.include_router(digital_twin_api.router)
    app.include_router(command_center_api.router)
    app.include_router(producer_agent_api.router)
    app.include_router(production_pilot_api.router)
    app.include_router(prompt_library_api.router)
    app.include_router(production_v1_api.router)
    app.include_router(creative_api.router)
    app.include_router(v1_phases_api.router)

    # Production Core API layer (unified domain)
    app.include_router(api_router, prefix="/api/core")

    @app.get("/api/health")
    async def health_check():
        return {
            "status": "ok",
            "version": "0.8.0",
            "phases": {
                "phase_1_character_memory": True,
                "phase_2_story_graph": True,
                "phase_3_director_agent": True,
                "phase_4_prompt_compiler": True,
                "phase_5_vision_critic": True,
                "phase_6_audio_generation": True,
                "phase_7_video_composition": True,
                "phase_8_cli_pipeline": True,
            },
        }

    # Serve frontend static files (if built)
    frontend_dist = Path("frontend/dist")
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        # Mount static assets (JS, CSS, images) at /assets
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # Serve specific static files from dist root
        @app.get("/favicon.svg")
        async def serve_favicon():
            favicon = frontend_dist / "favicon.svg"
            if favicon.exists():
                return FileResponse(str(favicon), media_type="image/svg+xml")
            return {"detail": "not found"}, 404

        # SPA catch-all: serve index.html for all non-API routes
        # This allows React Router to handle client-side routing (e.g., /creator, /overview)
        index_html = frontend_dist / "index.html"

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str, request: Request):
            # Skip API routes — they should have been matched earlier
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            # If the path maps to a real file in dist, serve it
            candidate = frontend_dist / full_path
            if candidate.is_file():
                return FileResponse(str(candidate))
            # Otherwise return index.html for SPA routing
            return FileResponse(str(index_html), media_type="text/html")

    return app


def _local_ui_origins() -> tuple[str, ...]:
    configured = os.environ.get("AI_MANGA_UI_ORIGINS", "")
    if configured:
        return tuple(origin.strip() for origin in configured.split(",") if origin.strip())
    return (
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:64497", "http://127.0.0.1:64497",
    )


app = create_app()

app.mount("/static/shots", StaticFiles(directory="storage/shot_thumbs"), name="shot-thumbs")