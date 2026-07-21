# Unified Production Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the durable startup path and establish one persistent, fail-closed backend foundation for every later local short-drama subsystem.

**Architecture:** FastAPI owns one SQLite-backed `DurableWorker` and one canonical runtime directory map. Legacy project and pipeline endpoints become compatibility facades over persistent services; the canonical CLI submits durable jobs instead of starting historical scripts. The production runner deliberately fails with `PIPELINE_NOT_READY` until the next sub-project installs real local generation adapters.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, SQLite WAL, PyYAML, pytest, Windows PowerShell

## Global Constraints

- All AI inference and media processing are local; this sub-project must not add cloud inference calls.
- Preserve every existing untracked file and historical directory; stage only files named by the current task.
- Treat `D:\LocalMiniDrama-main`, `D:\全自动AI生成视频`, `Z:\AI漫剧生成工具（永久VIP）+项目整合包`, and `Z:\ComfyUI-aki` as read-only references.
- Keep `backend_v3`, `backend_v4`, `backend_v6`, `backend_v7`, `backend_v10`, and `backend_v11` as reference-only directories; do not delete or rewrite them.
- SQLite is the only trusted job/project status source for the new production path.
- No placeholder image, video, or fallback artifact may be reported as successful output.
- The supported target is Windows with an RTX 5070 Ti 16GB; this foundation must remain deterministic without requiring a GPU.
- Use tests first, then the smallest implementation, then focused verification, then a task-scoped commit.

---

**Depends on:**

- `docs/superpowers/specs/2026-07-22-one-click-local-live-action-short-drama-design.md`
- Commits through `4fc448c`, which complete durable-orchestrator Tasks 1–6

**Produces:** A persistent FastAPI foundation with restart recovery, durable compatibility routes, persistent project/source metadata, canonical runtime paths, and a single CLI/API production entry. It does not produce real media; real local generation is the next sub-project.

## Current baseline

- `backend/orchestration/*`, migrations `001`–`004`, `/api/jobs`, commands, leases, checkpoint reconciliation, and SSE snapshots already exist.
- `tests/orchestration` and `tests/api/test_jobs_api.py` are passing in the last recorded 232-test orchestration/API baseline.
- `tests/api/test_lifespan_recovery.py` exists as an untracked RED test and must be preserved.
- `backend/main.py` does not construct the durable runtime or mount `backend.routes.jobs`.
- `backend/routes/pipeline.py` and `backend/routes/project.py` still keep process-memory dictionaries.
- `run.py --novel` still launches root `pipeline.py`; that path must stop being a formal production entry.

## File structure

| Path | Responsibility |
|---|---|
| `backend/runtime/__init__.py` | Runtime package marker |
| `backend/runtime/paths.py` | Canonical application/data paths independent of current working directory |
| `backend/config.py` | Typed local-only runtime and orchestration configuration |
| `config/settings.yaml` | Relative, portable defaults for the formal runtime |
| `backend/production/__init__.py` | Production package marker |
| `backend/production/executor.py` | Fail-closed runner until real adapters are installed |
| `backend/main.py` | One FastAPI lifespan, repository, services, worker thread, and routers |
| `backend/routes/pipeline.py` | Legacy pipeline facade over `JobService`, with no in-memory jobs |
| `backend/orchestration/migrations/005_projects_sources.sql` | Canonical project and source-item metadata |
| `backend/projects/schemas.py` | Project/source request and response contracts |
| `backend/projects/repository.py` | Project/source SQL using the orchestration database |
| `backend/projects/service.py` | Project application commands |
| `backend/routes/project.py` | Persistent project API; delete becomes non-destructive archive |
| `config/entrypoints.yaml` | Machine-readable canonical/compatibility/reference entrypoint policy |
| `run.py` | Canonical CLI that starts FastAPI and submits `/api/jobs` commands |
| `README.md` | Formal entrypoint and foundation status |
| `tests/runtime/test_paths.py` | Runtime path portability tests |
| `tests/api/test_lifespan_recovery.py` | Restart recovery and router wiring tests |
| `tests/api/test_pipeline_compat.py` | Legacy pipeline persistence tests |
| `tests/projects/test_repository.py` | Project/source persistence tests |
| `tests/api/test_projects_api.py` | Persistent project API tests |
| `tests/runtime/test_entrypoint.py` | CLI and entrypoint-policy tests |
| `tests/acceptance/test_foundation_contract.py` | Cross-module foundation acceptance contract |
| `docs/architecture/unified-production-foundation.md` | Implemented foundation boundary and operator commands |

### Task 1: Establish canonical local runtime paths

**Files:**
- Create: `backend/runtime/__init__.py`
- Create: `backend/runtime/paths.py`
- Modify: `backend/config.py`
- Modify: `config/settings.yaml`
- Test: `tests/runtime/test_paths.py`

**Interfaces:**
- Consumes: `backend.config.AppConfig`
- Produces: `RuntimePaths.from_config(config, application_root) -> RuntimePaths`, `RuntimePaths.ensure() -> None`

- [ ] **Step 1: Write failing portability tests**

Create `tests/runtime/test_paths.py`:

