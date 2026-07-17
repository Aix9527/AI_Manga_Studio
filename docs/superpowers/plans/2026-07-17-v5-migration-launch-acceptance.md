# V5 Migration, One-Click Launch and Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely index and selectively import existing projects, provide a reliable Windows one-click launcher and environment doctor, and enforce local/CI acceptance gates for persistence, real failure handling and Web behavior.

**Architecture:** Migration is a two-phase scan/import workflow: scan is strictly read-only and import copies selected, hashed assets into a managed project directory with provenance. One Python environment doctor powers the CLI, Web health page and launcher so diagnostics stay consistent. CircleCI runs only deterministic source tests and builds; local GPU/media acceptance remains an explicit release gate.

**Tech Stack:** Python, pathlib, hashlib, FastAPI, PowerShell, pytest, npm/Vite, CircleCI 2.1, Browser/IAB

---

**Depends on:** all preceding V5 plans.

## File structure

| Path | Responsibility |
|---|---|
| `backend/migration/models.py` | Scan/import result contracts |
| `backend/migration/scanner.py` | Read-only project and asset inventory |
| `backend/migration/importer.py` | Safe copy, hashing and provenance manifest |
| `backend/routes/migrations.py` | Migration preview and import API |
| `frontend/src/pages/ImportProjects.tsx` | Non-technical X 盘/旧项目 scan and selective import UI |
| `backend/diagnostics.py` | Python, Node/npm, FFmpeg, ComfyUI, model and workflow checks |
| `backend/routes/system.py` | Diagnostics API |
| `run.py` | Cross-platform one-click launcher and `--check` |
| `run.ps1` | Windows entry point with clear status and exit codes |
| `scripts/verify_v5.py` | Unified local acceptance runner and JSON report |
| `requirements-ci.txt` | Deterministic test dependencies without local GPU runtimes |
| `.circleci/config.yml` | Deterministic backend/frontend checks with lockfile caches |
| `tests/migration/*` | Read-only, conflict and provenance tests |
| `tests/test_diagnostics.py` | Environment detection tests |
| `tests/test_launcher.py` | Windows executable resolution tests |

### Task 1: Build a strictly read-only project scanner

**Files:**
- Create: `backend/migration/__init__.py`
- Create: `backend/migration/models.py`
- Create: `backend/migration/scanner.py`
- Test: `tests/migration/test_scanner.py`

- [ ] **Step 1: Write a failing no-write scan test**

Create `tests/migration/test_scanner.py`:

```python
from backend.migration.scanner import ProjectScanner


def test_scan_hashes_assets_without_modifying_source(tmp_path):
    source = tmp_path / "legacy"
    source.mkdir()
    novel = source / "novel.txt"
    novel.write_text("第一章", encoding="utf-8")
    before = novel.stat().st_mtime_ns
    report = ProjectScanner().scan(source)
    after = novel.stat().st_mtime_ns
    assert before == after
    assert report.files[0].relative_path == "novel.txt"
    assert report.files[0].sha256
    assert sorted(path.name for path in source.iterdir()) == ["novel.txt"]


def test_scan_marks_known_local_fallback_outputs_as_untrusted(tmp_path):
    source = tmp_path / "legacy"
    path = source / "output" / "v5_local_frames" / "shot-1" / "fallback.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not production")
    report = ProjectScanner().scan(source)
    assert report.files[0].trust == "untrusted"
    assert "fallback" in report.files[0].reason.lower()
```

- [ ] **Step 2: Run the tests and verify the migration package is missing**

```powershell
python -m pytest tests/migration/test_scanner.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Define immutable scan contracts**

Create `backend/migration/__init__.py` as an empty package marker and `backend/migration/models.py`:

```python
from typing import Literal

from pydantic import BaseModel, Field


class ScannedFile(BaseModel):
    source_path: str
    relative_path: str
    kind: Literal["input", "plan", "image", "video", "audio", "workflow", "config", "other"]
    size: int
    sha256: str
    trust: Literal["candidate", "untrusted"]
    reason: str = ""


class ScanReport(BaseModel):
    source_root: str
    files: list[ScannedFile] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    total_bytes: int = 0


class ImportSelection(BaseModel):
    source_root: str
    project_id: str
    relative_paths: list[str]


class ImportReport(BaseModel):
    project_id: str
    imported: list[str] = Field(default_factory=list)
    reused: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    manifest_path: str
