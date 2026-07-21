# Unified Production Foundation Implementation Plan Amendment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the mandatory self-review corrections to `2026-07-22-unified-production-foundation.md` before executing its affected tasks.

**Architecture:** This amendment is part of the implementation plan, not an optional follow-up. It tightens URL source rights validation and ensures Windows compatibility launchers forward to the canonical durable CLI.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, PyYAML, pytest, Windows batch

## Global Constraints

- Read this amendment together with `docs/superpowers/plans/2026-07-22-unified-production-foundation.md`.
- Where this amendment names a task and file, its instructions override the corresponding base-plan fragment.
- Preserve all unrelated untracked files and reference projects.
- Do not add cloud inference or placeholder-success behavior.

---

## Amendment A: Complete the read-only legacy novel listing

**Applies to:** Base-plan Task 3, Step 3

After the compatibility endpoints shown in the base plan, add this exact endpoint to `backend/routes/pipeline.py`:

```python
@router.get("/novels")
def list_novels():
    candidates = list(NOVELS_DIR.glob("*.txt"))
    candidates.extend(PROJECT_ROOT.glob("novel*.txt"))
    novels = [
        {
            "name": item.name,
            "path": str(item.resolve()),
            "size": item.stat().st_size,
            "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
        }
        for item in sorted(set(candidates))
        if item.is_file()
    ]
    return {"total": len(novels), "novels": novels}
```

Add this test to `tests/api/test_pipeline_compat.py`:

```python
def test_legacy_novel_listing_is_read_only(tmp_path, monkeypatch):
    novels = tmp_path / "novels"
    novels.mkdir()
    story = novels / "story.txt"
    story.write_text("测试故事", encoding="utf-8")
    monkeypatch.setattr(pipeline, "NOVELS_DIR", novels)
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)
    client, _ = make_client(tmp_path / "jobs.db")

    response = client.get("/api/pipeline/novels")

    assert response.status_code == 200
    assert response.json()["novels"][0]["path"] == str(story.resolve())
    assert story.read_text(encoding="utf-8") == "测试故事"
```

Run:

```powershell
python -m pytest tests/api/test_pipeline_compat.py -q
```

Expected: all compatibility tests PASS.

## Amendment B: Require rights confirmation for URL sources

**Applies to:** Base-plan Task 4, Steps 1 and 4

Add this failing test to `tests/projects/test_repository.py` before implementing `SourceCreate`:

```python
import pytest
from pydantic import ValidationError


def test_url_source_requires_rights_confirmation():
    with pytest.raises(ValidationError, match="rights confirmation"):
        SourceCreate(
            kind="url",
            original_name="来源视频",
            original_location="https://example.invalid/video/1",
            rights_confirmed=False,
        )
```

In `backend/projects/schemas.py`, import `model_validator` and `FiniteJsonRequest`, then make `SourceCreate` validate both finite metadata and URL rights confirmation:

```python
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.orchestration.schemas import FiniteJsonRequest


class SourceCreate(FiniteJsonRequest):
    kind: Literal["idea", "document", "video", "url"]
    original_name: str = Field(min_length=1, max_length=512)
    original_location: str = Field(min_length=1, max_length=8192)
    managed_path: str = ""
    sha256: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")
    rights_confirmed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_rights_confirmation_for_url(self) -> "SourceCreate":
        if self.kind == "url" and not self.rights_confirmed:
            raise ValueError("URL sources require rights confirmation")
        return self
```

Run:

```powershell
python -m pytest tests/projects/test_repository.py -q
```

Expected: the URL validation test and all repository tests PASS.

## Amendment C: Forward Windows one-click launchers to the canonical CLI

**Applies to:** Base-plan Task 5

Add these files to Task 5:

- Modify: `一键启动.bat`
- Modify: `run.bat`

Extend `test_formal_launcher_source_does_not_spawn_historical_pipeline` in `tests/runtime/test_entrypoint.py`:

```python
def test_formal_launcher_source_does_not_spawn_historical_pipeline():
    source = Path(run.__file__).read_text(encoding="utf-8")
    assert "PROJECT_ROOT / \"pipeline.py\"" not in source
    assert "orchestrator.py --novel" not in source
    for launcher in (Path("一键启动.bat"), Path("run.bat")):
        batch_source = launcher.read_text(encoding="utf-8")
        assert "pipeline.py" not in batch_source
        assert "run.py" in batch_source
```

Add these entries to `config/entrypoints.yaml`:

```yaml
compatibility:
  - path: "backend/routes/pipeline.py"
    status: "durable_facade"
  - path: "一键启动.bat"
    status: "forwards_to_canonical_cli"
  - path: "run.bat"
    status: "forwards_to_canonical_cli"
reference_only:
  - {path: "backend_v3", status: "reference_only"}
  - {path: "backend_v4", status: "reference_only"}
  - {path: "backend_v6", status: "reference_only"}
  - {path: "backend_v7", status: "reference_only"}
  - {path: "backend_v10", status: "reference_only"}
  - {path: "backend_v11", status: "reference_only"}
  - {path: "pipeline.py", status: "reference_only"}
  - {path: "orchestrator.py", status: "reference_only"}
  - {path: "pipeline.bat", status: "reference_only"}
  - {path: "run_v7.bat", status: "reference_only"}
  - {path: "start_v4.bat", status: "reference_only"}
  - {path: "start_v6.bat", status: "reference_only"}
```

In both `一键启动.bat` and `run.bat`, replace:

```bat
python -u "%~dp0pipeline.py" "!NOVEL_PATH!" 2>&1
```

with:

```bat
python -u "%~dp0run.py" --novel "!NOVEL_PATH!"
```

Do not modify `pipeline.bat`, `run_v7.bat`, `start_v4.bat`, or `start_v6.bat`; the manifest marks them reference-only.

Run:

```powershell
python -m pytest tests/runtime/test_entrypoint.py -q
```

Expected: all entrypoint tests PASS, and neither compatibility launcher names `pipeline.py`.

Replace the Task 5 commit command with:

```powershell
git add config/entrypoints.yaml run.py 一键启动.bat run.bat README.md tests/runtime/test_entrypoint.py
git commit -m "refactor: route the formal CLI through durable jobs"
```

## Amendment verification

Before the base plan's final verification, run:

```powershell
python -m pytest tests/api/test_pipeline_compat.py tests/projects/test_repository.py tests/runtime/test_entrypoint.py -q
rg -n "pipeline\.py" 一键启动.bat run.bat
```

Expected: all tests PASS and `rg` returns no matches. A nonzero `rg` exit code is expected because the forbidden text is absent.