```python
from pathlib import Path

from backend.config import AppConfig
from backend.runtime.paths import RuntimePaths


def test_relative_runtime_paths_resolve_from_application_root(tmp_path, monkeypatch):
    application_root = tmp_path / "application"
    application_root.mkdir()
    unrelated_cwd = tmp_path / "elsewhere"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    config = AppConfig(
        runtime={"data_root": "state", "local_only": True},
        orchestration={"database_path": "database/orchestration.db"},
    )

    paths = RuntimePaths.from_config(config, application_root)

    assert paths.data_root == (application_root / "state").resolve()
    assert paths.orchestration_database == (
        application_root / "state" / "database" / "orchestration.db"
    ).resolve()


def test_task_specific_environment_override_changes_only_data_root(
    tmp_path, monkeypatch
):
    override = tmp_path / "portable-data"
    monkeypatch.setenv("AI_MANGA_STUDIO_DATA_ROOT", str(override))
    config = AppConfig(
        runtime={"data_root": "ignored", "local_only": True},
        orchestration={"database_path": "database/jobs.db"},
    )

    paths = RuntimePaths.from_config(config, tmp_path / "application")

    assert paths.data_root == override.resolve()
    assert paths.orchestration_database == (
        override / "database" / "jobs.db"
    ).resolve()


def test_runtime_ensure_creates_only_managed_directories(tmp_path):
    config = AppConfig(
        runtime={"data_root": str(tmp_path), "local_only": True},
        orchestration={"database_path": "database/jobs.db"},
    )
    paths = RuntimePaths.from_config(config, tmp_path / "application")

    paths.ensure()

    assert paths.database_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.projects_dir.is_dir()
    assert paths.output_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.temp_dir.is_dir()
```

- [ ] **Step 2: Run the tests and verify the missing runtime package fails**

Run:

```powershell
python -m pytest tests/runtime/test_paths.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'backend.runtime'`.

- [ ] **Step 3: Implement the runtime path value object**

Create an empty `backend/runtime/__init__.py` and create `backend/runtime/paths.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    application_root: Path
    data_root: Path
    database_dir: Path
    orchestration_database: Path
    logs_dir: Path
    projects_dir: Path
    output_dir: Path
    cache_dir: Path
    temp_dir: Path

    @classmethod
    def from_config(cls, config, application_root: str | Path) -> "RuntimePaths":
        app_root = Path(application_root).resolve()
        configured_root = os.environ.get(
            "AI_MANGA_STUDIO_DATA_ROOT", config.runtime.data_root
        )
        data_root = Path(configured_root)
        if not data_root.is_absolute():
            data_root = app_root / data_root
        data_root = data_root.resolve()

        database_path = Path(config.orchestration.database_path)
        if not database_path.is_absolute():
            database_path = data_root / database_path
        database_path = database_path.resolve()

        return cls(
            application_root=app_root,
            data_root=data_root,
            database_dir=database_path.parent,
            orchestration_database=database_path,
            logs_dir=data_root / "logs",
            projects_dir=data_root / "projects",
            output_dir=data_root / "output",
            cache_dir=data_root / "cache",
            temp_dir=data_root / "temp",
        )

    def ensure(self) -> None:
        for directory in (
            self.database_dir,
            self.logs_dir,
            self.projects_dir,
            self.output_dir,
            self.cache_dir,
            self.temp_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Make the configuration explicitly local and portable**

In `backend/config.py`, add `Literal` to the typing import, add the runtime model, change the orchestration database default, and add `runtime` to `AppConfig`:

```python
from typing import Any, Dict, List, Literal, Optional


class RuntimeConfig(BaseModel):
    data_root: str = "."
    local_only: Literal[True] = True


class OrchestrationConfig(BaseModel):
    database_path: str = Field(
        default="database/orchestration.db",
        min_length=1,
    )
    worker_poll_seconds: float = Field(default=0.5, gt=0)
    lease_seconds: int = Field(default=30, gt=0)
    heartbeat_seconds: int = Field(default=10, gt=0)
    max_retries: int = Field(default=3, ge=0)
    retry_delays_seconds: List[int] = Field(default_factory=lambda: [5, 15, 45])