```

- [ ] **Step 4: Implement streaming hashes and trust classification**

Create `backend/migration/scanner.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from backend.migration.models import ScanReport, ScannedFile


SKIP_NAMES = {".git", "node_modules", "__pycache__", ".pytest_cache", "cache", "temp"}
KINDS = {
    ".txt": "input", ".md": "input", ".docx": "input",
    ".json": "plan", ".csv": "plan", ".xlsx": "plan",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
    ".mp4": "video", ".mov": "video", ".webm": "video",
    ".wav": "audio", ".mp3": "audio", ".flac": "audio",
    ".yaml": "config", ".yml": "config",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


class ProjectScanner:
    def scan(self, source_root: str | Path) -> ScanReport:
        root = Path(source_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"source is not a directory: {root}")
        files: list[ScannedFile] = []
        skipped: list[str] = []
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if any(part in SKIP_NAMES for part in relative.parts):
                if path.is_file(): skipped.append(str(relative))
                continue
            if not path.is_file():
                continue
            lower = str(relative).replace("\\", "/").lower()
            untrusted = "v5_local_frames" in lower or "fallback" in path.stem.lower()
            files.append(ScannedFile(
                source_path=str(path),
                relative_path=str(relative).replace("\\", "/"),
                kind=KINDS.get(path.suffix.lower(), "other"),
                size=path.stat().st_size,
                sha256=digest(path),
                trust="untrusted" if untrusted else "candidate",
                reason="fallback output is not accepted as production" if untrusted else "",
            ))
        return ScanReport(
            source_root=str(root),
            files=files,
            skipped=skipped,
            total_bytes=sum(item.size for item in files),
        )
```

- [ ] **Step 5: Run scanner tests and commit**

```powershell
python -m pytest tests/migration/test_scanner.py -q
git add backend/migration tests/migration/test_scanner.py
git commit -m "feat: scan legacy projects without modifying sources"
```

Expected: 2 passed; source timestamps and directory contents are unchanged.

### Task 2: Selectively import assets with provenance and conflict safety

**Files:**
- Create: `backend/migration/importer.py`
- Create: `backend/routes/migrations.py`
- Modify: `backend/main.py`
- Create: `frontend/src/pages/ImportProjects.tsx`
- Test: `tests/migration/test_importer.py`
- Test: `tests/api/test_migrations_api.py`

- [ ] **Step 1: Write failing safe-copy tests**

Create `tests/migration/test_importer.py`:

```python
from backend.migration.importer import ProjectImporter
from backend.migration.models import ImportSelection


def test_import_copies_into_managed_project_and_preserves_source(tmp_path):
    source = tmp_path / "legacy"
    source.mkdir()
    original = source / "novel.txt"
    original.write_text("original", encoding="utf-8")
    managed = tmp_path / "managed"
    report = ProjectImporter(managed).import_selection(ImportSelection(
        source_root=str(source), project_id="p1", relative_paths=["novel.txt"],
    ))
    assert original.read_text(encoding="utf-8") == "original"
    assert (managed / "p1" / "imports" / "novel.txt").read_text(encoding="utf-8") == "original"
    assert report.manifest_path.endswith("migration-manifest.json")


def test_changed_target_is_reported_as_conflict_and_not_overwritten(tmp_path):
    source = tmp_path / "legacy"; source.mkdir()
    (source / "shot.json").write_text("source", encoding="utf-8")
    target = tmp_path / "managed" / "p1" / "imports" / "shot.json"
    target.parent.mkdir(parents=True)
    target.write_text("keep-me", encoding="utf-8")
    report = ProjectImporter(tmp_path / "managed").import_selection(ImportSelection(
        source_root=str(source), project_id="p1", relative_paths=["shot.json"],
    ))
    assert target.read_text(encoding="utf-8") == "keep-me"
    assert report.conflicts == ["shot.json"]
```

- [ ] **Step 2: Run tests and verify importer is missing**

```powershell
python -m pytest tests/migration/test_importer.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Implement path-safe import and manifest writing**

Create `backend/migration/importer.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

from backend.migration.models import ImportReport, ImportSelection
from backend.migration.scanner import digest


class ProjectImporter:
    def __init__(self, managed_root: str | Path):
        self.managed_root = Path(managed_root).resolve()

    def import_selection(self, selection: ImportSelection) -> ImportReport:
        source_root = Path(selection.source_root).resolve(strict=True)
        target_root = (self.managed_root / selection.project_id / "imports").resolve()
        if self.managed_root not in target_root.parents:
            raise ValueError("project_id escapes the managed project root")
        target_root.mkdir(parents=True, exist_ok=True)
        imported: list[str] = []
        reused: list[str] = []
        conflicts: list[str] = []
        skipped: list[str] = []
        entries: list[dict] = []
        for raw_relative in selection.relative_paths:
            relative = Path(raw_relative)
            source = (source_root / relative).resolve(strict=True)
            if source_root not in source.parents or not source.is_file():
                skipped.append(raw_relative)
                continue
            target = (target_root / relative).resolve()
            if target_root not in target.parents:
                skipped.append(raw_relative)
                continue
            source_hash = digest(source)
            if target.exists():
                if target.is_file() and digest(target) == source_hash:
                    reused.append(raw_relative)
                else:
                    conflicts.append(raw_relative)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if digest(target) != source_hash:
                target.unlink(missing_ok=True)
                raise IOError(f"hash mismatch after copy: {relative}")
            imported.append(raw_relative)
            entries.append({"source": str(source), "target": str(target), "sha256": source_hash})
        manifest = target_root.parent / "migration-manifest.json"
        manifest.write_text(json.dumps({
            "source_root": str(source_root), "project_id": selection.project_id,
            "entries": entries, "imported": imported, "reused": reused,
            "conflicts": conflicts, "skipped": skipped,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return ImportReport(
            project_id=selection.project_id, imported=imported, reused=reused,
            conflicts=conflicts, skipped=skipped, manifest_path=str(manifest),
        )
```

- [ ] **Step 4: Add scan and import APIs**

Create `backend/routes/migrations.py`:

```python
from pathlib import Path

from fastapi import APIRouter, Request

from backend.migration.importer import ProjectImporter
from backend.migration.models import ImportSelection
from backend.migration.scanner import ProjectScanner

router = APIRouter(prefix="/api/migrations", tags=["Migrations"])


@router.post("/scan")
def scan(source_root: str):
    return ProjectScanner().scan(source_root)


@router.post("/import")
def import_selection(selection: ImportSelection, request: Request):
    managed = Path(request.app.state.config.project.root_path)
    return ProjectImporter(managed).import_selection(selection)
```

Include this router in `backend/main.py`. Write `tests/api/test_migrations_api.py` to assert `/scan` returns candidates but creates no source files, and `/import` only copies selected relative paths.

- [ ] **Step 5: Add the X 盘 selective-import page**

Create `frontend/src/pages/ImportProjects.tsx` and add route `/imports` to the app shell:

```tsx
import {Alert, Button, Checkbox, Input, List, Space, Typography} from "antd";
import {useState} from "react";

type ScannedFile = {relative_path: string; kind: string; size: number; trust: "candidate" | "untrusted"; reason: string};

export function ImportProjects() {
  const [source, setSource] = useState("X:\\");
  const [projectId, setProjectId] = useState("");
  const [files, setFiles] = useState<ScannedFile[]>([]);
  const [selected, setSelected] = useState<string[]>([]);

  const scan = async () => {
    const response = await fetch(`/api/migrations/scan?source_root=${encodeURIComponent(source)}`, {method: "POST"});
    if (!response.ok) throw new Error(await response.text());
    const report = await response.json();
    setFiles(report.files);
    setSelected(report.files.filter((file: ScannedFile) => file.trust === "candidate").map((file: ScannedFile) => file.relative_path));
  };

  const importSelected = async () => {
    const response = await fetch("/api/migrations/import", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({source_root: source, project_id: projectId, relative_paths: selected}),
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  };

  return <main>
    <Typography.Title level={2}>导入旧项目</Typography.Title>
    <Alert type="info" showIcon message="扫描不会修改 X 盘或原项目；导入只复制你勾选的内容。" />
    <Space.Compact block>
      <Input aria-label="来源目录" value={source} onChange={(event) => setSource(event.target.value)} />
      <Button onClick={() => void scan()}>只读扫描</Button>
    </Space.Compact>
    <Input aria-label="新项目名称" value={projectId} onChange={(event) => setProjectId(event.target.value)} />
    <Checkbox.Group value={selected} onChange={(values) => setSelected(values as string[])}>
      <List dataSource={files} renderItem={(file) => <List.Item>
        <Checkbox value={file.relative_path} disabled={file.trust === "untrusted"}>{file.relative_path}</Checkbox>
        {file.trust === "untrusted" ? <Alert type="warning" message={file.reason} /> : null}
      </List.Item>} />
    </Checkbox.Group>
    <Button type="primary" disabled={!projectId || selected.length === 0} onClick={() => void importSelected()}>导入所选内容</Button>
  </main>;
}
```

Create `frontend/src/pages/ImportProjects.test.tsx`:

```tsx
import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, it, vi} from "vitest";

import {ImportProjects} from "./ImportProjects";

it("selects trusted X drive assets and disables fallback outputs", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({files: [
    {relative_path: "images/shot.png", kind: "image", size: 10, trust: "candidate", reason: ""},
    {relative_path: "output/v5_local_frames/fallback.mp4", kind: "video", size: 10, trust: "untrusted", reason: "fallback output is not accepted as production"},
  ]}), {status: 200, headers: {"Content-Type": "application/json"}}));
  render(<ImportProjects />);
  await userEvent.click(screen.getByRole("button", {name: "只读扫描"}));
  expect(screen.getByRole("checkbox", {name: "images/shot.png"})).toBeChecked();
  expect(screen.getByRole("checkbox", {name: "output/v5_local_frames/fallback.mp4"})).toBeDisabled();
});
```

- [ ] **Step 6: Run migration tests and commit**

```powershell
python -m pytest tests/migration tests/api/test_migrations_api.py -q
Push-Location frontend
npm test -- src/pages/ImportProjects.test.tsx
Pop-Location
git add backend/migration backend/routes/migrations.py backend/main.py tests/migration tests/api/test_migrations_api.py frontend/src/pages/ImportProjects.tsx frontend/src/pages/ImportProjects.test.tsx frontend/src/App.tsx
git commit -m "feat: safely import selected legacy project assets"
```

Expected: all migration tests pass; conflicts never overwrite target files.

### Task 3: Create one environment doctor for CLI and Web

**Files:**
- Create: `backend/diagnostics.py`
- Create: `backend/routes/system.py`
- Modify: `backend/main.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: Write failing Windows npm and ComfyUI checks**

Create `tests/test_diagnostics.py`:

```python
from backend.diagnostics import EnvironmentDoctor


def test_windows_prefers_npm_cmd(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("shutil.which", lambda name: "C:/node/npm.cmd" if name == "npm.cmd" else None)
    assert EnvironmentDoctor().npm_executable() == "C:/node/npm.cmd"


def test_missing_comfyui_is_a_blocking_production_failure(monkeypatch):
    doctor = EnvironmentDoctor()
    monkeypatch.setattr(doctor, "check_comfyui", lambda: {"ok": False, "detail": "connection refused", "blocking": True})
    report = doctor.run()
    assert report["ready"] is False
    assert report["checks"]["comfyui"]["blocking"] is True
```

- [ ] **Step 2: Run the tests and verify diagnostics are missing**

```powershell
python -m pytest tests/test_diagnostics.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Implement executable and production dependency checks**

Create `backend/diagnostics.py`:

```python
from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from backend.comfyui_client import ComfyUIClient
from backend.config import get_config


class EnvironmentDoctor:
    def npm_executable(self) -> str | None:
        preferred = "npm.cmd" if platform.system() == "Windows" else "npm"
        return shutil.which(preferred) or shutil.which("npm")

    def executable(self, name: str) -> dict:
        path = shutil.which(name)
        return {"ok": bool(path), "detail": path or f"{name} not found", "blocking": True}

    def check_comfyui(self) -> dict:
        ok, detail = ComfyUIClient().check_connection()
        return {"ok": ok, "detail": detail, "blocking": True}

    def check_workflows(self) -> dict:
        root = Path(get_config().paths.workflow)
        required = [root / "templates" / "image_gen.json", root / "templates" / "i2v_gen.json"]
        missing = [str(path) for path in required if not path.is_file()]
        return {"ok": not missing, "detail": "ready" if not missing else f"missing: {missing}", "blocking": True}

    def run(self) -> dict:
        npm = self.npm_executable()
        checks = {
            "python": {"ok": True, "detail": platform.python_version(), "blocking": True},
            "node": self.executable("node"),
            "npm": {"ok": bool(npm), "detail": npm or "npm not found", "blocking": True},
            "ffmpeg": self.executable("ffmpeg"),
            "ffprobe": self.executable("ffprobe"),
            "comfyui": self.check_comfyui(),
            "workflows": self.check_workflows(),
        }
        return {"ready": all(item["ok"] for item in checks.values() if item["blocking"]), "checks": checks}
```

- [ ] **Step 4: Add a diagnostics API**

Create `backend/routes/system.py`:

```python
from fastapi import APIRouter

from backend.diagnostics import EnvironmentDoctor

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/diagnostics")
def diagnostics():
    return EnvironmentDoctor().run()
```

Include `system.router` in `backend/main.py`.

- [ ] **Step 5: Run diagnostics tests and commit**

```powershell
python -m pytest tests/test_diagnostics.py -q
git add backend/diagnostics.py backend/routes/system.py backend/main.py tests/test_diagnostics.py
git commit -m "feat: add production environment diagnostics"
```

Expected: Windows selects `npm.cmd`; missing ComfyUI or FFmpeg prevents production-ready status.

### Task 4: Repair the one-click Windows launcher

**Files:**
- Modify: `run.py:40-180,350-430`
- Replace: `run.ps1`
- Test: `tests/test_launcher.py`

- [ ] **Step 1: Write a failing command-resolution test**

Create `tests/test_launcher.py`:

```python
from run import command_for


def test_command_for_uses_cmd_shim_on_windows(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("shutil.which", lambda name: f"C:/bin/{name}" if name == "npm.cmd" else None)
    assert command_for("npm") == "C:/bin/npm.cmd"
```

- [ ] **Step 2: Run the test and reproduce the current failure**

```powershell
python -m pytest tests/test_launcher.py -q
python run.py --check
```

Expected: the unit test fails because `command_for` is missing; the current check incorrectly reports npm missing even when `npm.cmd --version` works.

- [ ] **Step 3: Implement cross-platform executable resolution**

Add to `run.py` and use it for every Node/npm subprocess:

```python
import platform
import shutil


def command_for(name: str) -> str:
    candidates = [f"{name}.cmd", name] if platform.system() == "Windows" else [name]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError(f"{name} not found")
```

Replace the three npm command arrays in `check_environment`, dependency installation and `start_frontend` so their first element is `command_for("npm")`. Make `--check` call `EnvironmentDoctor().run()` and exit 0 only when `ready` is true.

- [ ] **Step 4: Replace the PowerShell entry point**

Replace `run.ps1` with:

```powershell
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

python run.py --check
if ($LASTEXITCODE -ne 0) {
  Write-Host '环境检查未通过。请根据上方故障项修复后重试。' -ForegroundColor Red
  exit $LASTEXITCODE
}

python run.py --web
exit $LASTEXITCODE
```

`run.py --web` starts backend and frontend with hidden child windows, waits for `/health` and `http://localhost:3000`, prints both URLs, and terminates both child processes on Ctrl+C.

- [ ] **Step 5: Run launcher tests and smoke check**

```powershell
python -m pytest tests/test_launcher.py tests/test_diagnostics.py -q
python run.py --check
```

Expected: tests pass. The environment report names the actual missing dependency, and npm is detected through `npm.cmd` on Windows.

- [ ] **Step 6: Commit the launcher repair**

```powershell
git add run.py run.ps1 tests/test_launcher.py
git commit -m "fix: make one-click launcher reliable on Windows"
```

### Task 5: Add deterministic CircleCI source gates

**Files:**
- Create: `requirements-ci.txt`
- Create: `.circleci/config.yml`

- [ ] **Step 1: Establish the CI baseline and scope**

Document this baseline in the commit body:

```text
Current state: no CircleCI configuration; no historical job duration or flake data.
Initial scope: backend unit/integration tests using fake adapters, and frontend
typecheck/lint/test/build. Real GPU, ComfyUI models and media generation stay local.
```

- [ ] **Step 2: Separate deterministic CI dependencies from local GPU runtimes**

Create `requirements-ci.txt`:

```text
fastapi>=0.110.0,<0.200.0
uvicorn>=0.29.0,<1.0.0
pydantic>=2.6.0,<3.0.0
sqlalchemy>=2.0.0,<3.0.0
requests>=2.31.0,<3.0.0
httpx>=0.26.0,<1.0.0
pyyaml>=6.0,<7.0
loguru>=0.7.0,<1.0.0
Pillow>=10.0.0,<11.0.0
numpy>=1.26.0,<2.0.0
imageio>=2.34.0,<3.0.0
imageio-ffmpeg>=0.4.9,<1.0.0
psutil>=5.9.0,<6.0.0
rich>=13.0.0,<14.0.0
python-multipart>=0.0.9
python-docx>=1.1.0,<2.0.0
openpyxl>=3.1.0,<4.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

The local `requirements.txt` remains the production environment and still includes GPU/media packages. CI imports external model calls only through deterministic fakes.

- [ ] **Step 3: Create a two-job CircleCI workflow**

Create `.circleci/config.yml`:

```yaml
version: 2.1

jobs:
  backend-test:
    docker:
      - image: cimg/python:3.12
    steps:
      - checkout
      - run:
          name: Install FFmpeg validation runtime
          command: sudo apt-get update && sudo apt-get install -y ffmpeg
      - restore_cache:
          keys:
            - v1-pip-py312-{{ checksum "requirements-ci.txt" }}
      - run:
          name: Install Python dependencies
          command: python -m pip install --cache-dir ~/.cache/pip -r requirements-ci.txt
      - save_cache:
          key: v1-pip-py312-{{ checksum "requirements-ci.txt" }}
          paths:
            - ~/.cache/pip
      - run:
          name: Run backend tests
          command: mkdir -p test-results/backend && python -m pytest -q --junitxml=test-results/backend/results.xml
      - store_test_results:
          path: test-results/backend

  frontend-test:
    docker:
      - image: cimg/node:20.15
    working_directory: ~/project/frontend
    steps:
      - checkout:
          path: ~/project
      - restore_cache:
          keys:
            - v1-npm-node20-{{ checksum "package-lock.json" }}
      - run:
          name: Install frontend dependencies
          command: npm ci
      - save_cache:
          key: v1-npm-node20-{{ checksum "package-lock.json" }}
          paths:
            - ~/.npm
      - run: npm run typecheck
      - run: npm run lint
      - run: mkdir -p test-results/frontend && npm test -- --reporter=junit --outputFile=test-results/frontend/results.xml
      - run: npm run build
      - store_test_results:
          path: test-results/frontend

workflows:
  validate-v5:
    jobs:
      - backend-test
      - frontend-test
```

The cache keys use deterministic lockfile checksums. Cache only pip and npm download stores; do not cache virtual environments, `node_modules`, build output, models or generated media.

- [ ] **Step 4: Validate YAML and local command parity**

Run:

```powershell
python -c "import yaml; yaml.safe_load(open('.circleci/config.yml', encoding='utf-8')); print('valid')"
python -m pytest -q
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

Expected: YAML prints `valid`; all local equivalents of CI steps pass.

- [ ] **Step 5: Commit the CI gate**

```powershell
git add .circleci/config.yml requirements-ci.txt
git commit -m "ci: validate backend and web console"
```

### Task 6: Create one release acceptance runner

**Files:**
- Create: `scripts/verify_v5.py`
- Test: `tests/test_verify_v5.py`

- [ ] **Step 1: Write a failing report contract test**

Create `tests/test_verify_v5.py`:

```python
from scripts.verify_v5 import summarize


def test_release_report_fails_when_any_required_gate_fails():
    report = summarize({"backend": True, "frontend": True, "restart": False, "failure_resume": True})
    assert report["passed"] is False
    assert report["failed"] == ["restart"]
```

- [ ] **Step 2: Run the test and verify the runner is missing**

```powershell
python -m pytest tests/test_verify_v5.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Implement deterministic gate execution**

Create `scripts/verify_v5.py`:

```python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], cwd: Path = ROOT) -> dict:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    return {"passed": result.returncode == 0, "command": command, "output": (result.stdout + result.stderr)[-4000:]}


