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
from backend.routes.project import router as project_router
from backend.routes.generation import router as generation_router
from backend.routes.monitor import router as monitor_router
from backend.routes.shot import router as shot_router
from backend.routes.pipeline import router as pipeline_router
from backend.routes.llm import router as llm_router


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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Startup
    logger.info("=" * 60)
    logger.info("  AI Manga Studio Pro V1.0 — Starting...")
    logger.info("=" * 60)

    # Load config
    config = load_config()
    app.state.config = config
    logger.info(f"Config loaded: {config.project.root_path}")

    # Init database
    try:
        init_all_databases()
        logger.info("Databases initialized (5 shards)")
    except Exception as e:
        logger.warning(f"Database init skipped: {e}")

    # Ensure output directories
    for d in [
        PROJECT_ROOT / "output",
        PROJECT_ROOT / "cache",
        PROJECT_ROOT / "project",
        PROJECT_ROOT / "logs",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # Init LLM Service
    try:
        llm = get_llm_service()
        llm_status = await llm.check_status()
        logger.info(
            f"LLM Service: provider={llm_status.provider.value}, "
            f"available={llm_status.available}"
        )
    except Exception as e:
        logger.warning(f"LLM Service init skipped: {e}")

    logger.info("Server ready — http://127.0.0.1:8800")
    yield
    # Shutdown
    await shutdown_llm_service()
    logger.info("Server shutting down...")


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