class AppConfig(BaseModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    # retain every existing field below this line
```

Add these formal defaults near the top of `config/settings.yaml` without removing legacy sections:

```yaml
runtime:
  data_root: "."
  local_only: true

orchestration:
  database_path: "database/orchestration.db"
  worker_poll_seconds: 0.5
  lease_seconds: 30
  heartbeat_seconds: 10
  max_retries: 3
  retry_delays_seconds: [5, 15, 45]
```

- [ ] **Step 5: Run focused configuration and path tests**

Run:

```powershell
python -m pytest tests/runtime/test_paths.py tests/orchestration/test_state_machine.py -q
```

Expected: all tests PASS; changing the process working directory does not change the resolved database location.

- [ ] **Step 6: Commit the runtime boundary**

```powershell
git add backend/runtime/__init__.py backend/runtime/paths.py backend/config.py config/settings.yaml tests/runtime/test_paths.py
git commit -m "feat: define canonical local runtime paths"
```

### Task 2: Wire durable recovery into the FastAPI lifespan

**Files:**
- Create: `backend/production/__init__.py`
- Create: `backend/production/executor.py`
- Modify: `backend/main.py`
- Modify: `tests/api/test_lifespan_recovery.py`

**Interfaces:**
- Consumes: `RuntimePaths`, `JobRepository`, `JobService`, `DurableWorker`
- Produces: `create_job_runtime(config, runner_factory=ProductionStepRunner, runtime_paths=None) -> tuple[JobRepository, StepRunner, DurableWorker]`

- [ ] **Step 1: Preserve and extend the existing RED recovery test**

Replace `tests/api/test_lifespan_recovery.py` with:

```python
from types import SimpleNamespace

from backend.main import app, create_job_runtime
from backend.runtime.paths import RuntimePaths


class IdleRunner:
    def __init__(self, repository):
        self.repository = repository

    def run_next(self, job, cancel_requested):
        return None

    def cancel(self, job_id):
        return False


def runtime_config(database_path):
    return SimpleNamespace(
        orchestration=SimpleNamespace(
            database_path=str(database_path),
            retry_delays_seconds=[0, 0, 0],
            lease_seconds=30,
            heartbeat_seconds=10,
            worker_poll_seconds=0.01,
        )
    )


def test_runtime_recovers_expired_running_job(job_repo, running_job, tmp_path):
    config = runtime_config(job_repo.database.path)
    paths = RuntimePaths(
        application_root=tmp_path,
        data_root=tmp_path,
        database_dir=job_repo.database.path.parent,
        orchestration_database=job_repo.database.path,
        logs_dir=tmp_path / "logs",
        projects_dir=tmp_path / "projects",
        output_dir=tmp_path / "output",
        cache_dir=tmp_path / "cache",
        temp_dir=tmp_path / "temp",
    )

    repository, _, _ = create_job_runtime(
        config, runner_factory=IdleRunner, runtime_paths=paths
    )

    restored = repository.get_job(running_job["id"])
    assert restored["status"] == "queued"
    assert restored["steps"][0]["status"] == "completed"
    assert restored["steps"][1]["status"] == "queued"


def test_formal_app_mounts_the_durable_jobs_router_once():
    paths = [route.path for route in app.routes]
    assert paths.count("/api/jobs") == 2  # POST create and GET list
    assert paths.count("/api/jobs/current") == 1
```

- [ ] **Step 2: Run the recovery test and verify the missing factory fails**

Run:

```powershell
python -m pytest tests/api/test_lifespan_recovery.py -q
```

Expected: FAIL because `create_job_runtime` does not exist and the jobs router is not mounted.

- [ ] **Step 3: Add a fail-closed production runner**

Create an empty `backend/production/__init__.py` and create `backend/production/executor.py`:

```python
from __future__ import annotations

from backend.orchestration.worker import StepExecutionError


class ProductionStepRunner:
    """Explicit boundary until sub-project 2/3 install real local adapters."""

    def __init__(self, repository):
        self.repository = repository

    def run_next(self, job, cancel_requested):
        if cancel_requested():
            raise StepExecutionError("USER_CANCELLED", "任务已取消")
        raise StepExecutionError(
            "PIPELINE_NOT_READY",
            "本地生产执行器尚未安装；任务已安全停止且未生成占位产物",
        )

    def cancel(self, job_id: str) -> bool:
        return False
```

- [ ] **Step 4: Construct and recover the durable runtime before serving requests**

In `backend/main.py`, add these imports and factory above `lifespan`:

```python
from threading import Thread

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository, utcnow
from backend.orchestration.service import JobService
from backend.orchestration.worker import DurableWorker
from backend.production.executor import ProductionStepRunner
from backend.routes.jobs import router as jobs_router
from backend.runtime.paths import RuntimePaths


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
```

Replace the existing `lifespan` body with a single startup/shutdown owner while retaining the legacy database and LLM health checks:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    paths = RuntimePaths.from_config(config, PROJECT_ROOT)
    repository, runner, worker = create_job_runtime(
        config, runtime_paths=paths
    )
    app.state.config = config
    app.state.runtime_paths = paths
    app.state.job_repository = repository
    app.state.job_service = JobService(repository, runner)
    app.state.sse_poll_seconds = config.orchestration.worker_poll_seconds

    try:
        init_all_databases()
    except Exception as error:
        logger.warning(f"Legacy database initialization skipped: {error}")

    worker_thread = Thread(
        target=worker.serve,
        kwargs={"poll_seconds": config.orchestration.worker_poll_seconds},
        daemon=True,
        name="durable-production-worker",
    )
    worker_thread.start()

    try:
        try:
            llm = get_llm_service()
            llm_status = await llm.check_status()
            logger.info(
                f"LLM service: provider={llm_status.provider.value}, "
                f"available={llm_status.available}"
            )
        except Exception as error:
            logger.warning(f"LLM service unavailable: {error}")
        yield
    finally:
        worker.stop()
        worker_thread.join(timeout=5)
        await shutdown_llm_service()
```

Mount the durable router exactly once with the other formal routers:

```python
app.include_router(jobs_router)
```

- [ ] **Step 5: Run durable runtime and API regression tests**

Run:

```powershell
python -m pytest tests/api/test_lifespan_recovery.py tests/api/test_jobs_api.py tests/orchestration -q
```

Expected: all tests PASS; completed checkpoints stay completed and the expired running step returns to `queued`.

- [ ] **Step 6: Commit lifespan integration**

```powershell
git add backend/production/__init__.py backend/production/executor.py backend/main.py tests/api/test_lifespan_recovery.py
git commit -m "feat: restore durable runtime on application startup"
```

### Task 3: Replace the in-memory pipeline route with a durable compatibility facade

**Files:**
- Modify: `backend/routes/pipeline.py`
- Create: `tests/api/test_pipeline_compat.py`

**Interfaces:**
- Consumes: `request.app.state.job_service`, `JobCreate`
- Produces: legacy `/api/pipeline/run`, `/upload`, `/status/{job_id}`, `/jobs/{job_id}` responses backed by `JobRepository`

- [ ] **Step 1: Write failing compatibility tests**

Create `tests/api/test_pipeline_compat.py`:

```python
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.service import JobService
from backend.routes import pipeline


def make_client(database_path):
    app = FastAPI()
    repository = JobRepository(OrchestrationDatabase(database_path))
    app.state.job_service = JobService(
        repository, SimpleNamespace(cancel=lambda _job_id: True)
    )
    app.include_router(pipeline.router)
    return TestClient(app), repository


def test_legacy_run_creates_a_durable_job(tmp_path):
    novel = tmp_path / "story.txt"
    novel.write_text("测试故事", encoding="utf-8")
    client, repository = make_client(tmp_path / "jobs.db")

    response = client.post(
        "/api/pipeline/run",
        headers={"Idempotency-Key": "legacy-run-0001"},
        json={"novel_path": str(novel), "style": "realistic"},
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    assert repository.get_job(job_id)["status"] == "queued"
    assert not hasattr(pipeline, "_jobs")


def test_legacy_status_survives_a_new_app_instance(tmp_path):
    novel = tmp_path / "story.txt"
    novel.write_text("测试故事", encoding="utf-8")
    database = tmp_path / "jobs.db"
    first, _ = make_client(database)
    job_id = first.post(
        "/api/pipeline/run",
        headers={"Idempotency-Key": "legacy-run-0002"},
        json={"novel_path": str(novel)},
    ).json()["job_id"]

    second, _ = make_client(database)
    restored = second.get(f"/api/pipeline/status/{job_id}")

    assert restored.status_code == 200
    assert restored.json()["job_id"] == job_id


def test_legacy_cancel_uses_the_durable_command(tmp_path):
    novel = tmp_path / "story.txt"
    novel.write_text("测试故事", encoding="utf-8")
    client, repository = make_client(tmp_path / "jobs.db")
    job_id = client.post(
        "/api/pipeline/run",
        headers={"Idempotency-Key": "legacy-run-0003"},
        json={"novel_path": str(novel)},
    ).json()["job_id"]

    response = client.delete(
        f"/api/pipeline/jobs/{job_id}",
        headers={"Idempotency-Key": "legacy-cancel-0003"},
    )

    assert response.status_code == 200
    assert repository.get_job(job_id)["status"] == "cancelled"
```

- [ ] **Step 2: Run the compatibility tests and verify process-memory behavior fails**

Run:

```powershell
python -m pytest tests/api/test_pipeline_compat.py -q
```

Expected: FAIL because the module still exposes `_jobs`, status disappears across app instances, and cancel only changes memory.

- [ ] **Step 3: Replace process-memory state with service delegation**

Rewrite `backend/routes/pipeline.py` around these complete helpers and endpoints; retain `PipelineRunRequest`, `NovelListResponse`, and the existing novel-list behavior, but delete `_jobs`, `_stage_list`, `_set_stage`, `_run_pipeline_thread`, and `_create_job`:

```python
from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field

from backend.orchestration.repository import JobConflictError, JobNotFoundError
from backend.orchestration.schemas import JobCreate


router = APIRouter(prefix="/api/pipeline", tags=["Pipeline Compatibility"])
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NOVELS_DIR = PROJECT_ROOT / "novels"
NOVELS_DIR.mkdir(parents=True, exist_ok=True)


class PipelineRunRequest(BaseModel):
    novel_path: str
    style: Optional[str] = None
    chapter: Optional[int] = None
    max_shots: int = Field(default=1, ge=1, le=6)
    tts_enabled: bool = True
    subtitles_enabled: bool = True
    bgm_enabled: bool = False


def _service(request: Request):
    return request.app.state.job_service


def _safe_project_id(path: Path) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", path.stem).strip(" .")
    return (value or f"legacy-{uuid.uuid4().hex[:8]}")[:128]


def _command(body: PipelineRunRequest, idempotency_key: str) -> JobCreate:
    novel_path = Path(body.novel_path).resolve()
    if not novel_path.is_file():
        raise HTTPException(status_code=404, detail=f"Novel not found: {body.novel_path}")
    return JobCreate(
        project_id=_safe_project_id(novel_path),
        input_path=str(novel_path),
        input_type="novel",
        mode="automatic",
        shot_duration=5,
        width=1080,
        height=1920,
        fps=24,
        options={
            "style": body.style or "realistic",
            "chapter": body.chapter,
            "max_shots": body.max_shots,
            "tts_enabled": body.tts_enabled,
            "subtitles_enabled": body.subtitles_enabled,
            "bgm_enabled": body.bgm_enabled,
        },
        idempotency_key=idempotency_key,
    )


def _legacy_view(job: dict) -> dict:
    settings = job.get("settings", {})
    input_path = settings.get("input_path", "")
    return {
        "job_id": job["id"],
        "novel": Path(input_path).name if input_path else "",
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "started_at": job["created_at"],
        "finished_at": job.get("finished_at"),
        "output_dir": "",
        "final_video": job["final_video"],
        "stage_list": job["steps"],
    }


@router.post("/run")
def run_pipeline(
    body: PipelineRunRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = idempotency_key or f"legacy-{uuid.uuid4()}"
    return _legacy_view(_service(request).create(_command(body, key)))


@router.post("/upload")
async def upload_and_run(
    request: Request,
    file: UploadFile = File(...),
    style: str | None = Form(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    safe_name = Path(file.filename or "").name
    if not safe_name.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files accepted")
    novel_path = (NOVELS_DIR / safe_name).resolve()
    if NOVELS_DIR.resolve() not in novel_path.parents:
        raise HTTPException(status_code=400, detail="Unsafe file name")
    novel_path.write_bytes(await file.read())
    body = PipelineRunRequest(novel_path=str(novel_path), style=style)
    key = idempotency_key or f"legacy-upload-{uuid.uuid4()}"
    return _legacy_view(_service(request).create(_command(body, key)))


@router.get("/status/{job_id}")
def get_status(job_id: str, request: Request):
    job = _service(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _legacy_view(job)


@router.delete("/jobs/{job_id}")
def cancel_job(
    job_id: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        job = _service(request).cancel(
            job_id, idempotency_key or f"legacy-cancel-{uuid.uuid4()}"
        )
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except JobConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _legacy_view(job)
```

Retain `/api/pipeline/novels` as a read-only listing endpoint. Its response must not scan or write outside `PROJECT_ROOT` and `NOVELS_DIR`.

- [ ] **Step 4: Run compatibility and durable API tests**

Run:

```powershell
python -m pytest tests/api/test_pipeline_compat.py tests/api/test_jobs_api.py -q
```

Expected: all tests PASS; a second app instance reads the same legacy job from SQLite.

- [ ] **Step 5: Commit the compatibility facade**

```powershell
git add backend/routes/pipeline.py tests/api/test_pipeline_compat.py
git commit -m "fix: persist legacy pipeline commands"
```

### Task 4: Persist project and input-source metadata in the canonical database

**Files:**
- Create: `backend/orchestration/migrations/005_projects_sources.sql`
- Create: `backend/projects/__init__.py`
- Create: `backend/projects/schemas.py`
- Create: `backend/projects/repository.py`
- Create: `backend/projects/service.py`
- Modify: `backend/routes/project.py`
- Modify: `backend/main.py`
- Create: `tests/projects/test_repository.py`
- Create: `tests/api/test_projects_api.py`

**Interfaces:**
- Consumes: `OrchestrationDatabase`
- Produces: `ProjectRepository.create/get/list/archive/add_source`, `ProjectService`, persistent `/api/projects`

- [ ] **Step 1: Write failing repository tests**

Create `tests/projects/test_repository.py`:

```python
from backend.orchestration.database import OrchestrationDatabase
from backend.projects.repository import ProjectRepository
from backend.projects.schemas import ProjectCreate, SourceCreate


def test_project_and_source_survive_repository_reopen(tmp_path):
    database_path = tmp_path / "studio.db"
    first = ProjectRepository(OrchestrationDatabase(database_path))
    project = first.create(ProjectCreate(name="午夜来电"))
    source = first.add_source(
        project["id"],
        SourceCreate(
            kind="idea",
            original_name="创意",
            original_location="午夜接到来自自己的电话",
            rights_confirmed=True,
        ),
    )

    second = ProjectRepository(OrchestrationDatabase(database_path))
    restored = second.get(project["id"])

    assert restored["name"] == "午夜来电"
    assert restored["target_duration_seconds"] == 60
    assert restored["sources"][0]["id"] == source["id"]


def test_archive_is_non_destructive(tmp_path):
    repository = ProjectRepository(
        OrchestrationDatabase(tmp_path / "studio.db")
    )
    project = repository.create(ProjectCreate(name="保留素材"))

    archived = repository.archive(project["id"])

    assert archived["status"] == "archived"
    assert repository.get(project["id"], include_archived=True) is not None
```

- [ ] **Step 2: Run repository tests and verify the projects package is missing**

Run:

```powershell
python -m pytest tests/projects/test_repository.py -q
```

Expected: FAIL during import because `backend.projects` does not exist.

- [ ] **Step 3: Add project/source tables as migration 005**

Create `backend/orchestration/migrations/005_projects_sources.sql`:

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'archived')),
    mode TEXT NOT NULL DEFAULT 'automatic'
        CHECK(mode IN ('automatic', 'manual_review')),
    content_style TEXT NOT NULL DEFAULT 'live_action',
    target_duration_seconds INTEGER NOT NULL DEFAULT 60
        CHECK(target_duration_seconds BETWEEN 30 AND 90),
    width INTEGER NOT NULL DEFAULT 1080,
    height INTEGER NOT NULL DEFAULT 1920,
    fps INTEGER NOT NULL DEFAULT 24,
    quality_preset TEXT NOT NULL DEFAULT 'preview_then_quality',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE source_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('idea', 'document', 'video', 'url')),
    original_name TEXT NOT NULL,
    original_location TEXT NOT NULL,
    managed_path TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    rights_confirmed INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_projects_status_updated
    ON projects(status, updated_at DESC);