def summarize(gates: dict[str, bool]) -> dict:
    failed = [name for name, passed in gates.items() if not passed]
    return {"passed": not failed, "failed": failed, "gates": gates}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="logs/v5-acceptance.json")
    args = parser.parse_args()
    checks = {
        "backend": run([sys.executable, "-m", "pytest", "-q"]),
        "frontend_typecheck": run(["npm.cmd" if sys.platform == "win32" else "npm", "run", "typecheck"], ROOT / "frontend"),
        "frontend_lint": run(["npm.cmd" if sys.platform == "win32" else "npm", "run", "lint"], ROOT / "frontend"),
        "frontend_test": run(["npm.cmd" if sys.platform == "win32" else "npm", "test"], ROOT / "frontend"),
        "frontend_build": run(["npm.cmd" if sys.platform == "win32" else "npm", "run", "build"], ROOT / "frontend"),
    }
    summary = summarize({name: item["passed"] for name, item in checks.items()})
    report = {"created_at": datetime.now(timezone.utc).isoformat(), **summary, "checks": checks}
    target = ROOT / args.report
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the report test and full runner**

```powershell
python -m pytest tests/test_verify_v5.py -q
python scripts/verify_v5.py
```

Expected: the contract test passes. The runner exits 0 only if every deterministic backend and frontend gate passes and writes `logs/v5-acceptance.json`.

