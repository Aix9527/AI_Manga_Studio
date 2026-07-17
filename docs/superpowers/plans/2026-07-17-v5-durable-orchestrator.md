# V5 Durable Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace process-memory pipeline threads with a SQLite-backed job orchestrator that survives navigation, browser refresh, backend restart, and computer restart.

**Architecture:** FastAPI owns a single local `DurableWorker` started by application lifespan. REST commands and the worker both operate through a transactional SQLite repository; job events reach the Web client over SSE with polling fallback. Step execution is injected through a protocol so persistence and recovery can be tested without ComfyUI.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, SQLite WAL, pytest, pytest-asyncio

---

**Depends on:** `docs/superpowers/specs/2026-07-17-ai-short-drama-studio-v5-design.md`

**Produces:** A durable API and worker that can execute a fake pipeline end to end. The real V5 production executor is connected in the next plan.

## File structure

| Path | Responsibility |
|---|---|
| `.gitignore` | Keep models, generated media, databases, caches and secrets out of Git |
| `pytest.ini` | Restrict discovery to the repository test suite |
| `backend/orchestration/enums.py` | Job/step states and legal transitions |
| `backend/orchestration/schemas.py` | API and repository value objects |
| `backend/orchestration/database.py` | SQLite connection, migrations and transactions |
| `backend/orchestration/migrations/001_jobs.sql` | Durable job schema |
| `backend/orchestration/repository.py` | All task-state reads and writes |
| `backend/orchestration/checkpoints.py` | Artifact hashing and checkpoint validation |
| `backend/orchestration/worker.py` | Leasing, retries, recovery and cancellation |
| `backend/orchestration/service.py` | Application commands and current-job selection |
| `backend/routes/jobs.py` | Job REST and SSE API |
| `backend/production/executor.py` | Explicit not-ready runner until the production plan replaces it |
| `backend/main.py` | Lifespan wiring |
| `backend/config.py` | Orchestrator configuration |
| `backend/routes/pipeline.py` | Compatibility wrapper for old V5 endpoints |
| `tests/orchestration/*` | State, persistence, checkpoint, worker and recovery tests |
| `tests/api/test_jobs_api.py` | API behavior and idempotency tests |

### Task 1: Establish repository and test hygiene

**Files:**
- Create: `.gitignore`
- Create: `pytest.ini`

- [ ] **Step 1: Add a repository ignore policy**

Create `.gitignore` with this content:

```gitignore
# Python
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/

# Frontend
frontend/node_modules/
frontend/dist/
frontend/.vite/

# Runtime state and generated media
database/*.db
database/*.db-*
logs/
cache/
storage/
output/
outputs/
renders/
temp/
project/
projects/*/artifacts/
novels/

# Large local engines and models
comfyui/
127.0.0.1_8188/
models/
workflow/downloaded/

# Local brainstorming UI
.superpowers/

# Secrets and OS files
.env
.env.*
!.env.example
Thumbs.db
.DS_Store
```