CREATE INDEX idx_source_items_project_created
    ON source_items(project_id, created_at);
```

- [ ] **Step 4: Define project/source contracts**

Create an empty `backend/projects/__init__.py` and create `backend/projects/schemas.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    mode: Literal["automatic", "manual_review"] = "automatic"
    target_duration_seconds: int = Field(default=60, ge=30, le=90)
    width: int = Field(default=1080, ge=256, le=8192)
    height: int = Field(default=1920, ge=256, le=8192)
    fps: int = Field(default=24, ge=8, le=60)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("project name cannot be blank")
        return cleaned


class SourceCreate(BaseModel):
    kind: Literal["idea", "document", "video", "url"]
    original_name: str = Field(min_length=1, max_length=512)
    original_location: str = Field(min_length=1, max_length=8192)
    managed_path: str = ""
    sha256: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")
    rights_confirmed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 5: Implement the focused project repository and service**

Create `backend/projects/repository.py` with SQL confined to this class:

```python
from __future__ import annotations

import json
from uuid import uuid4

from backend.orchestration.repository import utcnow
from backend.projects.schemas import ProjectCreate, SourceCreate


class ProjectRepository:
    def __init__(self, database):
        self.database = database

    def create(self, command: ProjectCreate) -> dict:
        project_id = str(uuid4())
        now = utcnow()
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO projects(
                    id, name, description, mode, content_style,
                    target_duration_seconds, width, height, fps,
                    quality_preset, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'live_action', ?, ?, ?, ?,
                          'preview_then_quality', ?, ?)""",
                (
                    project_id, command.name, command.description, command.mode,
                    command.target_duration_seconds, command.width,
                    command.height, command.fps, now, now,
                ),
            )
        return self.get(project_id)

    def get(self, project_id: str, include_archived: bool = False) -> dict | None:
        condition = "" if include_archived else " AND status != 'archived'"
        with self.database.connection() as connection:
            row = connection.execute(
                f"SELECT * FROM projects WHERE id=?{condition}", (project_id,)
            ).fetchone()
            if row is None:
                return None
            project = dict(row)
            project["sources"] = [
                self._source(row)
                for row in connection.execute(
                    "SELECT * FROM source_items WHERE project_id=? ORDER BY created_at, id",
                    (project_id,),
                )
            ]
            return project

    def list(self, include_archived: bool = False) -> list[dict]:
        where = "" if include_archived else "WHERE status != 'archived'"
        with self.database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM projects {where} ORDER BY updated_at DESC, id"
                )
            ]

    def archive(self, project_id: str) -> dict:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE projects SET status='archived', updated_at=? WHERE id=?",
                (utcnow(), project_id),
            )
            if cursor.rowcount != 1:
                raise LookupError("project not found")
        return self.get(project_id, include_archived=True)

    def add_source(self, project_id: str, command: SourceCreate) -> dict:
        if self.get(project_id, include_archived=True) is None:
            raise LookupError("project not found")
        source_id = str(uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO source_items(
                    id, project_id, kind, original_name, original_location,
                    managed_path, sha256, rights_confirmed, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id, project_id, command.kind, command.original_name,
                    command.original_location, command.managed_path, command.sha256,
                    int(command.rights_confirmed),
                    json.dumps(command.metadata, ensure_ascii=False, sort_keys=True),
                    utcnow(),
                ),
            )
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM source_items WHERE id=?", (source_id,)
            ).fetchone()
            return self._source(row)

    @staticmethod
    def _source(row) -> dict:
        item = dict(row)
        item["rights_confirmed"] = bool(item["rights_confirmed"])
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item
```