- [ ] **Step 5: Commit the acceptance runner**

```powershell
git add scripts/verify_v5.py tests/test_verify_v5.py
git commit -m "test: add V5 release acceptance runner"
```

### Task 7: Perform real local release acceptance

**Files:**
- Create: `docs/acceptance/2026-07-17-v5-release-report.md`

- [ ] **Step 1: Run the deterministic suite**

```powershell
python scripts/verify_v5.py
```

Expected: exit 0 and a passing JSON report.

- [ ] **Step 2: Run a real one-shot production sample**

Start with `run.ps1`, create a one-shot 5-second project at 1080×1920 with dialogue plus a clear footstep/action cue, and keep automatic mode enabled. Verify:

```text
input parsed
real first frame exists and decodes at 1080×1920
real last frame exists and decodes at 1080×1920
real shot video decodes and is at least 5 seconds
voice WAV and lip-synced shot video both validate
SRT exists, the caption is burned into the rendered sample, and the final MP4 has an audio stream
BGM and inferred footstep SFX are present in the strict audio timeline and mix succeeds
final movie decodes and is not a copied first shot for multi-shot tests
```

- [ ] **Step 3: Run real fault and resume acceptance**

Use a copied test workflow with one required ComfyUI node name deliberately changed. Start a job and verify it retries three times, becomes `failed`, and stays on that step. Restore the valid workflow and click “修复后从本步骤继续”. Verify upstream artifact hashes do not change and only the failed step plus downstream steps execute.

