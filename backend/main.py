"""
AI Manga Studio Pro V1.0 — FastAPI Main Entry Point

Integrates all routers: project, generation, monitor, shot.
Also initializes the database, config, middleware, and static file serving.

Run:
    uvicorn backend.main:app --host 127.0.0.1 --port 8800 --reload
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

# Ensure backend package is importable
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import load_config
from backend.db import init_all_databases
from backend.llm_service import get_llm_service, shutdown_llm_service
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository, utcnow
from backend.orchestration.service import JobService
from backend.orchestration.worker import DurableWorker
from backend.production.executor import ProductionStepRunner
from backend.projects.repository import ProjectRepository
from backend.projects.service import ProjectService
from backend.routes.project import router as project_router
from backend.routes.generation import router as generation_router
from backend.routes.monitor import router as monitor_router
from backend.routes.shot import router as shot_router
from backend.routes.pipeline import router as pipeline_router
from backend.routes.llm import router as llm_router
from backend.routes.jobs import router as jobs_router
from backend.runtime.paths import RuntimePaths


# ── Logging Setup ──────────────────────────────────────────

LOG_PATH = PROJECT_ROOT / "logs" / "manga_studio.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    colorize=True,
)
logger.add(
    LOG_PATH,
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    rotation="100 MB",
    retention="30 days",
    encoding="utf-8",
)


# ── Application Lifespan ───────────────────────────────────


def create_job_runtime(
    config,
    runner_factory=ProductionStepRunner,
    runtime_paths: RuntimePaths | None = None,
):
    paths = runtime_paths or RuntimePaths.from_config(config, PROJECT_ROOT)
    paths.ensure()
    database = OrchestrationDatabase(paths.orchestration_database)
    repository = JobRepository(database)
    repository.recover_expired_leases(utcnow())
    repository.reconcile_checkpoints()
    runner = runner_factory(repository=repository)
    worker = DurableWorker(
        repository,
        runner,
        retry_delays=config.orchestration.retry_delays_seconds,
        lease_seconds=config.orchestration.lease_seconds,
        heartbeat_seconds=config.orchestration.heartbeat_seconds,
    )
    return repository, runner, worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    paths = RuntimePaths.from_config(config, PROJECT_ROOT)
    repository, runner, worker = create_job_runtime(
        config, runtime_paths=paths
    )
    app.state.project_service = ProjectService(
        ProjectRepository(repository.database)
    )
    app.state.config = config
    app.state.runtime_paths = paths
    app.state.job_repository = repository
    app.state.job_service = JobService(repository, runner)
    app.state.sse_poll_seconds = config.orchestration.worker_poll_seconds

    try:
        init_all_databases()
    except Exception as error:
        logger.warning(f'Legacy database initialization skipped: {error}')

    worker_thread = Thread(
        target=worker.serve,
        kwargs={'poll_seconds': config.orchestration.worker_poll_seconds},
        daemon=True,
        name='durable-production-worker',
    )
    worker_thread.start()

    try:
        try:
            llm = get_llm_service()
            llm_status = await llm.check_status()
            logger.info(
                f'LLM service: provider={llm_status.provider.value}, '
                f'available={llm_status.available}'
            )
        except Exception as error:
            logger.warning(f'LLM service unavailable: {error}')
        yield
    finally:
        worker.stop()
        worker_thread.join(timeout=5)
        await shutdown_llm_service()


# ── FastAPI Application ────────────────────────────────────

app = FastAPI(
    title="AI Manga Studio Pro",
    description="Local Manga Generation System — Novel to Video, Fully Automated",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── CORS Middleware ────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────

app.include_router(project_router, tags=["Projects"])
app.include_router(generation_router, tags=["Generation"])
app.include_router(monitor_router, tags=["Monitor"])
app.include_router(shot_router, tags=["Shots"])
app.include_router(pipeline_router, tags=["Pipeline"])
app.include_router(llm_router, tags=["LLM Service"])
app.include_router(jobs_router)


# ── Static Files (optional) ────────────────────────────────

output_dir = PROJECT_ROOT / "output"
if output_dir.exists():
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")


# ── Root Health Check ──────────────────────────────────────

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "name": "AI Manga Studio Pro",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    import psutil

    return {
        "status": "healthy",
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "memory_used_pct": psutil.virtual_memory().percent,
        "disk_used_pct": psutil.disk_usage(str(PROJECT_ROOT)).percent,
    }