Create `backend/projects/service.py`:

```python
class ProjectService:
    def __init__(self, repository):
        self.repository = repository

    def create(self, command):
        return self.repository.create(command)

    def get(self, project_id, include_archived=False):
        return self.repository.get(project_id, include_archived)

    def list(self, include_archived=False):
        return self.repository.list(include_archived)

    def archive(self, project_id):
        return self.repository.archive(project_id)

    def add_source(self, project_id, command):
        return self.repository.add_source(project_id, command)
```

- [ ] **Step 6: Replace the in-memory project API**

Rewrite `backend/routes/project.py` so it has no `_projects`, no directory scan, and no `shutil.rmtree`:

```python
from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.projects.schemas import ProjectCreate, SourceCreate


router = APIRouter(prefix="/api/projects", tags=["Projects"])


def _service(request: Request):
    return request.app.state.project_service


@router.get("")
def list_projects(
    request: Request,
    include_archived: bool = Query(default=False),
):
    items = _service(request).list(include_archived)
    return {"total": len(items), "projects": items}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(command: ProjectCreate, request: Request):
    return _service(request).create(command)


@router.get("/{project_id}")
def get_project(project_id: str, request: Request):
    project = _service(request).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project_id}/sources", status_code=status.HTTP_201_CREATED)
def add_source(project_id: str, command: SourceCreate, request: Request):
    try:
        return _service(request).add_source(project_id, command)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{project_id}")
def archive_project(project_id: str, request: Request):
    try:
        return _service(request).archive(project_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
```