- [ ] **Step 4: Run restart acceptance**

During a later shot, close backend and frontend, then run `run.ps1` again. Verify the same job ID returns, completed steps remain completed, and the interrupted job resumes from its last valid checkpoint.

- [ ] **Step 5: Run Browser/IAB Web acceptance**

Verify the approved target flow at 1440×900 and 390×844:

```text
/production -> active task -> /monitor -> /tasks -> refresh -> same task and progress
failed step -> retry controls -> workflow fixed -> current-step continuation
manual review enabled -> waiting_review -> approve -> next stage
automatic mode -> no approval pause
```

Capture DOM, console and screenshot evidence outside the repository, and compare the browser screenshots with the accepted concept using `view_image`.

- [ ] **Step 6: Write the release report**

Create `docs/acceptance/2026-07-17-v5-release-report.md` containing:

```markdown
# V5 Release Acceptance Report

- Deterministic suite: PASS/FAIL with JSON report path
- Real production sample: job ID, input, shot count, resolution, durations, final path
- Failure/resume: failed stage, retry count, preserved artifact hashes, resumed stages
- Restart recovery: job ID before/after and checkpoint comparison
- Web QA: URLs, viewports, console result, interaction path and screenshot locations
- Visual fidelity: mismatch ledger and remaining intentional deviations
- Migration safety: source root, imported count, conflict count and source hash comparison
- Release decision: PASS only when every required line above passes
```

- [ ] **Step 7: Commit evidence and final documentation**

```powershell
git add docs/acceptance/2026-07-17-v5-release-report.md
git commit -m "docs: record V5 release acceptance"
```

## Plan verification checkpoint

Release is blocked unless all conditions hold:

- deterministic backend and frontend gates pass locally;
- CircleCI configuration parses and uses lockfile-based caches only;
- migration scan does not modify source and import never overwrites conflicts;
- `run.py --check` finds Windows npm through `npm.cmd`;
- missing ComfyUI, model, node, workflow or FFmpeg is reported as blocking;
- a real 5–15 second shot and final movie pass media validation;
- fault, repair, resume and application-restart evidence proves checkpoint recovery;
- Browser/IAB proves progress survives navigation and refresh;
- accepted and implemented Web screens have no material visual mismatch after `view_image` comparison.