- [ ] **Step 2: Restrict pytest discovery**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
norecursedirs = comfyui 127.0.0.1_8188 output outputs renders storage cache .git frontend/node_modules
addopts = -ra
asyncio_mode = auto
```

- [ ] **Step 3: Verify collection no longer enters ComfyUI or output folders**

Run:

```powershell
python -m pytest --collect-only -q
```

Expected: only tests under `tests/` are listed; no import errors from `comfyui/` or generated output directories.

- [ ] **Step 4: Record the curated source baseline**

Run:

```powershell
git add .gitignore pytest.ini requirements.txt backend frontend/src frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/index.html config workflow/*.json workflow/templates tests run.py run.ps1 *.bat docs
git status --short
git commit -m "chore: establish V5 source baseline"
```

Expected: source and configuration are committed; models, generated media, databases, logs and caches are absent from the staged list.

### Task 2: Define durable states, commands and configuration

**Files:**
- Create: `backend/orchestration/__init__.py`
- Create: `backend/orchestration/enums.py`
- Create: `backend/orchestration/schemas.py`
- Modify: `backend/config.py:39-190`
- Test: `tests/orchestration/test_state_machine.py`

- [ ] **Step 1: Write the failing transition and request-validation tests**

Create `tests/orchestration/test_state_machine.py`:

```python
import pytest
from pydantic import ValidationError

from backend.orchestration.enums import JobStatus, assert_transition
from backend.orchestration.schemas import JobCreate


def test_failed_job_can_resume_but_completed_job_cannot_run_again():
    assert_transition(JobStatus.FAILED, JobStatus.QUEUED)
    with pytest.raises(ValueError, match="completed -> queued"):
        assert_transition(JobStatus.COMPLETED, JobStatus.QUEUED)


@pytest.mark.parametrize("duration", [4.99, 15.01])
def test_job_rejects_shot_duration_outside_five_to_fifteen_seconds(duration):
    with pytest.raises(ValidationError):
        JobCreate(
            project_id="project-1",
            input_path="novel.txt",
            input_type="novel",
            shot_duration=duration,
            width=1080,
            height=1920,
        )


@pytest.mark.parametrize("project_id", ["../escape", "folder/name", "folder\\name", "CON", "name. "])
def test_job_rejects_project_names_that_cannot_be_safe_windows_folders(project_id):
    with pytest.raises(ValidationError):
        JobCreate(
            project_id=project_id, input_path="input.txt", input_type="novel",
            shot_duration=5, width=1080, height=1920,
            idempotency_key="safe-name-test",
        )
```

- [ ] **Step 2: Run the tests and verify missing modules fail**

Run:

```powershell
python -m pytest tests/orchestration/test_state_machine.py -q
```

Expected: FAIL during import because `backend.orchestration` does not exist.

- [ ] **Step 3: Implement states and legal transitions**

Create `backend/orchestration/__init__.py` as an empty package marker and create `backend/orchestration/enums.py`:

```python
from enum import StrEnum


class JobStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    CANCELLED = "cancelled"


LEGAL_JOB_TRANSITIONS = {
    JobStatus.DRAFT: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.CANCELLED},
    JobStatus.RUNNING: {
        JobStatus.RETRY_WAIT,
        JobStatus.WAITING_REVIEW,
        JobStatus.FAILED,
        JobStatus.PAUSED,
        JobStatus.COMPLETED,
        JobStatus.CANCELLED,
    },
    JobStatus.RETRY_WAIT: {JobStatus.QUEUED, JobStatus.FAILED, JobStatus.PAUSED, JobStatus.CANCELLED},
    JobStatus.WAITING_REVIEW: {JobStatus.QUEUED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.FAILED: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.PAUSED: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.CANCELLED: set(),
}


def assert_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in LEGAL_JOB_TRANSITIONS[current]:
        raise ValueError(f"illegal job transition: {current} -> {target}")
```

- [ ] **Step 4: Implement validated command schemas**

Create `backend/orchestration/schemas.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from backend.orchestration.enums import JobStatus, StepStatus


InputType = Literal["novel", "script", "storyboard"]
JobMode = Literal["automatic", "manual_review"]


class JobCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    input_path: str = Field(min_length=1)
    input_type: InputType
    mode: JobMode = "automatic"
    shot_duration: float = Field(default=5.0, ge=5.0, le=15.0)
    width: int = Field(default=1080, ge=256, le=8192)
    height: int = Field(default=1920, ge=256, le=8192)
    fps: int = Field(default=24, ge=8, le=60)
    options: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("width", "height")
    @classmethod
    def require_even_dimensions(cls, value: int) -> int:
        if value % 2:
            raise ValueError("video dimensions must be even")
        return value

    @field_validator("project_id")
    @classmethod
    def require_safe_project_folder(cls, value: str) -> str:
        cleaned = value.strip()
        forbidden = '<>:"/\\|?*'
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if not cleaned or cleaned in {".", ".."} or any(char in forbidden or ord(char) < 32 for char in cleaned):
            raise ValueError("project name contains unsafe path characters")
        if cleaned.rstrip(" .") != cleaned or cleaned.upper() in reserved:
            raise ValueError("project name is not a valid Windows folder")
        return cleaned


class JobStepView(BaseModel):
    id: str
    stage_key: str
    shot_id: str | None = None
    status: StepStatus
    attempt: int
    progress: float
    error_code: str = ""
    error_message: str = ""


class JobView(BaseModel):
    id: str
    project_id: str
    status: JobStatus
    mode: JobMode
    desired_state: str = "running"
    current_stage: str = ""
    current_shot: str = ""
    progress: float = 0.0
    message: str = ""
    final_video: str = ""
    created_at: datetime
    updated_at: datetime
    steps: list[JobStepView] = Field(default_factory=list)


class JobAction(BaseModel):
    step_id: str | None = None
    comment: str = ""


class RollbackAction(BaseModel):
    step_id: str
    confirm_invalidated_step_ids: list[str]


class ReviewAction(BaseModel):
    action: Literal["approve", "edit", "retry", "rollback"]
    comment: str = ""
    patch: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 5: Add orchestrator configuration and run the tests**

Add this model to `backend/config.py` and add `orchestration` to `AppConfig`:

```python
class OrchestrationConfig(BaseModel):
    database_path: str = "D:/AI_Manga_Studio/database/orchestration.db"
    worker_poll_seconds: float = 0.5
    lease_seconds: int = 30
    heartbeat_seconds: int = 10
    max_retries: int = 3
    retry_delays_seconds: List[int] = [5, 15, 45]


class AppConfig(BaseModel):
    # retain the existing fields
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
```

Run:

```powershell
python -m pytest tests/orchestration/test_state_machine.py -q
```

Expected: 3 passed.

- [ ] **Step 6: Commit the state contract**

```powershell
git add backend/orchestration backend/config.py tests/orchestration/test_state_machine.py
git commit -m "feat: define durable job state contract"
```

### Task 3: Build the transactional SQLite repository

**Files:**
- Create: `backend/orchestration/migrations/001_jobs.sql`
- Create: `backend/orchestration/database.py`
- Create: `backend/orchestration/repository.py`
- Test: `tests/orchestration/test_repository.py`

- [ ] **Step 1: Write persistence and idempotency tests**

Create `tests/orchestration/test_repository.py`:

```python
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate


def request(key="request-0001"):
    return JobCreate(
        project_id="p1",
        input_path="input.txt",
        input_type="novel",
        shot_duration=5,
        width=1080,
        height=1920,
        idempotency_key=key,
    )


def test_job_survives_repository_reopen(tmp_path):
    path = tmp_path / "orchestration.db"
    first = JobRepository(OrchestrationDatabase(path))
    job = first.create_job(request())
    second = JobRepository(OrchestrationDatabase(path))
    restored = second.get_job(job["id"])
    assert restored["project_id"] == "p1"
    assert restored["status"] == "queued"


def test_idempotency_key_returns_existing_job(tmp_path):
    repo = JobRepository(OrchestrationDatabase(tmp_path / "jobs.db"))
    first = repo.create_job(request())
    second = repo.create_job(request())
    assert second["id"] == first["id"]
```

- [ ] **Step 2: Run the tests and verify the database module is missing**

Run:

```powershell
python -m pytest tests/orchestration/test_repository.py -q
```

Expected: FAIL because `OrchestrationDatabase` is not defined.

- [ ] **Step 3: Create the schema migration**

Create `backend/orchestration/migrations/001_jobs.sql`:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    input_path TEXT NOT NULL,
    input_type TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    desired_state TEXT NOT NULL DEFAULT 'running',
    current_stage TEXT NOT NULL DEFAULT '',
    current_shot TEXT NOT NULL DEFAULT '',
    progress REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    final_video TEXT NOT NULL DEFAULT '',
    settings_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    worker_id TEXT,
    lease_until TEXT,
    run_after TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS job_steps (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    stage_key TEXT NOT NULL,
    shot_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    progress REAL NOT NULL DEFAULT 0,
    input_hash TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(job_id, sequence, shot_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL REFERENCES job_steps(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    validated_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(step_id, kind, path)
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_actions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL REFERENCES job_steps(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    comment TEXT NOT NULL,
    patch_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_steps_job_sequence ON job_steps(job_id, sequence);
CREATE INDEX IF NOT EXISTS idx_events_job_id ON job_events(job_id, id);
```

- [ ] **Step 4: Implement connection and migration handling**

Create `backend/orchestration/database.py`:

```python
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class OrchestrationDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        migration = Path(__file__).parent / "migrations" / "001_jobs.sql"
        with self.connect() as conn:
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, datetime('now'))"
            )
            conn.commit()
```

- [ ] **Step 5: Implement repository creation and reads**

Create `backend/orchestration/repository.py` with these methods and keep SQL inside this class:

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.schemas import JobCreate


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def rowdict(row) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class JobRepository:
    def __init__(self, database: OrchestrationDatabase):
        self.database = database

    def create_job(self, request: JobCreate) -> dict[str, Any]:
        with self.database.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if existing:
                return dict(existing)
            job_id = str(uuid.uuid4())
            now = utcnow()
            conn.execute(
                """INSERT INTO jobs(
                    id, project_id, input_path, input_type, mode, status,
                    settings_json, idempotency_key, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
                (
                    job_id,
                    request.project_id,
                    request.input_path,
                    request.input_type,
                    request.mode,
                    request.model_dump_json(),
                    request.idempotency_key,
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO job_events(job_id, event_type, payload_json, created_at) VALUES(?, 'job.created', '{}', ?)",
                (job_id, now),
            )
            return dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.database.connect() as conn:
            job = rowdict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
            if not job:
                return None
            job["settings"] = json.loads(job.pop("settings_json"))
            job["steps"] = [dict(row) for row in conn.execute(
                "SELECT * FROM job_steps WHERE job_id = ? ORDER BY sequence, shot_id",
                (job_id,),
            )]
            return job

    def get_current_job(self) -> dict[str, Any] | None:
        terminal = ("completed", "cancelled")
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT id FROM jobs WHERE status NOT IN (?, ?) ORDER BY updated_at DESC LIMIT 1",
                terminal,
            ).fetchone()
        return self.get_job(row["id"]) if row else None

    def list_jobs(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )]
        for row in rows:
            row.pop("settings_json", None)
        return rows

    def append_event(self, job_id: str, event_type: str, payload: dict[str, Any]) -> int:
        with self.database.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO job_events(job_id, event_type, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (job_id, event_type, json.dumps(payload, ensure_ascii=False), utcnow()),
            )
            return int(cursor.lastrowid)

    def list_events(self, job_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM job_events WHERE job_id = ? AND id > ? ORDER BY id",
                (job_id, after_id),
            )]
```

- [ ] **Step 6: Run repository tests**

```powershell
python -m pytest tests/orchestration/test_repository.py -q
```

Expected: 2 passed.

- [ ] **Step 7: Commit the persistence layer**

```powershell
git add backend/orchestration tests/orchestration/test_repository.py
git commit -m "feat: persist V5 jobs and events in SQLite"
```

### Task 4: Add validated artifact checkpoints

**Files:**
- Create: `backend/orchestration/checkpoints.py`
- Modify: `backend/orchestration/repository.py`
- Test: `tests/orchestration/test_checkpoints.py`

- [ ] **Step 1: Write a failing checkpoint integrity test**

Create `tests/orchestration/test_checkpoints.py`:

```python
import uuid

from backend.orchestration.checkpoints import ArtifactDraft, validate_checkpoint
from backend.orchestration.schemas import JobCreate


def test_checkpoint_becomes_invalid_when_artifact_changes(tmp_path):
    artifact = tmp_path / "shot.json"
    artifact.write_text('{"shot": 1}', encoding="utf-8")
    draft = ArtifactDraft.from_path("shot_plan", artifact, {"shots": 1})
    assert validate_checkpoint([draft], expected_input_hash="abc", actual_input_hash="abc")
    artifact.write_text('{"shot": 2}', encoding="utf-8")
    assert not validate_checkpoint([draft], expected_input_hash="abc", actual_input_hash="abc")


def test_restart_reconciliation_preserves_other_shots(job_repo, tmp_path):
    job = job_repo.create_job(JobCreate(
        project_id="checkpoint", input_path="input.txt", input_type="novel",
        shot_duration=5, width=1080, height=1920, idempotency_key="checkpoint-request",
    ))
    first_id, other_id, compose_id = (str(uuid.uuid4()) for _ in range(3))
    with job_repo.database.transaction() as conn:
        conn.executemany(
            "INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status) VALUES(?, ?, ?, ?, ?, 'pending')",
            [
                (first_id, job["id"], 4, "first_frame", "shot-1"),
                (other_id, job["id"], 4, "first_frame", "shot-2"),
                (compose_id, job["id"], 10, "compose_export", ""),
            ],
        )
    first = tmp_path / "shot-1.png"; first.write_bytes(b"one")
    other = tmp_path / "shot-2.png"; other.write_bytes(b"two")
    job_repo.complete_step(job["id"], first_id, "hash-1", [ArtifactDraft.from_path("first_frame", first)])
    job_repo.complete_step(job["id"], other_id, "hash-2", [ArtifactDraft.from_path("first_frame", other)])
    first.unlink()
    assert job_repo.reconcile_checkpoints() == 1
    restored = job_repo.get_job(job["id"])
    statuses = {step["id"]: step["status"] for step in restored["steps"]}
    assert statuses[first_id] == "queued"
    assert statuses[other_id] == "completed"
    assert statuses[compose_id] == "queued"
```

- [ ] **Step 2: Run the test and verify it fails**

```powershell
python -m pytest tests/orchestration/test_checkpoints.py -q
```

Expected: FAIL because `ArtifactDraft` is missing.

- [ ] **Step 3: Implement hashing and validation**

Create `backend/orchestration/checkpoints.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArtifactDraft:
    kind: str
    path: str
    sha256: str
    size: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(cls, kind: str, path: str | Path, metadata: dict[str, Any] | None = None):
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        return cls(kind, str(resolved), sha256_file(resolved), resolved.stat().st_size, metadata or {})


def validate_checkpoint(
    artifacts: Iterable[ArtifactDraft],
    expected_input_hash: str,
    actual_input_hash: str,
) -> bool:
    if expected_input_hash != actual_input_hash:
        return False
    for artifact in artifacts:
        path = Path(artifact.path)
        if not path.is_file() or path.stat().st_size != artifact.size:
            return False
        if sha256_file(path) != artifact.sha256:
            return False
    return True
```

- [ ] **Step 4: Add atomic step completion to the repository**

Add `complete_step` to `JobRepository` so artifacts and step success commit together:

```python
def complete_step(self, job_id, step_id, step_input_hash, artifacts):
    import json
    import uuid
    from backend.orchestration.repository import utcnow

    with self.database.transaction() as conn:
        for artifact in artifacts:
            conn.execute(
                """INSERT INTO artifacts(
                    id, job_id, step_id, kind, path, sha256, size, metadata_json, validated_at, active
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(step_id, kind, path) DO UPDATE SET
                    sha256=excluded.sha256, size=excluded.size,
                    metadata_json=excluded.metadata_json,
                    validated_at=excluded.validated_at, active=1""",
                (
                    str(uuid.uuid4()), job_id, step_id, artifact.kind, artifact.path,
                    artifact.sha256, artifact.size,
                    json.dumps(artifact.metadata, ensure_ascii=False), utcnow(),
                ),
            )
        conn.execute(
            """UPDATE job_steps SET status='completed', progress=1, input_hash=?,
               error_code='', error_message='', finished_at=? WHERE id=? AND job_id=?""",
            (step_input_hash, utcnow(), step_id, job_id),
        )

def reconcile_checkpoints(self) -> int:
    from pathlib import Path
    from backend.orchestration.checkpoints import sha256_file

    with self.database.connect() as conn:
        rows = list(conn.execute(
            "SELECT job_id, step_id, path, sha256, size FROM artifacts WHERE active=1"
        ))
    invalid: list[tuple[str, str]] = []
    for row in rows:
        path = Path(row["path"])
        if not path.is_file() or path.stat().st_size != row["size"] or sha256_file(path) != row["sha256"]:
            key = (row["job_id"], row["step_id"])
            if key not in invalid:
                invalid.append(key)
    for job_id, step_id in invalid:
        with self.database.transaction() as conn:
            selected = conn.execute(
                "SELECT sequence, shot_id FROM job_steps WHERE id=? AND job_id=?",
                (step_id, job_id),
            ).fetchone()
            downstream = [item["id"] for item in conn.execute(
                """SELECT id FROM job_steps WHERE job_id=? AND sequence>?
                   AND (?='' OR shot_id=? OR shot_id='') ORDER BY sequence, shot_id""",
                (job_id, selected["sequence"], selected["shot_id"], selected["shot_id"]),
            )]
            affected = [step_id, *downstream]
            marks = ",".join("?" for _ in affected)
            conn.execute(
                f"UPDATE artifacts SET active=0 WHERE job_id=? AND step_id IN ({marks})",
                (job_id, *affected),
            )
            conn.execute(
                f"UPDATE job_steps SET status='queued', input_hash='' WHERE job_id=? AND id IN ({marks})",
                (job_id, *affected),
            )
            conn.execute(
                """UPDATE jobs SET status='queued', desired_state='running', final_video='', run_after=NULL,
                   message='检测到检查点损坏，已从受影响步骤恢复', worker_id=NULL,
                   lease_until=NULL, updated_at=? WHERE id=?""",
                (utcnow(), job_id),
            )
    return len(invalid)
```

- [ ] **Step 5: Run checkpoint and repository tests**

```powershell
python -m pytest tests/orchestration/test_checkpoints.py tests/orchestration/test_repository.py -q
```

Expected: 3 passed.

- [ ] **Step 6: Commit checkpoint support**

```powershell
git add backend/orchestration tests/orchestration/test_checkpoints.py
git commit -m "feat: validate and persist production checkpoints"
```

### Task 5: Implement leasing, retries and restart recovery

**Files:**
- Create: `backend/orchestration/worker.py`
- Modify: `backend/orchestration/repository.py`
- Test: `tests/orchestration/test_worker.py`
- Test: `tests/orchestration/test_recovery.py`

- [ ] **Step 1: Write failing retry and recovery tests**

Create `tests/orchestration/test_worker.py`:

```python
from dataclasses import dataclass

from backend.orchestration.worker import DurableWorker, StepExecutionError


@dataclass
class AlwaysFails:
    repository: object
    calls: int = 0

    def run_next(self, job, cancel_requested):
        self.calls += 1
        with self.repository.database.transaction() as conn:
            conn.execute(
                """UPDATE job_steps SET status='running' WHERE id=(
                    SELECT id FROM job_steps WHERE job_id=? AND status IN ('queued','running')
                    ORDER BY sequence LIMIT 1
                )""",
                (job["id"],),
            )
        raise StepExecutionError("COMFY_NODE_MISSING", "missing node")

    def cancel(self, job_id):
        return True


def test_worker_stops_on_failed_step_after_three_retries(job_repo, queued_job):
    runner = AlwaysFails(job_repo)
    worker = DurableWorker(job_repo, runner, retry_delays=[0, 0, 0])
    for _ in range(4):
        worker.run_once()
    job = job_repo.get_job(queued_job["id"])
    assert runner.calls == 4
    assert job["status"] == "failed"
    assert job["steps"][0]["attempt"] == 4
```

Create `tests/orchestration/test_recovery.py`:

```python
def test_expired_running_job_is_requeued_without_resetting_completed_steps(job_repo, running_job):
    recovered = job_repo.recover_expired_leases(now="2099-01-01T00:00:00+00:00")
    job = job_repo.get_job(running_job["id"])
    assert recovered == 1
    assert job["status"] == "queued"
    assert job["steps"][0]["status"] == "completed"
```

Create `tests/orchestration/conftest.py`:

```python
import uuid

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository, utcnow
from backend.orchestration.schemas import JobCreate


@pytest.fixture
def job_repo(tmp_path):
    return JobRepository(OrchestrationDatabase(tmp_path / "orchestration.db"))


def create_job(repo, key):
    return repo.create_job(JobCreate(
        project_id=key,
        input_path="input.txt",
        input_type="novel",
        shot_duration=5,
        width=1080,
        height=1920,
        idempotency_key=f"request-{key}",
    ))


@pytest.fixture
def queued_job(job_repo):
    job = create_job(job_repo, "queued")
    with job_repo.database.transaction() as conn:
        conn.execute(
            """INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status)
               VALUES(?, ?, 0, 'input_parse', '', 'running')""",
            (str(uuid.uuid4()), job["id"]),
        )
    return job


@pytest.fixture
def running_job(job_repo):
    job = create_job(job_repo, "running")
    with job_repo.database.transaction() as conn:
        conn.execute(
            """UPDATE jobs SET status='running', worker_id='dead-worker',
               lease_until='2000-01-01T00:00:00+00:00' WHERE id=?""",
            (job["id"],),
        )
        conn.execute(
            """INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status, finished_at)
               VALUES(?, ?, 0, 'input_parse', '', 'completed', ?)""",
            (str(uuid.uuid4()), job["id"], utcnow()),
        )
        conn.execute(
            """INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status)
               VALUES(?, ?, 1, 'script_plan', '', 'running')""",
            (str(uuid.uuid4()), job["id"]),
        )
    return job
```

- [ ] **Step 2: Run the worker tests and verify failure**

```powershell
python -m pytest tests/orchestration/test_worker.py tests/orchestration/test_recovery.py -q
```

Expected: FAIL because the worker and lease methods do not exist.

- [ ] **Step 3: Add repository lease and failure methods**

Add these transactional methods to `JobRepository`:

```python
def claim_next(self, worker_id: str, now: str, lease_until: str):
    claimed_id = None
    with self.database.transaction() as conn:
        row = conn.execute(
            """SELECT id FROM jobs
               WHERE status='queued' OR (status='retry_wait' AND run_after<=?)
               ORDER BY created_at LIMIT 1""",
            (now,),
        ).fetchone()
        if not row:
            return None
        changed = conn.execute(
            """UPDATE jobs SET status='running', worker_id=?, lease_until=?, updated_at=?
               WHERE id=? AND (status='queued' OR (status='retry_wait' AND run_after<=?))""",
            (worker_id, lease_until, utcnow(), row["id"], now),
        ).rowcount
        claimed_id = row["id"] if changed else None
    return self.get_job(claimed_id) if claimed_id else None

def recover_expired_leases(self, now: str) -> int:
    with self.database.transaction() as conn:
        return conn.execute(
            """UPDATE jobs SET status='queued', worker_id=NULL, lease_until=NULL,
               message='从中断检查点恢复', updated_at=?
               WHERE status='running' AND lease_until IS NOT NULL AND lease_until < ?""",
            (utcnow(), now),
        ).rowcount

def fail_or_retry_step(
    self, job_id: str, step_id: str, code: str, message: str,
    max_retries: int, retry_at: str | None,
):
    with self.database.transaction() as conn:
        step = conn.execute("SELECT attempt FROM job_steps WHERE id=?", (step_id,)).fetchone()
        job = conn.execute("SELECT desired_state FROM jobs WHERE id=?", (job_id,)).fetchone()
        attempt = int(step["attempt"]) + 1
        exhausted = attempt > max_retries
        step_status = "failed" if exhausted else "retry_wait"
        job_status = "failed" if exhausted else (
            "paused" if job["desired_state"] == "paused" else "retry_wait"
        )
        conn.execute(
            "UPDATE job_steps SET attempt=?, status=?, error_code=?, error_message=? WHERE id=?",
            (attempt, step_status, code, message, step_id),
        )
        conn.execute(
            """UPDATE jobs SET status=?, message=?, run_after=?, worker_id=NULL,
               lease_until=NULL, updated_at=? WHERE id=?""",
            (job_status, message, retry_at if job_status == "retry_wait" else None, utcnow(), job_id),
        )
        return exhausted, attempt
```

- [ ] **Step 4: Implement one-iteration worker logic**

Create `backend/orchestration/worker.py`:

```python
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol


class StepExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class StepRunner(Protocol):
    def run_next(self, job: dict, cancel_requested: Callable[[], bool]):
        raise NotImplementedError

    def cancel(self, job_id: str) -> bool:
        raise NotImplementedError


class DurableWorker:
    def __init__(self, repository, runner: StepRunner, retry_delays=None, lease_seconds=30):
        self.repository = repository
        self.runner = runner
        self.retry_delays = retry_delays or [5, 15, 45]
        self.lease_seconds = lease_seconds
        self.worker_id = str(uuid.uuid4())
        self._stop = threading.Event()

    def run_once(self) -> bool:
        now = datetime.now(timezone.utc)
        self.repository.recover_expired_leases(now.isoformat())
        job = self.repository.claim_next(
            self.worker_id,
            now.isoformat(),
            (now + timedelta(seconds=self.lease_seconds)).isoformat(),
        )
        if not job:
            return False
        try:
            outcome = self.runner.run_next(
                job,
                lambda: self.repository.is_cancel_requested(job["id"]),
            )
            if outcome is not None:
                self.repository.apply_step_outcome(job["id"], outcome)
        except StepExecutionError as error:
            if self.repository.is_cancel_requested(job["id"]):
                self.repository.finalize_cancel(job["id"])
                return True
            step_id = self.repository.current_step_id(job["id"])
            current = self.repository.get_job(job["id"])
            attempt = int(next(step for step in current["steps"] if step["id"] == step_id)["attempt"]) + 1
            delay = self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)]
            retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            exhausted, attempt = self.repository.fail_or_retry_step(
                job["id"], step_id, error.code, str(error), len(self.retry_delays), retry_at
            )
        return True

    def serve(self, poll_seconds: float = 0.5) -> None:
        while not self._stop.is_set():
            if not self.run_once():
                self._stop.wait(poll_seconds)

    def stop(self) -> None:
        self._stop.set()
```

Add the worker helpers to `JobRepository`:

```python
def is_cancel_requested(self, job_id: str) -> bool:
    with self.database.connect() as conn:
        row = conn.execute("SELECT desired_state FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row["desired_state"] == "cancelled")

def finalize_cancel(self, job_id: str) -> None:
    with self.database.transaction() as conn:
        conn.execute(
            """UPDATE job_steps SET status='cancelled'
               WHERE job_id=? AND status IN ('pending','queued','running','retry_wait')""",
            (job_id,),
        )
        conn.execute(
            """UPDATE jobs SET status='cancelled', message='已取消', run_after=NULL,
               worker_id=NULL, lease_until=NULL, updated_at=? WHERE id=?""",
            (utcnow(), job_id),
        )

def current_step_id(self, job_id: str) -> str:
    with self.database.connect() as conn:
        row = conn.execute(
            """SELECT id FROM job_steps WHERE job_id=?
               AND status IN ('running', 'retry_wait', 'failed')
               ORDER BY sequence LIMIT 1""",
            (job_id,),
        ).fetchone()
        if not row:
            raise LookupError(f"job {job_id} has no active step")
        return str(row["id"])

def apply_step_outcome(self, job_id: str, outcome) -> None:
    self.complete_step(job_id, outcome.step_id, outcome.input_hash, outcome.artifacts)
    with self.database.transaction() as conn:
        job = conn.execute("SELECT mode, desired_state FROM jobs WHERE id=?", (job_id,)).fetchone()
        target = "cancelled" if job["desired_state"] == "cancelled" else (
            "paused" if job["desired_state"] == "paused" else (
                "waiting_review" if job["mode"] == "manual_review" else "queued"
            )
        )
        conn.execute(
            """UPDATE jobs SET status=?, progress=?, message=?, final_video=?, run_after=NULL,
               worker_id=NULL, lease_until=NULL, updated_at=? WHERE id=?""",
            (target, outcome.progress, outcome.message, outcome.final_video, utcnow(), job_id),
        )

def ensure_bootstrap_step(self, job_id: str) -> str:
    import uuid
    with self.database.transaction() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO job_steps(
                id, job_id, sequence, stage_key, shot_id, status
            ) VALUES(?, ?, 0, 'input_parse', '', 'pending')""",
            (str(uuid.uuid4()), job_id),
        )
        row = conn.execute(
            "SELECT id FROM job_steps WHERE job_id=? AND sequence=0 AND shot_id=''",
            (job_id,),
        ).fetchone()
        conn.execute(
            "UPDATE job_steps SET status='running', started_at=? WHERE id=?",
            (utcnow(), row["id"]),
        )
        return str(row["id"])
```

- [ ] **Step 5: Run retry and recovery tests**

```powershell
python -m pytest tests/orchestration/test_worker.py tests/orchestration/test_recovery.py -q
```

Expected: all worker and recovery tests pass; the fake runner is called four times (initial attempt plus three retries), and completed checkpoints remain completed.

- [ ] **Step 6: Commit durable execution**

```powershell
git add backend/orchestration tests/orchestration
git commit -m "feat: recover and retry durable pipeline jobs"
```

### Task 6: Expose job commands and event streaming

**Files:**
- Create: `backend/orchestration/service.py`
- Create: `backend/routes/jobs.py`
- Test: `tests/api/test_jobs_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/api/test_jobs_api.py`:

```python
def test_current_job_survives_new_test_client(app_factory):
    first = app_factory()
    created = first.post("/api/jobs", json={
        "project_id": "p1",
        "input_path": "input.txt",
        "input_type": "novel",
        "mode": "automatic",
        "shot_duration": 5,
        "width": 1080,
        "height": 1920,
        "fps": 24,
        "options": {},
        "idempotency_key": "browser-request-0001",
    }).json()
    second = app_factory()
    restored = second.get("/api/jobs/current").json()
    assert restored["id"] == created["id"]


def test_retry_keeps_completed_steps_and_requeues_failed_step(client, failed_job):
    response = client.post(f"/api/jobs/{failed_job['id']}/retry", json={"step_id": failed_job["failed_step_id"]})
    assert response.status_code == 200
    restored = client.get(f"/api/jobs/{failed_job['id']}").json()
    assert restored["status"] == "queued"
    assert restored["steps"][0]["status"] == "completed"


def test_rollback_preview_and_confirmation_use_the_same_exact_step_ids(client, failed_job):
    preview = client.get(
        f"/api/jobs/{failed_job['id']}/rollback-preview",
        params={"step_id": failed_job["completed_step_id"]},
    ).json()
    expected = [failed_job["completed_step_id"], failed_job["failed_step_id"]]
    assert preview["invalidated_step_ids"] == expected
    restored = client.post(f"/api/jobs/{failed_job['id']}/rollback", json={
        "step_id": failed_job["completed_step_id"],
        "confirm_invalidated_step_ids": expected,
    }).json()
    assert restored["status"] == "queued"
    assert [step["status"] for step in restored["steps"]] == ["queued", "queued"]
```

Create `tests/api/conftest.py` so both clients share the same SQLite file:

```python
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate
from backend.orchestration.service import JobService
from backend.routes.jobs import router


@pytest.fixture
def api_database_path(tmp_path):
    return tmp_path / "api.db"


@pytest.fixture
def app_factory(api_database_path):
    def factory():
        app = FastAPI()
        repository = JobRepository(OrchestrationDatabase(api_database_path))
        runner = SimpleNamespace(cancel=lambda job_id: True)
        app.state.job_service = JobService(repository, runner)
        app.include_router(router)
        return TestClient(app)
    return factory


@pytest.fixture
def client(app_factory):
    return app_factory()


@pytest.fixture
def failed_job(client):
    service = client.app.state.job_service
    job = service.create(JobCreate(
        project_id="failed", input_path="input.txt", input_type="novel",
        shot_duration=5, width=1080, height=1920,
        idempotency_key="failed-request-0001",
    ))
    first_id, failed_id = str(uuid.uuid4()), str(uuid.uuid4())
    with service.repository.database.transaction() as conn:
        conn.execute("UPDATE jobs SET status='failed' WHERE id=?", (job["id"],))
        conn.execute(
            "INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status) VALUES(?, ?, 0, 'input_parse', '', 'completed')",
            (first_id, job["id"]),
        )
        conn.execute(
            "INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status) VALUES(?, ?, 1, 'script_plan', '', 'failed')",
            (failed_id, job["id"]),
        )
    return {**job, "completed_step_id": first_id, "failed_step_id": failed_id}
```

- [ ] **Step 2: Run the API tests and verify routes are missing**

```powershell
python -m pytest tests/api/test_jobs_api.py -q
```

Expected: FAIL with 404 responses.

- [ ] **Step 3: Implement application commands**

Create `backend/orchestration/service.py`:

```python
class JobService:
    def __init__(self, repository, runner):
        self.repository = repository
        self.runner = runner

    def create(self, command):
        created = self.repository.create_job(command)
        return self.repository.get_job(created["id"])

    def current(self):
        return self.repository.get_current_job()

    def get(self, job_id):
        return self.repository.get_job(job_id)

    def list(self, limit=50, offset=0):
        return self.repository.list_jobs(limit, offset)

    def pause(self, job_id):
        return self.repository.request_state(job_id, "paused")

    def resume(self, job_id):
        return self.repository.resume_job(job_id)

    def retry(self, job_id, step_id=None):
        return self.repository.retry_failed_step(job_id, step_id)

    def cancel(self, job_id):
        self.repository.request_state(job_id, "cancelled")
        self.runner.cancel(job_id)
        return self.repository.get_job(job_id)

    def rollback(self, job_id, step_id, confirmed):
        affected = [step_id, *self.repository.downstream_step_ids(job_id, step_id)]
        if affected != confirmed:
            raise ValueError("rollback confirmation does not match affected steps")
        self.repository.invalidate_steps(job_id, affected)
        return self.repository.resume_job(job_id)

    def rollback_preview(self, job_id, step_id):
        return {
            "step_id": step_id,
            "invalidated_step_ids": [step_id, *self.repository.downstream_step_ids(job_id, step_id)],
        }

    def review(self, job_id, step_id, action, comment, patch):
        return self.repository.record_review(job_id, step_id, action, comment, patch)
```

Add the service command methods to `JobRepository`:

```python
def request_state(self, job_id: str, desired: str):
    with self.database.transaction() as conn:
        current = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not current:
            raise ValueError("job not found")
        target = "cancelled" if desired == "cancelled" else (
            current["status"] if current["status"] == "running" else "paused"
        )
        message = "已取消" if desired == "cancelled" else (
            "当前步骤完成后暂停" if target == "running" else "已暂停"
        )
        conn.execute(
            "UPDATE jobs SET desired_state=?, status=?, message=?, updated_at=? WHERE id=?",
            (desired, target, message, utcnow(), job_id),
        )
        if target == "cancelled":
            conn.execute(
                "UPDATE job_steps SET status='cancelled' WHERE job_id=? AND status IN ('pending','queued','running','retry_wait')",
                (job_id,),
            )
    return self.get_job(job_id)

def resume_job(self, job_id: str):
    with self.database.transaction() as conn:
        job = conn.execute("SELECT status, desired_state FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job and job["status"] == "running" and job["desired_state"] == "paused":
            conn.execute(
                "UPDATE jobs SET desired_state='running', message='继续执行', updated_at=? WHERE id=?",
                (utcnow(), job_id),
            )
        else:
            if not job or job["status"] not in ("failed", "paused", "waiting_review", "retry_wait"):
                raise ValueError("job is not resumable")
            conn.execute(
                "UPDATE job_steps SET status='queued', error_code='', error_message='' WHERE job_id=? AND status IN ('failed','retry_wait')",
                (job_id,),
            )
            conn.execute(
                """UPDATE jobs SET status='queued', desired_state='running', message='继续执行', run_after=NULL,
                   worker_id=NULL, lease_until=NULL, updated_at=? WHERE id=?""",
                (utcnow(), job_id),
            )
    return self.get_job(job_id)

def retry_failed_step(self, job_id: str, step_id: str | None):
    with self.database.transaction() as conn:
        if step_id:
            row = conn.execute(
                "SELECT id FROM job_steps WHERE id=? AND job_id=? AND status='failed'",
                (step_id, job_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM job_steps WHERE job_id=? AND status='failed' ORDER BY sequence, shot_id LIMIT 1",
                (job_id,),
            ).fetchone()
        if not row:
            raise ValueError("failed step not found")
        conn.execute(
            "UPDATE job_steps SET status='queued', error_code='', error_message='' WHERE id=?",
            (row["id"],),
        )
        conn.execute(
            """UPDATE jobs SET status='queued', desired_state='running', message='从故障步骤继续', run_after=NULL,
               worker_id=NULL, lease_until=NULL, updated_at=? WHERE id=?""",
            (utcnow(), job_id),
        )
    return self.get_job(job_id)

def downstream_step_ids(self, job_id: str, step_id: str):
    with self.database.connect() as conn:
        selected = conn.execute("SELECT sequence, shot_id FROM job_steps WHERE id=? AND job_id=?", (step_id, job_id)).fetchone()
        if not selected:
            raise ValueError("step not found")
        return [row["id"] for row in conn.execute(
            """SELECT id FROM job_steps
               WHERE job_id=? AND sequence>?
                 AND (?='' OR shot_id=? OR shot_id='')
               ORDER BY sequence, shot_id""",
            (job_id, selected["sequence"], selected["shot_id"], selected["shot_id"]),
        )]

def invalidate_steps(self, job_id: str, step_ids: list[str]):
    if not step_ids:
        return
    marks = ",".join("?" for _ in step_ids)
    with self.database.transaction() as conn:
        conn.execute(
            f"UPDATE job_steps SET status='invalidated' WHERE job_id=? AND id IN ({marks})",
            (job_id, *step_ids),
        )
        conn.execute(
            f"UPDATE artifacts SET active=0 WHERE job_id=? AND step_id IN ({marks})",
            (job_id, *step_ids),
        )
        conn.execute(
            f"UPDATE job_steps SET status='queued' WHERE job_id=? AND id IN ({marks})",
            (job_id, *step_ids),
        )

def record_review(self, job_id, step_id, action, comment, patch):
    import json
    import uuid
    with self.database.transaction() as conn:
        conn.execute(
            """INSERT INTO review_actions(id, job_id, step_id, action, comment, patch_json, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), job_id, step_id, action, comment, json.dumps(patch, ensure_ascii=False), utcnow()),
        )
        if action == "approve":
            conn.execute("UPDATE jobs SET status='queued', desired_state='running', updated_at=? WHERE id=?", (utcnow(), job_id))
        elif action in ("retry", "edit"):
            if action == "edit" and patch:
                job_row = conn.execute("SELECT settings_json FROM jobs WHERE id=?", (job_id,)).fetchone()
                settings = json.loads(job_row["settings_json"])
                options_patch = patch.get("options", {})
                for key in ("shot_duration", "width", "height", "fps"):
                    if key in patch:
                        settings[key] = patch[key]
                settings.setdefault("options", {}).update(options_patch)
                settings = JobCreate.model_validate(settings).model_dump(mode="json")
                conn.execute(
                    "UPDATE jobs SET settings_json=? WHERE id=?",
                    (json.dumps(settings, ensure_ascii=False), job_id),
                )
            conn.execute("UPDATE artifacts SET active=0 WHERE step_id=?", (step_id,))
            conn.execute("UPDATE job_steps SET status='queued', input_hash='' WHERE id=?", (step_id,))
            conn.execute("UPDATE jobs SET status='queued', desired_state='running', updated_at=? WHERE id=?", (utcnow(), job_id))
        elif action == "rollback":
            raise ValueError("use rollback preview and confirmation endpoint")
    return self.get_job(job_id)
```

- [ ] **Step 4: Implement REST and SSE routes**

Create `backend/routes/jobs.py`:

```python
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.orchestration.schemas import JobAction, JobCreate, ReviewAction, RollbackAction

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


def service(request: Request):
    return request.app.state.job_service


def command(operation):
    try:
        return operation()
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("")
def create_job(command: JobCreate, request: Request):
    return service(request).create(command)


@router.get("/current")
def current_job(request: Request):
    return service(request).current()


@router.get("")
def list_jobs(request: Request, limit: int = 50, offset: int = 0):
    return {"items": service(request).list(limit, offset)}


@router.get("/{job_id}")
def get_job(job_id: str, request: Request):
    job = service(request).get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.post("/{job_id}/pause")
def pause_job(job_id: str, request: Request):
    return command(lambda: service(request).pause(job_id))


@router.post("/{job_id}/resume")
def resume_job(job_id: str, request: Request):
    return command(lambda: service(request).resume(job_id))


@router.post("/{job_id}/retry")
def retry_job(job_id: str, action: JobAction, request: Request):
    return command(lambda: service(request).retry(job_id, action.step_id))


@router.post("/{job_id}/rollback")
def rollback_job(job_id: str, action: RollbackAction, request: Request):
    return command(lambda: service(request).rollback(job_id, action.step_id, action.confirm_invalidated_step_ids))


@router.get("/{job_id}/rollback-preview")
def rollback_preview(job_id: str, step_id: str, request: Request):
    return command(lambda: service(request).rollback_preview(job_id, step_id))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    return service(request).cancel(job_id)


@router.post("/{job_id}/steps/{step_id}/review")
def review_step(job_id: str, step_id: str, action: ReviewAction, request: Request):
    return command(lambda: service(request).review(job_id, step_id, action.action, action.comment, action.patch))


@router.get("/{job_id}/events")
async def stream_events(job_id: str, request: Request):
    async def events():
        event_id = 0
        previous = ""
        while not await request.is_disconnected():
            job = service(request).get(job_id)
            if job is None:
                yield "event: gone\ndata: {}\n\n"
                return
            payload = json.dumps(job, ensure_ascii=False, sort_keys=True)
            if payload != previous:
                event_id += 1
                previous = payload
                yield f"id: {event_id}\nevent: job\ndata: {payload}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type="text/event-stream")
```

The SSE stream compares the complete durable snapshot rather than relying only on in-process notifications, so every progress/status change becomes visible even after a backend restart. `job_events` remains the persistent audit log.

- [ ] **Step 5: Run API tests**

```powershell
python -m pytest tests/api/test_jobs_api.py -q
```

Expected: current-job restoration and failed-step retry tests pass.

- [ ] **Step 6: Commit the durable API**

```powershell
git add backend/orchestration/service.py backend/routes/jobs.py tests/api/test_jobs_api.py
git commit -m "feat: expose durable job control API"
```

### Task 7: Wire lifespan and retire process-memory job state

**Files:**
- Modify: `backend/main.py:38-87`
- Modify: `backend/routes/pipeline.py:1-185`
- Test: `tests/api/test_lifespan_recovery.py`

- [ ] **Step 1: Write a failing lifespan recovery test**

Create `tests/api/test_lifespan_recovery.py`:

```python
from types import SimpleNamespace

from backend.main import create_job_runtime


class IdleRunner:
    def __init__(self, repository):
        self.repository = repository

    def run_next(self, job, cancel_requested):
        return None

    def cancel(self, job_id):
        return False


def test_runtime_recovers_expired_running_job(job_repo, running_job):
    config = SimpleNamespace(orchestration=SimpleNamespace(
        database_path=str(job_repo.database.path),
        retry_delays_seconds=[0, 0, 0],
        lease_seconds=30,
    ))
    repository, _, _ = create_job_runtime(config, runner_factory=IdleRunner)
    restored = repository.get_job(running_job["id"])
    assert restored["status"] == "queued"
    assert restored["steps"][0]["status"] == "completed"
```

- [ ] **Step 2: Run the lifespan test and verify it fails**

```powershell
python -m pytest tests/api/test_lifespan_recovery.py -q
```

Expected: FAIL because `create_job_runtime` does not exist.

- [ ] **Step 3: Wire repository, service and worker into FastAPI lifespan**

In `backend/main.py`, make runtime construction independently testable, recover leases before starting the worker, initialize it before `yield`, start one daemon worker thread, and stop/join it after `yield`:

```python
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository, utcnow
from backend.orchestration.service import JobService
from backend.orchestration.worker import DurableWorker
from backend.production.executor import ProductionStepRunner
from backend.routes.jobs import router as jobs_router


def create_job_runtime(config, runner_factory=ProductionStepRunner):
    database = OrchestrationDatabase(config.orchestration.database_path)
    repository = JobRepository(database)
    repository.recover_expired_leases(utcnow())
    repository.reconcile_checkpoints()
    runner = runner_factory(repository=repository)
    worker = DurableWorker(
        repository,
        runner,
        retry_delays=config.orchestration.retry_delays_seconds,
        lease_seconds=config.orchestration.lease_seconds,
    )
    return repository, runner, worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository, runner, worker = create_job_runtime(config)
    app.state.config = config
    app.state.job_service = JobService(repository, runner)
    worker_thread = Thread(target=worker.serve, daemon=True, name="durable-v5-worker")
    worker_thread.start()

    yield

    worker.stop()
    worker_thread.join(timeout=5)
```

Until the production plan replaces it, create `backend/production/__init__.py` as an empty package marker and `backend/production/executor.py`:

```python
from backend.orchestration.worker import StepExecutionError


class ProductionStepRunner:
    def __init__(self, repository):
        self.repository = repository

    def run_next(self, job, cancel_requested):
        if cancel_requested():
            raise StepExecutionError("USER_CANCELLED", "任务已取消")
        self.repository.ensure_bootstrap_step(job["id"])
        raise StepExecutionError("PIPELINE_NOT_READY", "production executor is not installed")

    def cancel(self, job_id: str) -> bool:
        return False
```

This runner produces an explicit failed job and never fabricates output.

Include `jobs_router` alongside existing routers:

```python
app.include_router(jobs_router, tags=["Jobs"])
```

- [ ] **Step 4: Replace legacy pipeline thread creation with service delegation**

Keep `/api/pipeline/run`, `/api/pipeline/status/{job_id}` and cancellation as compatibility endpoints, but delegate them to `JobService`. Remove `_jobs`, `threading.Thread`, `_run_pipeline_thread`, `_set_stage` and `_stage_list` from `backend/routes/pipeline.py`.

Use this request mapping:

```python
command = JobCreate(
    project_id=Path(request.novel_path).stem,
    input_path=request.novel_path,
    input_type="novel",
    mode="automatic",
    shot_duration=5,
    width=1080,
    height=1920,
    options={
        "style": request.style or "anime",
        "chapter": request.chapter,
        "max_shots": request.max_shots,
        "tts_enabled": request.tts_enabled,
        "subtitles_enabled": request.subtitles_enabled,
        "bgm_enabled": request.bgm_enabled,
    },
    idempotency_key=f"legacy-{uuid.uuid4()}",
)
return request.app.state.job_service.create(command)
```

- [ ] **Step 5: Run all orchestrator and API tests**

```powershell
python -m pytest tests/orchestration tests/api -q
```

Expected: all tests pass. A new `TestClient` restores the same job, and legacy endpoints no longer depend on process memory.

- [ ] **Step 6: Run the backend smoke check**

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8800
```

In a second terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8800/api/jobs/current
```

Expected: HTTP 200 with the current job or JSON `null`; restarting uvicorn does not erase existing jobs.

- [ ] **Step 7: Commit the lifespan integration**

```powershell
git add backend/main.py backend/routes/pipeline.py backend/production/executor.py tests/api/test_lifespan_recovery.py
git commit -m "feat: restore durable jobs on application startup"
```

## Plan verification checkpoint

Run:

```powershell
python -m pytest tests/orchestration tests/api -q
python -m pytest tests/test_pipeline_v5.py -q
```

Expected:

- all new durable-job tests pass;
- the existing focused V5 tests still run, even though the local fallback behavior will be removed in the production-pipeline plan;
- an expired `running` job is requeued after restart;
- a `failed` job stays failed until a user command requeues it;
- completed checkpoints are never reset during recovery.