In `backend/main.py`, import the service/repository and attach them to the same database used by jobs immediately after `create_job_runtime` returns:

```python
from backend.projects.repository import ProjectRepository
from backend.projects.service import ProjectService

app.state.project_service = ProjectService(
    ProjectRepository(repository.database)
)
```

- [ ] **Step 7: Add API persistence tests**

Create `tests/api/test_projects_api.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.projects.repository import ProjectRepository
from backend.projects.service import ProjectService
from backend.routes.project import router


def client_for(path):
    app = FastAPI()
    app.state.project_service = ProjectService(
        ProjectRepository(OrchestrationDatabase(path))
    )
    app.include_router(router)
    return TestClient(app)


def test_project_api_persists_and_delete_archives(tmp_path):
    database = tmp_path / "studio.db"
    first = client_for(database)
    created = first.post("/api/projects", json={"name": "午夜来电"})
    assert created.status_code == 201
    project_id = created.json()["id"]

    second = client_for(database)
    assert second.get(f"/api/projects/{project_id}").status_code == 200
    assert second.delete(f"/api/projects/{project_id}").status_code == 200
    assert second.get(f"/api/projects/{project_id}").status_code == 404
    archived = second.get("/api/projects?include_archived=true").json()
    assert archived["projects"][0]["status"] == "archived"
```

- [ ] **Step 8: Run project, migration, and API tests**

Run:

```powershell
python -m pytest tests/projects/test_repository.py tests/api/test_projects_api.py tests/orchestration/test_repository.py -q
```

Expected: all tests PASS; reopening the database preserves projects and source metadata, and DELETE never removes files.

- [ ] **Step 9: Commit canonical project persistence**

```powershell
git add backend/orchestration/migrations/005_projects_sources.sql backend/projects backend/routes/project.py backend/main.py tests/projects/test_repository.py tests/api/test_projects_api.py
git commit -m "feat: persist projects and source metadata"
```

### Task 5: Make `run.py` the only formal CLI production entry

**Files:**
- Create: `config/entrypoints.yaml`
- Modify: `run.py`
- Modify: `README.md`
- Create: `tests/runtime/test_entrypoint.py`

**Interfaces:**
- Consumes: `/api/jobs`, `/api/jobs/{id}`
- Produces: `api_json_request`, `submit_job`, `monitor_job`; one machine-readable entrypoint policy

- [ ] **Step 1: Write failing entrypoint tests**

Create `tests/runtime/test_entrypoint.py`:

```python
import json
from pathlib import Path

import yaml

import run


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_submit_job_posts_to_durable_api(tmp_path):
    novel = tmp_path / "story.txt"
    novel.write_text("测试故事", encoding="utf-8")
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        return FakeResponse({"id": "job-1", "status": "queued"})

    result = run.submit_job(
        novel, style="realistic", base_url="http://127.0.0.1:8800", opener=opener
    )

    assert captured["url"] == "http://127.0.0.1:8800/api/jobs"
    assert captured["payload"]["input_path"] == str(novel.resolve())
    assert result["id"] == "job-1"


def test_formal_launcher_source_does_not_spawn_historical_pipeline():
    source = Path(run.__file__).read_text(encoding="utf-8")
    assert "PROJECT_ROOT / \"pipeline.py\"" not in source
    assert "orchestrator.py --novel" not in source


def test_entrypoint_manifest_has_one_canonical_cli():
    manifest = yaml.safe_load(
        Path("config/entrypoints.yaml").read_text(encoding="utf-8")
    )
    assert manifest["canonical"]["cli"] == "run.py"
    assert manifest["canonical"]["api"] == "backend.main:app"
    assert all(item["status"] != "canonical" for item in manifest["reference_only"])
```

- [ ] **Step 2: Run entrypoint tests and verify direct-script launching fails**

Run:

```powershell
python -m pytest tests/runtime/test_entrypoint.py -q
```

Expected: FAIL because `submit_job` and the manifest do not exist and `run.py` still names/spawns historical pipelines.

- [ ] **Step 3: Add the machine-readable entrypoint policy**

Create `config/entrypoints.yaml`:

```yaml
schema_version: 1
canonical:
  cli: "run.py"
  api: "backend.main:app"
  job_api: "/api/jobs"
  project_api: "/api/projects"
compatibility:
  - path: "backend/routes/pipeline.py"
    status: "durable_facade"
reference_only:
  - {path: "backend_v3", status: "reference_only"}
  - {path: "backend_v4", status: "reference_only"}
  - {path: "backend_v6", status: "reference_only"}
  - {path: "backend_v7", status: "reference_only"}
  - {path: "backend_v10", status: "reference_only"}
  - {path: "backend_v11", status: "reference_only"}
  - {path: "pipeline.py", status: "reference_only"}
  - {path: "orchestrator.py", status: "reference_only"}
policy:
  delete_legacy_files: false
  allow_placeholder_success: false
```

- [ ] **Step 4: Submit and monitor jobs through the canonical API**

Add `json`, `urllib.error`, `urllib.request`, and `uuid` imports to `run.py`. Replace the direct `pipeline.py` subprocess logic with these functions:

```python
def api_json_request(
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    base_url: str = f"http://{BACKEND_HOST}:{BACKEND_PORT}",
    opener=None,
) -> dict | None:
    opener = opener or urllib.request.urlopen
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener(request, timeout=10) as response:
            body = response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"本地服务不可用：{error}") from error
    return json.loads(body) if body else None


def submit_job(
    novel_path: str | Path,
    style: str | None = None,
    *,
    base_url: str = f"http://{BACKEND_HOST}:{BACKEND_PORT}",
    opener=None,
) -> dict:
    novel = Path(novel_path).resolve()
    if not novel.is_file():
        raise FileNotFoundError(f"输入文件不存在：{novel}")
    return api_json_request(
        "POST",
        "/api/jobs",
        {
            "project_id": novel.stem,
            "input_path": str(novel),
            "input_type": "novel",
            "mode": "automatic",
            "shot_duration": 5,
            "width": 1080,
            "height": 1920,
            "fps": 24,
            "options": {"style": style or "realistic"},
            "idempotency_key": f"cli-{uuid.uuid4()}",
        },
        base_url=base_url,
        opener=opener,
    )


def monitor_job(job_id: str, poll_seconds: float = 1.0) -> int:
    last = None
    while True:
        job = api_json_request("GET", f"/api/jobs/{job_id}")
        snapshot = (job["status"], job["progress"], job["message"])
        if snapshot != last:
            print(f"  [{job['status']}] {job['progress']:.0%} {job['message']}")
            last = snapshot
        if job["status"] == "completed":
            return 0
        if job["status"] in {"failed", "cancelled"}:
            return 1
        time.sleep(poll_seconds)


def run_pipeline(novel_path: str, style: str | None = None, config: str | None = None):
    if config:
        raise ValueError("The canonical durable API does not accept legacy config files")
    if not is_port_in_use(BACKEND_PORT):
        start_backend()
        if not wait_for_service(
            f"http://{BACKEND_HOST}:{BACKEND_PORT}/health",
            max_wait=30,
            name="Backend",
        ):
            raise RuntimeError("本地后端启动失败")
    job = submit_job(novel_path, style=style)
    print(f"  Durable job created: {job['id']}")
    return monitor_job(job["id"])
```

Remove the `pipeline.py` subprocess block and the `orchestrator.py --novel` examples. Do not alter or delete historical files.

- [ ] **Step 5: Document the formal entry and fail-closed milestone**

Replace the top “Quick Start” section of `README.md` with this exact foundation status:

```markdown
## 正式运行入口

- CLI：`python run.py --web` 或 `python run.py --novel <文本路径>`
- API：`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8800`
- 正式任务接口：`/api/jobs`

`backend_v3/v4/v6/v7/v10/v11`、根目录 `pipeline.py` 和
`orchestrator.py` 仅保留为历史参考，不再是正式生产入口。

当前里程碑只提供可靠任务与项目底座。真实本地模型执行器未安装时，
任务会以 `PIPELINE_NOT_READY` 明确失败，不会生成占位图片或伪成片。
```

- [ ] **Step 6: Run entrypoint and CLI syntax tests**

Run:

```powershell
python -m pytest tests/runtime/test_entrypoint.py -q
python -m py_compile run.py backend/main.py
```

Expected: all tests PASS and both Python files compile without output.

- [ ] **Step 7: Commit the formal entrypoint policy**

```powershell
git add config/entrypoints.yaml run.py README.md tests/runtime/test_entrypoint.py
git commit -m "refactor: route the formal CLI through durable jobs"
```

### Task 6: Prove the unified foundation contract

**Files:**
- Create: `tests/acceptance/test_foundation_contract.py`
- Create: `docs/architecture/unified-production-foundation.md`

**Interfaces:**
- Consumes: all Tasks 1–5
- Produces: one deterministic acceptance gate and an operator-facing boundary document

- [ ] **Step 1: Add a cross-module acceptance test**

Create `tests/acceptance/test_foundation_contract.py`:

```python
from pathlib import Path
from types import SimpleNamespace

from backend.main import create_job_runtime
from backend.orchestration.schemas import JobCreate
from backend.projects.repository import ProjectRepository
from backend.projects.schemas import ProjectCreate, SourceCreate
from backend.runtime.paths import RuntimePaths


class IdleRunner:
    def __init__(self, repository):
        self.repository = repository

    def run_next(self, job, cancel_requested):
        return None

    def cancel(self, job_id):
        return False


def test_one_database_restores_job_project_and_source(tmp_path):
    config = SimpleNamespace(
        orchestration=SimpleNamespace(
            database_path="database/studio.db",
            retry_delays_seconds=[0, 0, 0],
            lease_seconds=30,
            heartbeat_seconds=10,
            worker_poll_seconds=0.01,
        )
    )
    paths = RuntimePaths(
        application_root=tmp_path,
        data_root=tmp_path,
        database_dir=tmp_path / "database",
        orchestration_database=tmp_path / "database" / "studio.db",
        logs_dir=tmp_path / "logs",
        projects_dir=tmp_path / "projects",
        output_dir=tmp_path / "output",
        cache_dir=tmp_path / "cache",
        temp_dir=tmp_path / "temp",
    )
    job_repository, _, _ = create_job_runtime(
        config, runner_factory=IdleRunner, runtime_paths=paths
    )
    project_repository = ProjectRepository(job_repository.database)
    project = project_repository.create(ProjectCreate(name="统一底座验收"))
    project_repository.add_source(
        project["id"],
        SourceCreate(
            kind="idea",
            original_name="创意",
            original_location="一个来自未来的电话",
            rights_confirmed=True,
        ),
    )
    job = job_repository.create_job(
        JobCreate(
            project_id=project["id"],
            input_path="inputs/idea.txt",
            input_type="novel",
            idempotency_key="acceptance-job-0001",
        )
    )

    reopened_jobs, _, _ = create_job_runtime(
        config, runner_factory=IdleRunner, runtime_paths=paths
    )
    reopened_projects = ProjectRepository(reopened_jobs.database)

    assert reopened_jobs.get_job(job["id"])["status"] == "queued"
    assert reopened_projects.get(project["id"])["sources"][0]["kind"] == "idea"
    assert not list(tmp_path.rglob("*.mp4"))


def test_reference_directories_are_not_part_of_the_formal_backend():
    main_source = Path("backend/main.py").read_text(encoding="utf-8")
    for legacy in (
        "backend_v3", "backend_v4", "backend_v6", "backend_v7",
        "backend_v10", "backend_v11",
    ):
        assert legacy not in main_source
```

- [ ] **Step 2: Run the complete deterministic foundation suite**

Run:

```powershell
python -m pytest tests/orchestration tests/api tests/projects tests/runtime tests/acceptance/test_foundation_contract.py -q
python -m pytest tests/test_pipeline_v5.py -q
```

Expected: all tests PASS. The historical focused V5 tests still collect, but the formal API/CLI never invokes their fallback path.

- [ ] **Step 3: Perform a local backend smoke test**

Start the backend:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8800
```

In a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8800/health
Invoke-RestMethod http://127.0.0.1:8800/api/jobs/current
Invoke-RestMethod http://127.0.0.1:8800/api/projects
```

Expected: `/health` returns HTTP 200, `/api/jobs/current` returns a job or JSON `null`, and `/api/projects` returns a persistent list. Stop uvicorn, start it again, and confirm the same project/job rows remain.

- [ ] **Step 4: Document the implemented boundary**

Create `docs/architecture/unified-production-foundation.md`:

```markdown
# Unified Production Foundation

## Canonical path

- CLI: `run.py`
- API application: `backend.main:app`
- Job commands: `/api/jobs`
- Project metadata: `/api/projects`
- Database: `<data_root>/database/orchestration.db`

## Implemented

- Durable jobs, commands, leases, retries, checkpoints and restart recovery
- Persistent projects and source metadata
- Legacy pipeline compatibility through the durable job service
- Portable runtime paths and a local-only configuration guard
- Explicit `PIPELINE_NOT_READY` failure when no production adapter is installed

## Not implemented in this milestone

- Model discovery or download
- ComfyUI workflow execution
- Script, character, scene or storyboard generation
- TTS, lip sync, subtitles, BGM, composition or Jianying export
- Electron desktop packaging

Those capabilities belong to the subsequent sub-projects in the approved
2026-07-22 design. Historical backends and scripts remain reference-only and
must not be used to claim production success.
```

- [ ] **Step 5: Verify the staged scope and commit the acceptance gate**

```powershell
git add tests/acceptance/test_foundation_contract.py docs/architecture/unified-production-foundation.md
git diff --cached --check
git diff --cached --name-status
git commit -m "test: define unified foundation acceptance"
```

Expected staged files: only the acceptance test and architecture document. Commit succeeds.

## Final verification checkpoint

Run:

```powershell
python -m pytest tests/orchestration tests/api tests/projects tests/runtime tests/acceptance/test_foundation_contract.py -q
python -m pytest tests/test_pipeline_v5.py -q
python -m py_compile run.py backend/main.py
git status --short
```

Expected:

- all deterministic foundation tests pass;
- focused historical V5 tests still pass or any pre-existing failure is documented without changing reference code;
- `run.py` and `backend/main.py` compile;
- no reference project or historical backend is modified;
- existing unrelated untracked files remain untouched;
- no `.mp4`, placeholder image, or fake success artifact is generated;
- the only new commits are the six task-scoped commits in this plan.
