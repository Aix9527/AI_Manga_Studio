# V5 Real Production Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the durable orchestrator to one real V5 production chain that accepts novels, scripts and storyboard tables, produces 5–15 second shots at user-selected resolution, includes sound and final composition, and fails explicitly instead of fabricating output.

**Architecture:** A `ProductionStepRunner` translates the next durable step into a focused adapter call. Input normalization, ComfyUI generation, audio/rendering and media validation share typed contracts; every successful adapter returns validated `ArtifactDraft` records for atomic checkpointing. `PipelineV5` becomes a compatibility facade and no longer owns fallback or job-state policy.

**Tech Stack:** Python, Pydantic 2, FastAPI, ComfyUI REST, Pillow, FFmpeg/ffprobe, existing V5 director modules, pytest

---

**Depends on:** `docs/superpowers/plans/2026-07-17-v5-durable-orchestrator.md`

**Produces:** A real end-to-end production executor usable by both the durable worker and legacy V5 entry point.

**Renderer boundary:** Keep strict FFmpeg as the single release-critical compositor because the current V5 backend, validators and recovery checkpoints are Python-native. `CompositionAdapter` remains the extension boundary for a future Remotion or HyperFrames title/overlay renderer; neither is placed in the mandatory path now, avoiding a second timeline/state system and a Node 22 dependency in the one-click launcher.

## File structure

| Path | Responsibility |
|---|---|
| `backend/production/contracts.py` | Step context, outcome and production error types |
| `backend/production/input_loader.py` | Detect and normalize novel, script and storyboard inputs |
| `backend/routes/uploads.py` | Stream browser-selected source files into managed storage and validate them |
| `backend/production/media_validation.py` | Validate JSON, image, audio, video and final movie artifacts |
| `backend/production/comfy_adapter.py` | ComfyUI submission, output resolution and cancellation |
| `backend/production/planning_adapter.py` | Create a stable project/shot plan |
| `backend/production/visual_adapter.py` | Character sheets, storyboard, first/last frames and shot video |
| `backend/production/audio_adapter.py` | TTS, lip sync, subtitles, SFX and BGM preparation |
| `backend/production/composition_adapter.py` | Final assembly and output verification |
| `backend/production/stages.py` | Ordered stage registry and dependency hashes |
| `backend/production/executor.py` | Durable worker integration |
| `backend/pipeline_v5.py` | Compatibility facade without local generation fallbacks |
| `backend/composer.py` | Correct final composition invocation |
| `backend/scheduler/novel.py` | Preserve valid existing shot state |
| `requirements.txt` | DOCX/XLSX input readers |
| `tests/production/*` | Typed adapter and no-fabrication tests |

### Task 1: Normalize all three input types

**Files:**
- Create: `backend/production/__init__.py`
- Create: `backend/production/contracts.py`
- Create: `backend/production/input_loader.py`
- Create: `backend/routes/uploads.py`
- Modify: `backend/main.py`
- Modify: `requirements.txt`
- Test: `tests/production/test_input_loader.py`
- Test: `tests/api/test_uploads_api.py`

- [ ] **Step 1: Write failing detection and validation tests**

Create `tests/production/test_input_loader.py`:

```python
import csv
import json

import pytest

from backend.production.input_loader import InputLoader


def test_text_novel_is_detected_and_preserved(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("第一章 雨夜\n少年推开旧门。", encoding="utf-8")
    document = InputLoader().load(source)
    assert document.input_type == "novel"
    assert "少年推开旧门" in document.raw_text


def test_json_storyboard_rejects_shot_shorter_than_five_seconds(tmp_path):
    source = tmp_path / "shots.json"
    source.write_text(json.dumps({"shots": [{"shot_id": "s1", "duration": 4}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="5.0 and 15.0"):
        InputLoader().load(source)


def test_csv_storyboard_uses_requested_resolution(tmp_path):
    source = tmp_path / "shots.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["shot_id", "action", "duration"])
        writer.writeheader()
        writer.writerow({"shot_id": "s1", "action": "转身", "duration": "8"})
    document = InputLoader().load(source, width=1080, height=1920)
    assert document.shots[0].duration == 8
    assert (document.width, document.height) == (1080, 1920)
```

- [ ] **Step 2: Run the tests and verify the loader is missing**

```powershell
python -m pytest tests/production/test_input_loader.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Add typed production contracts**

Create `backend/production/__init__.py` as an empty package marker and create `backend/production/contracts.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from backend.orchestration.checkpoints import ArtifactDraft


class ProductionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ShotPlan(BaseModel):
    shot_id: str
    chapter: int = 1
    scene: int = 1
    action: str = ""
    dialogue: str = ""
    duration: float = Field(ge=5.0, le=15.0)
    width: int
    height: int
    extras: dict[str, Any] = Field(default_factory=dict)


class InputDocument(BaseModel):
    input_type: str
    source_path: str
    raw_text: str = ""
    width: int
    height: int
    shots: list[ShotPlan] = Field(default_factory=list)


@dataclass(frozen=True)
class StepContext:
    job: dict[str, Any]
    step: dict[str, Any]
    project_dir: Path
    cancel_requested: Callable[[], bool]


@dataclass(frozen=True)
class StepOutcome:
    step_id: str
    input_hash: str
    artifacts: list[ArtifactDraft]
    progress: float
    message: str
    final_video: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Implement extension and content detection**

Create `backend/production/input_loader.py`:

```python
from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.production.contracts import InputDocument, ShotPlan


class InputLoader:
    def load(self, source: str | Path, width: int = 1080, height: int = 1920) -> InputDocument:
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        suffix = path.suffix.lower()
        if suffix in {".json", ".csv", ".xlsx"}:
            rows = self._storyboard_rows(path)
            shots = [self._shot(row, index, width, height) for index, row in enumerate(rows, 1)]
            return InputDocument(
                input_type="storyboard",
                source_path=str(path),
                width=width,
                height=height,
                shots=shots,
            )
        text = self._read_text(path)
        input_type = "script" if self._looks_like_script(text) else "novel"
        return InputDocument(
            input_type=input_type,
            source_path=str(path),
            raw_text=text,
            width=width,
            height=height,
        )

    def _read_text(self, path: Path) -> str:
        if path.suffix.lower() in {".txt", ".md"}:
            return path.read_text(encoding="utf-8-sig")
        if path.suffix.lower() == ".docx":
            from docx import Document
            return "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
        raise ValueError(f"unsupported input format: {path.suffix}")

    def _storyboard_rows(self, path: Path) -> list[dict]:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            return payload["shots"] if isinstance(payload, dict) else payload
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        from openpyxl import load_workbook
        sheet = load_workbook(path, read_only=True, data_only=True).active
        rows = list(sheet.iter_rows(values_only=True))
        headers = [str(value or "").strip() for value in rows[0]]
        return [dict(zip(headers, row)) for row in rows[1:]]

    def _shot(self, row: dict, index: int, width: int, height: int) -> ShotPlan:
        duration = float(row.get("duration") or row.get("时长") or 5)
        if not 5.0 <= duration <= 15.0:
            raise ValueError("shot duration must be between 5.0 and 15.0 seconds")
        return ShotPlan(
            shot_id=str(row.get("shot_id") or row.get("镜头号") or f"shot-{index:04d}"),
            chapter=int(row.get("chapter") or row.get("章节") or 1),
            scene=int(row.get("scene") or row.get("场次") or 1),
            action=str(row.get("action") or row.get("动作") or ""),
            dialogue=str(row.get("dialogue") or row.get("对白") or ""),
            duration=duration,
            width=width,
            height=height,
            extras={str(key): value for key, value in row.items()},
        )

    @staticmethod
    def _looks_like_script(text: str) -> bool:
        markers = ("场景：", "人物：", "对白：", "INT.", "EXT.", "【场景】")
        return sum(marker in text for marker in markers) >= 2
```

- [ ] **Step 5: Add a safe browser-upload API**

Create `backend/routes/uploads.py`:

```python
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from backend.production.input_loader import InputLoader

router = APIRouter(prefix="/api/uploads", tags=["Uploads"])
ALLOWED = {".txt", ".md", ".docx", ".json", ".csv", ".xlsx"}
MAX_BYTES = 100 * 1024 * 1024


@router.post("")
async def upload_input(request: Request, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, f"unsupported input format: {suffix or 'none'}")
    root = Path(request.app.state.upload_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{uuid.uuid4()}{suffix}"
    temporary = target.with_suffix(f"{suffix}.part")
    size = 0
    try:
        with temporary.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "input file exceeds 100 MB")
                handle.write(chunk)
        os.replace(temporary, target)
        document = InputLoader().load(target)
    except HTTPException:
        temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    except Exception as error:
        temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise HTTPException(422, f"input validation failed: {error}") from error
    finally:
        await file.close()
    return {
        "path": str(target), "original_name": Path(file.filename or "input").name,
        "input_type": document.input_type, "size": size,
    }
```

Create `tests/api/test_uploads_api.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes.uploads import router


def upload_client(tmp_path):
    app = FastAPI()
    app.state.upload_root = tmp_path / "uploads"
    app.include_router(router)
    return TestClient(app), app.state.upload_root


def test_upload_streams_to_managed_storage_and_detects_novel(tmp_path):
    client, root = upload_client(tmp_path)
    response = client.post("/api/uploads", files={
        "file": ("../../story.txt", "第一章\n少年醒来".encode("utf-8"), "text/plain"),
    })
    assert response.status_code == 200
    payload = response.json()
    target = Path(payload["path"]).resolve()
    assert root.resolve() in target.parents
    assert payload["original_name"] == "story.txt"
    assert payload["input_type"] == "novel"


def test_unsupported_upload_is_rejected_without_writing(tmp_path):
    client, root = upload_client(tmp_path)
    response = client.post("/api/uploads", files={"file": ("payload.exe", b"no", "application/octet-stream")})
    assert response.status_code == 415
    assert not root.exists()
```

Import `Path`, set `app.state.upload_root = Path("storage/uploads")`, include this router in `backend/main.py`, and run:

```powershell
python -m pytest tests/api/test_uploads_api.py -q
```

Expected: 2 passed; client filenames never choose the server destination path.

- [ ] **Step 6: Add DOCX and XLSX readers**

Append to `requirements.txt`:

```text
python-docx>=1.1.0,<2.0.0
openpyxl>=3.1.0,<4.0.0
```

Install and run the tests:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests/production/test_input_loader.py -q
```

Expected: 3 passed.

- [ ] **Step 7: Commit normalized input and upload support**

```powershell
git add backend/production backend/routes/uploads.py backend/main.py requirements.txt tests/production/test_input_loader.py tests/api/test_uploads_api.py
git commit -m "feat: normalize novel script and storyboard inputs"
```

### Task 2: Make ComfyUI failures explicit and cancellable

**Files:**
- Create: `backend/production/comfy_adapter.py`
- Modify: `backend/comfyui_client.py:152-402`
- Test: `tests/production/test_comfy_adapter.py`

- [ ] **Step 1: Write failing no-output and cancellation tests**

Create `tests/production/test_comfy_adapter.py`:

```python
import pytest

from backend.production.comfy_adapter import ComfyAdapter
from backend.production.contracts import ProductionError


class EmptyClient:
    def submit_workflow(self, workflow, wait=True):
        return None

    def cancel_current(self):
        return True


def test_missing_comfy_output_is_a_real_failure():
    with pytest.raises(ProductionError, match="returned no output") as error:
        ComfyAdapter(EmptyClient()).submit({"1": {}}, expected="image")
    assert error.value.code == "COMFY_NO_OUTPUT"


def test_adapter_forwards_cancel_to_comfyui():
    assert ComfyAdapter(EmptyClient()).cancel()
```

- [ ] **Step 2: Run the tests and verify the adapter is missing**

```powershell
python -m pytest tests/production/test_comfy_adapter.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Implement explicit ComfyUI output handling**

Create `backend/production/comfy_adapter.py`:

```python
from pathlib import Path

from backend.production.contracts import ProductionError


class ComfyAdapter:
    def __init__(self, client):
        self.client = client

    def submit(self, workflow: dict, expected: str) -> Path:
        result = self.client.submit_workflow(workflow, wait=True)
        if not result:
            raise ProductionError("COMFY_NO_OUTPUT", "ComfyUI returned no output")
        collection = "images" if expected == "image" else "videos"
        candidates = result.get(collection, [])
        if not candidates:
            raise ProductionError("COMFY_WRONG_OUTPUT", f"ComfyUI returned no {expected}")
        path = Path(candidates[0].get("path", "")).resolve()
        if not path.is_file():
            raise ProductionError("COMFY_OUTPUT_MISSING", f"ComfyUI output file is missing: {path}")
        return path

    def cancel(self) -> bool:
        return bool(self.client.cancel_current())
```

- [ ] **Step 4: Preserve ComfyUI error details in the client**

Add `last_error: str` to `ComfyUIClient`, set it for non-200 submission, history error and timeout, and clear it before a new submission:

```python
self.last_error = ""

# before POST /prompt
self.last_error = ""

# non-200
self.last_error = f"HTTP {resp.status_code}: {resp.text[:1000]}"

# history error
self.last_error = json.dumps(status, ensure_ascii=False)

# timeout
self.last_error = f"timeout after {self.max_wait}s"
```

Update `ComfyAdapter.submit` so the no-output message appends `client.last_error` when present.

- [ ] **Step 5: Run adapter tests and commit**

```powershell
python -m pytest tests/production/test_comfy_adapter.py -q
git add backend/comfyui_client.py backend/production/comfy_adapter.py tests/production/test_comfy_adapter.py
git commit -m "fix: surface ComfyUI generation failures"
```

Expected: 2 passed; no local image or video is created during the tests.

### Task 3: Validate every media artifact before checkpointing

**Files:**
- Create: `backend/production/media_validation.py`
- Test: `tests/production/test_media_validation.py`

- [ ] **Step 1: Write failing image and final-video validation tests**

Create `tests/production/test_media_validation.py`:

```python
import subprocess

import pytest
from PIL import Image

from backend.production.media_validation import MediaValidator
from backend.production.contracts import ProductionError


def test_image_resolution_must_match_request(tmp_path):
    path = tmp_path / "frame.png"
    Image.new("RGB", (320, 180), "red").save(path)
    with pytest.raises(ProductionError, match="resolution"):
        MediaValidator().image(path, width=1080, height=1920)


def test_video_validator_rejects_missing_file(tmp_path):
    with pytest.raises(ProductionError, match="missing"):
        MediaValidator().video(tmp_path / "missing.mp4", width=1080, height=1920, min_duration=5)
```

- [ ] **Step 2: Run the tests and verify failure**

```powershell
python -m pytest tests/production/test_media_validation.py -q
```

Expected: FAIL because `MediaValidator` is missing.

- [ ] **Step 3: Implement JSON, image, audio and video validators**

Create `backend/production/media_validation.py`:

```python
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

from PIL import Image

from backend.production.contracts import ProductionError


class MediaValidator:
    def json(self, path: str | Path, required_keys: set[str]) -> dict:
        resolved = Path(path)
        if not resolved.is_file():
            raise ProductionError("ARTIFACT_MISSING", f"JSON artifact missing: {resolved}")
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        missing = required_keys.difference(payload)
        if missing:
            raise ProductionError("JSON_INVALID", f"JSON missing keys: {sorted(missing)}")
        return payload

    def image(self, path: str | Path, width: int, height: int) -> dict:
        resolved = Path(path)
        if not resolved.is_file():
            raise ProductionError("ARTIFACT_MISSING", f"image missing: {resolved}")
        with Image.open(resolved) as image:
            image.verify()
        with Image.open(resolved) as image:
            if image.size != (width, height):
                raise ProductionError("IMAGE_RESOLUTION", f"image resolution {image.size} != {(width, height)}")
            return {"width": image.width, "height": image.height, "format": image.format}

    def audio(self, path: str | Path) -> dict:
        resolved = Path(path)
        if not resolved.is_file():
            raise ProductionError("ARTIFACT_MISSING", f"audio missing: {resolved}")
        with wave.open(str(resolved), "rb") as stream:
            duration = stream.getnframes() / stream.getframerate()
            if duration <= 0:
                raise ProductionError("AUDIO_EMPTY", f"audio has zero duration: {resolved}")
            return {"duration": duration, "sample_rate": stream.getframerate(), "channels": stream.getnchannels()}

    def video(self, path: str | Path, width: int, height: int, min_duration: float) -> dict:
        resolved = Path(path)
        if not resolved.is_file() or resolved.stat().st_size == 0:
            raise ProductionError("ARTIFACT_MISSING", f"video missing: {resolved}")
        command = [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(resolved),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            raise ProductionError("VIDEO_DECODE", f"video cannot be decoded: {resolved}") from error
        probe = json.loads(result.stdout)
        video = next((stream for stream in probe["streams"] if stream["codec_type"] == "video"), None)
        duration = float(probe["format"].get("duration") or 0)
        if not video or (int(video["width"]), int(video["height"])) != (width, height):
            raise ProductionError("VIDEO_RESOLUTION", "video resolution does not match the project")
        if duration + 0.15 < min_duration:
            raise ProductionError("VIDEO_DURATION", f"video duration {duration:.2f}s is shorter than {min_duration:.2f}s")
        return {"width": width, "height": height, "duration": duration, "codec": video.get("codec_name", "")}
```

- [ ] **Step 4: Run validator tests and commit**

```powershell
python -m pytest tests/production/test_media_validation.py -q
git add backend/production/media_validation.py tests/production/test_media_validation.py
git commit -m "feat: validate real production artifacts"
```

Expected: 2 passed.

### Task 4: Remove V5 local fallbacks and fix final composition

**Files:**
- Modify: `backend/pipeline_v5.py:457-630`
- Modify: `backend/lipsync.py:291-530`
- Modify: `backend/composer.py:131-220`
- Modify: `backend/scheduler/novel.py:160-205`
- Replace: `tests/test_pipeline_v5.py`
- Test: `tests/production/test_pipeline_no_fallback.py`
- Test: `tests/production/test_composition.py`

- [ ] **Step 1: Replace the fallback test with an explicit-failure test**

Delete `test_local_interpolated_video_renderer_creates_mp4` from `tests/test_pipeline_v5.py`. Create `tests/production/test_pipeline_no_fallback.py`:

```python
import pytest

from backend.pipeline_v5 import PipelineV5, ShotPipelineResult
from backend.unified_shot import UnifiedShot


class NoOutputComfy:
    def submit_workflow(self, workflow, wait=True):
        return None


def test_first_frame_failure_does_not_create_local_substitute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline = PipelineV5.__new__(PipelineV5)
    pipeline.comfyui = NoOutputComfy()
    pipeline.workflow_gen = type("Workflow", (), {"generate": lambda self, shot: {"1": {}}})()
    shot = UnifiedShot(chapter=1, scene=1, shot=1, duration=5, width=1080, height=1920)
    result = ShotPipelineResult(shot_id="shot-1")
    with pytest.raises(RuntimeError, match="ComfyUI image generation returned no output"):
        pipeline._generate_image(shot, pipeline._build_cinematic_shot(shot), result)
    assert not (tmp_path / "output" / "v5_local_frames").exists()


def test_lipsync_provider_failure_does_not_create_silent_audio(monkeypatch, tmp_path):
    from backend.lipsync import LipSync
    engine = LipSync(output_dir=str(tmp_path))
    monkeypatch.setattr(engine, "_tts_cosyvoice", lambda task, output: "")
    monkeypatch.setattr(engine, "_tts_azure", lambda task, output: "")
    monkeypatch.setattr(engine, "_tts_elevenlabs", lambda task, output: "")
    task = engine.create_task(1, "角色A", "你好", "frame.png")
    result = engine.process_task(task)
    assert result.status.value == "failed"
    assert not list(tmp_path.rglob("*.wav"))


def test_explicit_i2v_model_never_falls_through_to_another_template():
    from backend.i2v_generator import I2VGenerator
    generator = I2VGenerator.__new__(I2VGenerator)
    generator._wan_template = None
    generator._ltx_template = {"1": {}}
    generator._ad_template = None
    with pytest.raises(RuntimeError, match="wan.*template.*unavailable"):
        generator.generate(UnifiedShot(), "first.png", model="wan")
```

Create `tests/production/test_composition.py`:

```python
import subprocess
from types import SimpleNamespace

import pytest

from backend.pipeline_v5 import PipelineV5, ShotPipelineResult
from backend.render import FFmpegPostProduction, PostProductionConfig


@pytest.fixture
def ffmpeg_video_without_audio(tmp_path):
    target = tmp_path / "silent-video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x256:d=1:r=24",
        "-an", "-c:v", "libx264", str(target),
    ], check=True, capture_output=True)
    return str(target)


def test_failed_composition_returns_no_final_video(monkeypatch, tmp_path):
    first = tmp_path / "one.mp4"
    second = tmp_path / "two.mp4"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    monkeypatch.setattr(
        "backend.composer.CinemaComposer.compose",
        lambda self, *args, **kwargs: SimpleNamespace(success=False, output_path="", error="ffmpeg failed"),
    )
    pipeline = PipelineV5.__new__(PipelineV5)
    result = pipeline._compose_final_video("p1", [
        ShotPipelineResult(video_path=str(first)),
        ShotPipelineResult(video_path=str(second)),
    ])
    assert result == ""


def test_strict_postproduction_never_skips_failed_bgm(monkeypatch, tmp_path):
    renderer = FFmpegPostProduction.__new__(FFmpegPostProduction)
    renderer.config = PostProductionConfig(strict=True)
    renderer._temp_dir = tmp_path
    renderer._bgm_dir = tmp_path
    bgm = tmp_path / "music.wav"
    bgm.write_bytes(b"audio")
    monkeypatch.setattr(renderer, "_pick_bgm", lambda: str(bgm))
    monkeypatch.setattr(renderer, "_get_video_duration", lambda path: 5.0)
    monkeypatch.setattr("backend.render.subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="mix failed"))
    with pytest.raises(RuntimeError, match="BGM mix failed"):
        renderer._mix_bgm(str(tmp_path / "input.mp4"))


def test_postproduction_adds_an_audio_track_before_mixing(ffmpeg_video_without_audio, tmp_path):
    renderer = FFmpegPostProduction(PostProductionConfig(strict=True), output_dir=str(tmp_path))
    normalized = renderer._ensure_audio_track(ffmpeg_video_without_audio)
    assert renderer._has_audio_stream(normalized) is True
```

- [ ] **Step 2: Run the tests and prove the current fallback behavior fails them**

```powershell
python -m pytest tests/production/test_pipeline_no_fallback.py tests/production/test_composition.py -q
```

Expected: both tests fail against the current code.

- [ ] **Step 3: Remove local image and video fallback calls**

Change `PipelineV5._generate_image`, `_generate_last_frame` and `_generate_video` so missing output raises:

```python
comfy_result = self.comfyui.submit_workflow(workflow, wait=True)
if not comfy_result:
    raise RuntimeError("ComfyUI image generation returned no output")
```

Use the corresponding messages for last frame and video. Delete `_generate_local_keyframe` and `_generate_local_video_fallback` from `backend/pipeline_v5.py`. Keep the standalone local renderer modules only for developer media tests; the production pipeline must not import them.

In `backend/lipsync.py`, replace the call to `_generate_silent_wav` in `_generate_tts` with:

```python
raise RuntimeError(
    f"all configured TTS providers failed for task {task.task_id}; silent audio is forbidden"
)
```

Delete `_generate_silent_wav` when no non-production caller remains.

Add `model: str = "auto"` and `fps: int = 24` to `_generate_video` and forward both to `I2VGenerator.generate`. In `I2VGenerator.generate`, an explicitly requested `wan`, `ltx`, or `animatediff` template must raise `<model> template unavailable` when absent; only `model="auto"` may select among installed real templates.

- [ ] **Step 4: Fix final composition semantics**

Add `strict: bool = True` to `PostProductionConfig`. Add one failure helper to `FFmpegPostProduction`:

```python
def _fail_or_passthrough(self, stage: str, video_path: str, detail: str) -> str:
    if self.config.strict:
        raise RuntimeError(f"{stage} failed: {detail}")
    logger.warning(f"FFmpegPostProduction: {stage} failed — {detail[:200]}")
    return video_path
```

Use it instead of returning the first clip or previous video after stitching, requested subtitle, BGM, SFX, opening or ending FFmpeg commands fail. In strict mode, missing requested BGM/SFX source files also raise. Add `_has_audio_stream` using `ffprobe`, and `_ensure_audio_track` that muxes `anullsrc` into silent I2V clips before BGM/SFX mixing; its FFmpeg failure also uses `_fail_or_passthrough`. The outer `render` method calls `_ensure_audio_track` immediately after subtitle burn, may log an exception and return `""`, and must never report an earlier intermediate file as the final result.

Replace `_compose_final_video` with:

```python
def _compose_final_video(self, project_id: str, shots: list[ShotPipelineResult]) -> str:
    video_paths = [shot.video_path for shot in shots]
    if not video_paths or any(not path or not os.path.isfile(path) for path in video_paths):
        return ""
    if len(video_paths) == 1:
        return video_paths[0]
    from backend.composer import CinemaComposer
    composer = CinemaComposer(output_dir=os.path.join("output", project_id, "final"))
    result = composer.compose(
        video_paths,
        output_name="final_v5.mp4",
        add_transitions=False,
    )
    if not result.success:
        logger.error(f"PipelineV5: final composition failed: {result.error}")
        return ""
    return result.output_path
```

Do not catch and downgrade composition exceptions, and never return `video_paths[0]` when a multi-clip composition fails.

- [ ] **Step 5: Preserve successful shot JSON during reparsing**

In `backend/scheduler/novel.py`, before writing a shot file, read an existing file and retain `status`, `image_path`, `video_path` and retry metadata only when the stable shot identity matches:

```python
existing_path = Path(shot.json_path)
if existing_path.is_file():
    existing = UnifiedShot.from_json_file(str(existing_path))
    if existing.shot_id == shot.shot_id:
        shot.status = existing.status
        shot.image_path = existing.image_path
        shot.video_path = existing.video_path
        shot.retry_count = existing.retry_count
```

- [ ] **Step 6: Run the focused V5 tests and commit**

```powershell
python -m pytest tests/test_pipeline_v5.py tests/production/test_pipeline_no_fallback.py tests/production/test_composition.py -q
git add backend/pipeline_v5.py backend/composer.py backend/scheduler/novel.py tests/test_pipeline_v5.py tests/production
git commit -m "fix: stop V5 on real generation failures"
```

Expected: all focused tests pass; no `v5_local_frames` directory is created, and a failed sound/composition stage cannot silently produce a nominal success.

### Task 5: Build the ordered production-stage executor

**Files:**
- Create: `backend/production/planning_adapter.py`
- Create: `backend/production/visual_adapter.py`
- Create: `backend/production/audio_adapter.py`
- Create: `backend/production/composition_adapter.py`
- Create: `backend/production/stages.py`
- Replace: `backend/production/executor.py`
- Test: `tests/production/test_executor.py`

- [ ] **Step 1: Write a failing stage-order and manual-review test**

Create `tests/production/test_executor.py`:

```python
from types import SimpleNamespace

import pytest

from backend.production.executor import ProductionStepRunner
from backend.production.stages import stage_keys


@pytest.fixture
def executor_fixture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def execute(mode):
        repository = SimpleNamespace(
            ensure_steps=lambda job_id, stages: None,
            ensure_shot_steps=lambda job_id, stages, shot_ids: None,
            next_incomplete_step=lambda job_id: {
                "id": "step-1", "stage_key": "input_parse", "shot_id": None,
            },
            upstream_artifact_hashes=lambda job_id, step_id: [],
            progress_after=lambda step_id: 0.1,
            mark_completed=lambda job_id: True,
        )
        runner = ProductionStepRunner(
            repository,
            adapters={"input_parse": lambda context: []},
        )
        return runner.run_next({
            "id": "job-1", "project_id": "project-1", "mode": mode,
            "settings": {"width": 1080, "height": 1920, "fps": 24},
        }, lambda: False)

    return execute


def test_stage_registry_covers_full_short_drama_chain():
    assert stage_keys() == [
        "input_parse", "script_plan", "character_scene", "storyboard",
        "first_frame", "last_frame", "shot_video", "voice_lipsync",
        "subtitle_sfx_bgm", "quality", "compose_export",
    ]


def test_automatic_mode_does_not_request_review(executor_fixture):
    outcome = executor_fixture("automatic")
    assert outcome.metadata["requires_review"] is False


def test_manual_mode_requests_review_after_successful_stage(executor_fixture):
    outcome = executor_fixture("manual_review")
    assert outcome.metadata["requires_review"] is True
```

- [ ] **Step 2: Run the tests and verify the stage registry is missing**

```powershell
python -m pytest tests/production/test_executor.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Define the complete stage registry**

Create `backend/production/stages.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class StageDefinition:
    key: str
    label: str
    shot_scoped: bool


STAGES = [
    StageDefinition("input_parse", "输入识别与解析", False),
    StageDefinition("script_plan", "剧本与镜头规划", False),
    StageDefinition("character_scene", "角色、场景与一致性", False),
    StageDefinition("storyboard", "分镜设计", True),
    StageDefinition("first_frame", "首帧生成", True),
    StageDefinition("last_frame", "尾帧生成", True),
    StageDefinition("shot_video", "镜头视频", True),
    StageDefinition("voice_lipsync", "配音与口型", True),
    StageDefinition("subtitle_sfx_bgm", "字幕、音效与音乐", False),
    StageDefinition("quality", "质量检查", True),
    StageDefinition("compose_export", "合成与导出", False),
]


def stage_keys() -> list[str]:
    return [stage.key for stage in STAGES]
```

- [ ] **Step 4: Implement focused adapters over existing V5 modules**

Create `backend/production/planning_adapter.py`:

```python
import json

from backend.orchestration.checkpoints import ArtifactDraft
from backend.production.contracts import InputDocument, ProductionError, ShotPlan, StepContext
from backend.production.input_loader import InputLoader
from backend.scheduler.novel import NovelStage
from backend.unified_shot import UnifiedShot


class PlanningAdapter:
    def parse(self, context: StepContext) -> list[ArtifactDraft]:
        if context.cancel_requested():
            raise ProductionError("USER_CANCELLED", "任务已取消")
        settings = context.job["settings"]
        document = InputLoader().load(
            context.job["input_path"], int(settings["width"]), int(settings["height"])
        )
        target = context.project_dir / "input.json"
        target.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        return [ArtifactDraft.from_path("normalized_input", target, {"input_type": document.input_type})]

    def plan(self, context: StepContext) -> list[ArtifactDraft]:
        if context.cancel_requested():
            raise ProductionError("USER_CANCELLED", "任务已取消")
        document = InputDocument.model_validate_json(
            (context.project_dir / "input.json").read_text(encoding="utf-8")
        )
        settings = context.job["settings"]
        shots = list(document.shots)
        if not shots:
            NovelStage(project_dir=str(context.project_dir.parent)).parse(
                document.source_path,
                project_id=context.job["project_id"],
                max_shots_per_chapter=int(settings.get("options", {}).get("max_shots", 30)),
            )
            for path in sorted(context.project_dir.glob("ch*/shots/shot_*.json")):
                source = UnifiedShot.from_json_file(str(path))
                source.duration = float(settings["shot_duration"])
                source.width, source.height = int(settings["width"]), int(settings["height"])
                source.to_json_file(str(path))
                shots.append(ShotPlan(
                    shot_id=source.shot_id, chapter=source.chapter, scene=source.scene,
                    action=source.action, dialogue=source.dialogue, duration=source.duration,
                    width=source.width, height=source.height,
                ))
        else:
            for index, planned in enumerate(shots, 1):
                path = context.project_dir / f"ch{planned.chapter:02d}" / "shots" / f"shot_{index:03d}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                UnifiedShot(
                    shot_id=planned.shot_id, chapter=planned.chapter, scene=planned.scene,
                    shot=index, action=planned.action, dialogue=planned.dialogue,
                    duration=planned.duration, width=planned.width, height=planned.height,
                ).to_json_file(str(path))
        if not shots:
            raise ProductionError("PLAN_EMPTY", "输入未生成任何镜头")
        target = context.project_dir / "plan.json"
        target.write_text(json.dumps({"shots": [shot.model_dump() for shot in shots]}, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts = [ArtifactDraft.from_path("project_plan", target, {"shots": len(shots)})]
        artifacts.extend(ArtifactDraft.from_path("shot_plan", path, {}) for path in sorted(context.project_dir.glob("ch*/shots/shot_*.json")))
        return artifacts
```

Create `backend/production/visual_adapter.py`:

```python
import json
from dataclasses import asdict

from backend.orchestration.checkpoints import ArtifactDraft
from backend.pipeline_v5 import PipelineResult, PipelineV5, ShotPipelineResult
from backend.production.contracts import ProductionError, StepContext
from backend.production.media_validation import MediaValidator
from backend.unified_shot import UnifiedShot


class VisualAdapter:
    def __init__(self):
        self.pipeline = PipelineV5()
        self.validator = MediaValidator()

    def _guard(self, context):
        if context.cancel_requested():
            raise ProductionError("USER_CANCELLED", "任务已取消")

    def cancel(self):
        cancel = getattr(self.pipeline.comfyui, "cancel_current", None)
        return bool(cancel and cancel())

    def _shot(self, context):
        for path in sorted(context.project_dir.glob("ch*/shots/shot_*.json")):
            shot = UnifiedShot.from_json_file(str(path))
            if shot.shot_id == context.step.get("shot_id"):
                return shot, path
        raise ProductionError("SHOT_NOT_FOUND", f"镜头不存在: {context.step.get('shot_id')}")

    def character_scene(self, context):
        self._guard(context)
        result = PipelineResult(project_id=context.job["project_id"])
        stage = self.pipeline._stage_character_sheets(result)
        if stage.status != "success":
            raise ProductionError("CHARACTER_SHEET_FAILED", stage.error or "角色资产生成失败")
        target = context.project_dir / "character_sheets.json"
        target.write_text(json.dumps([asdict(sheet) for sheet in result.character_sheets], ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return [ArtifactDraft.from_path("character_sheets", target, stage.output)]

    def storyboard(self, context):
        self._guard(context)
        shot, _ = self._shot(context)
        panel = self.pipeline.storyboard_engine.generate_from_cinematic_shots([self.pipeline._build_cinematic_shot(shot)])[0]
        target = context.project_dir / "storyboards" / f"{shot.shot_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(panel), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return [ArtifactDraft.from_path("storyboard", target, {"shot_id": shot.shot_id})]

    def first_frame(self, context):
        self._guard(context)
        shot, path = self._shot(context)
        result = self.pipeline._generate_image(shot, self.pipeline._build_cinematic_shot(shot), ShotPipelineResult(shot_id=shot.shot_id))
        metadata = self.validator.image(result.image_path, shot.width, shot.height)
        shot.image_path = result.image_path
        shot.to_json_file(str(path))
        return [ArtifactDraft.from_path("first_frame", result.image_path, metadata)]

    def last_frame(self, context):
        self._guard(context)
        shot, path = self._shot(context)
        if not shot.image_path:
            raise ProductionError("FIRST_FRAME_MISSING", f"{shot.shot_id} 缺少首帧")
        result = self.pipeline._generate_last_frame(
            shot, self.pipeline._build_cinematic_shot(shot),
            ShotPipelineResult(
                shot_id=shot.shot_id,
                image_path=shot.image_path,
                image_prompt=getattr(shot, "positive_prompt", ""),
            ),
        )
        metadata = self.validator.image(result.last_frame_path, shot.width, shot.height)
        shot.extra["last_frame_path"] = result.last_frame_path
        shot.to_json_file(str(path))
        return [ArtifactDraft.from_path("last_frame", result.last_frame_path, metadata)]

    def shot_video(self, context):
        self._guard(context)
        shot, path = self._shot(context)
        requested = context.job["settings"].get("options", {}).get("video_workflow", "auto")
        model = {"wan22": "wan", "ltx23": "ltx"}.get(requested, requested)
        result = self.pipeline._generate_video(
            shot, self.pipeline._build_cinematic_shot(shot),
            ShotPipelineResult(shot_id=shot.shot_id, image_path=shot.image_path, last_frame_path=str(shot.extra.get("last_frame_path", ""))),
            model=model,
            fps=int(context.job["settings"]["fps"]),
        )
        metadata = self.validator.video(result.video_path, shot.width, shot.height, shot.duration)
        shot.video_path = result.video_path
        shot.to_json_file(str(path))
        return [ArtifactDraft.from_path("shot_video", result.video_path, metadata)]

    def quality(self, context):
        self._guard(context)
        shot, _ = self._shot(context)
        report = {
            "image": self.validator.image(shot.image_path, shot.width, shot.height),
            "video": self.validator.video(shot.video_path, shot.width, shot.height, shot.duration),
        }
        target = context.project_dir / "quality" / f"{shot.shot_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return [ArtifactDraft.from_path("quality_report", target, {"shot_id": shot.shot_id})]
```

Create `backend/production/audio_adapter.py`:

```python
import json
from pathlib import Path

from backend.lipsync import LipSync, LipSyncStatus
from backend.orchestration.checkpoints import ArtifactDraft
from backend.production.contracts import ProductionError
from backend.production.media_validation import MediaValidator
from backend.scheduler.subtitle import SubtitleStage
from backend.unified_shot import UnifiedShot


class AudioAdapter:
    SFX_KEYWORDS = {
        "footstep": ("脚步", "走路", "奔跑", "footstep", "walk", "run"),
        "whoosh": ("掠过", "挥动", "飞过", "whoosh", "swing", "fly"),
        "impact": ("撞击", "击中", "落地", "impact", "hit", "land"),
        "magic": ("魔法", "法术", "能量", "magic", "spell", "energy"),
        "ambient": ("风", "雨", "城市", "森林", "wind", "rain", "city", "forest"),
        "sword_clash": ("刀", "剑", "兵器", "sword", "blade"),
        "explosion": ("爆炸", "爆破", "explosion", "blast"),
    }

    def __init__(self):
        self.validator = MediaValidator()

    def _shots(self, context):
        return [(UnifiedShot.from_json_file(str(path)), path) for path in sorted(context.project_dir.glob("ch*/shots/shot_*.json"))]

    def _shot(self, context):
        for shot, path in self._shots(context):
            if shot.shot_id == context.step.get("shot_id"):
                return shot, path
        raise ProductionError("SHOT_NOT_FOUND", f"镜头不存在: {context.step.get('shot_id')}")

    def _sfx_markers(self, shot):
        source = f"{shot.sfx} {shot.action}".lower()
        return [
            {"category": category, "offset": min(0.25, shot.duration / 4), "volume": 0.6}
            for category, words in self.SFX_KEYWORDS.items()
            if any(word in source for word in words)
        ]

    def voice_lipsync(self, context):
        if context.cancel_requested():
            raise ProductionError("USER_CANCELLED", "任务已取消")
        options = context.job["settings"].get("options", {})
        if not options.get("tts_enabled", True):
            return []
        engine = LipSync(output_dir=str(context.project_dir / "audio"))
        artifacts = []
        shot, path = self._shot(context)
        if not shot.dialogue:
            return artifacts
        task = engine.create_task(shot.shot, shot.characters[0] if shot.characters else "旁白", shot.dialogue, shot.image_path)
        result = engine.process_task(task)
        if result.status != LipSyncStatus.complete:
            raise ProductionError("TTS_LIPSYNC_FAILED", result.error_message or f"{shot.shot_id} 配音口型失败")
        artifacts.append(ArtifactDraft.from_path("voice", result.wav_path, self.validator.audio(result.wav_path)))
        shot.extra["voice_path"] = result.wav_path
        if options.get("lipsync_enabled", True):
            video_meta = self.validator.video(result.lip_video_path, shot.width, shot.height, shot.duration)
            shot.video_path = result.lip_video_path
            artifacts.append(ArtifactDraft.from_path("lipsync_video", result.lip_video_path, video_meta))
        shot.to_json_file(str(path))
        return artifacts

    def subtitle_sfx_bgm(self, context):
        if context.cancel_requested():
            raise ProductionError("USER_CANCELLED", "任务已取消")
        shots = [item[0] for item in self._shots(context)]
        options = context.job["settings"].get("options", {})
        artifacts = []
        subtitle_path = ""
        if options.get("subtitles_enabled", True):
            subtitle = SubtitleStage().generate(shots, str(context.project_dir / "audio"))
            subtitle_path = subtitle.subtitle_path
            if subtitle.total and not Path(subtitle_path).is_file():
                raise ProductionError("SUBTITLE_FAILED", "字幕文件未生成")
            if subtitle_path:
                artifacts.append(ArtifactDraft.from_path("subtitles", subtitle_path, {"entries": subtitle.total}))
        bgm_dir = Path(options.get("bgm_dir") or "assets/bgm")
        sfx_dir = Path(options.get("sfx_dir") or "assets/sfx")
        if options.get("bgm_enabled", True) and not any(bgm_dir.glob("*.*")):
            raise ProductionError("BGM_MISSING", f"背景音乐目录为空: {bgm_dir}")
        if options.get("sfx_enabled", True) and not any(sfx_dir.glob("*.*")):
            raise ProductionError("SFX_MISSING", f"音效目录为空: {sfx_dir}")
        sfx_by_shot = {
            shot.shot_id: self._sfx_markers(shot)
            for shot in shots
            if self._sfx_markers(shot)
        } if options.get("sfx_enabled", True) else {}
        target = context.project_dir / "audio" / "timeline.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "subtitle_path": subtitle_path,
            "bgm_dir": str(bgm_dir.resolve()),
            "sfx_dir": str(sfx_dir.resolve()),
            "sfx_by_shot": sfx_by_shot,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts.append(ArtifactDraft.from_path("audio_timeline", target, {}))
        return artifacts
```

Create `backend/production/composition_adapter.py`:

```python
import json

from backend.orchestration.checkpoints import ArtifactDraft
from backend.production.contracts import ProductionError
from backend.production.media_validation import MediaValidator
from backend.render import FFmpegPostProduction, PostProductionConfig, VideoSegment
from backend.unified_shot import UnifiedShot


class CompositionAdapter:
    def compose_export(self, context):
        if context.cancel_requested():
            raise ProductionError("USER_CANCELLED", "任务已取消")
        shots = [UnifiedShot.from_json_file(str(path)) for path in sorted(context.project_dir.glob("ch*/shots/shot_*.json"))]
        if not shots or any(not shot.video_path for shot in shots):
            raise ProductionError("SHOT_VIDEO_MISSING", "并非所有镜头都生成了真实视频")
        timeline = json.loads((context.project_dir / "audio" / "timeline.json").read_text(encoding="utf-8"))
        segments = [VideoSegment(
            path=shot.video_path,
            duration=shot.duration,
            subtitle_path=timeline.get("subtitle_path", ""),
            sfx=list(timeline.get("sfx_by_shot", {}).get(shot.shot_id, [])),
        ) for shot in shots]
        settings = context.job["settings"]
        renderer = FFmpegPostProduction(
            config=PostProductionConfig(
                fps=int(settings["fps"]),
                resolution=f"{settings['width']}x{settings['height']}",
                strict=True,
            ),
            bgm_dir=timeline.get("bgm_dir", ""), sfx_dir=timeline.get("sfx_dir", ""),
            output_dir=str(context.project_dir / "final"),
        )
        output = renderer.render(segments, "final.mp4")
        if not output:
            raise ProductionError("COMPOSE_FAILED", "最终合成没有生成视频")
        minimum = sum(shot.duration for shot in shots) - max(0, len(shots) - 1) * 0.5
        metadata = MediaValidator().video(output, int(settings["width"]), int(settings["height"]), minimum)
        return [ArtifactDraft.from_path("final_video", output, metadata)]
```

- [ ] **Step 5: Implement the durable step runner**

Replace the explicit-failure stub in `backend/production/executor.py`:

```python
from pathlib import Path

from backend.orchestration.checkpoints import input_hash
from backend.orchestration.worker import StepExecutionError
from backend.production.audio_adapter import AudioAdapter
from backend.production.composition_adapter import CompositionAdapter
from backend.production.contracts import ProductionError, StepContext, StepOutcome
from backend.production.planning_adapter import PlanningAdapter
from backend.production.stages import STAGES
from backend.production.visual_adapter import VisualAdapter


class ProductionStepRunner:
    def __init__(self, repository, adapters=None):
        self.repository = repository
        self.adapters = adapters or self._default_adapters()

    def run_next(self, job, cancel_requested):
        project_dir = Path("projects") / job["project_id"]
        project_dir.mkdir(parents=True, exist_ok=True)
        self.repository.ensure_steps(job["id"], STAGES)
        plan_path = project_dir / "plan.json"
        if plan_path.is_file():
            import json
            shot_ids = [shot["shot_id"] for shot in json.loads(plan_path.read_text(encoding="utf-8"))["shots"]]
            self.repository.ensure_shot_steps(job["id"], STAGES, shot_ids)
        step = self.repository.next_incomplete_step(job["id"])
        if step is None:
            if not self.repository.mark_completed(job["id"]):
                raise StepExecutionError("FINAL_VIDEO_MISSING", "所有步骤已结束，但未找到经过验证的最终视频")
            return None
        settings = job["settings"]
        context = StepContext(job, step, project_dir, cancel_requested)
        handler = self.adapters[step["stage_key"]]
        try:
            artifacts = handler(context)
        except ProductionError as error:
            raise StepExecutionError(error.code, str(error)) from error
        dependency_hash = input_hash({
            "settings": settings,
            "stage": step["stage_key"],
            "shot_id": step.get("shot_id"),
            "upstream": self.repository.upstream_artifact_hashes(job["id"], step["id"]),
        })
        return StepOutcome(
            step_id=step["id"],
            input_hash=dependency_hash,
            artifacts=artifacts,
            progress=self.repository.progress_after(step["id"]),
            message=f"{step['stage_key']} 完成",
            final_video=artifacts[0].path if step["stage_key"] == "compose_export" else "",
            metadata={"requires_review": job["mode"] == "manual_review"},
        )

    def cancel(self, job_id: str) -> bool:
        cancelled = False
        targets = {getattr(handler, "__self__", handler) for handler in self.adapters.values()}
        for adapter in targets:
            cancel = getattr(adapter, "cancel", None)
            cancelled = bool(cancel and cancel()) or cancelled
        return cancelled

    def _default_adapters(self):
        planning = PlanningAdapter()
        visual = VisualAdapter()
        audio = AudioAdapter()
        compose = CompositionAdapter()
        return {
            "input_parse": planning.parse,
            "script_plan": planning.plan,
            "character_scene": visual.character_scene,
            "storyboard": visual.storyboard,
            "first_frame": visual.first_frame,
            "last_frame": visual.last_frame,
            "shot_video": visual.shot_video,
            "voice_lipsync": audio.voice_lipsync,
            "subtitle_sfx_bgm": audio.subtitle_sfx_bgm,
            "quality": visual.quality,
            "compose_export": compose.compose_export,
        }
```

Add these repository helpers to `backend/orchestration/repository.py`:

```python
def ensure_steps(self, job_id, stages):
    import uuid
    with self.database.transaction() as conn:
        for sequence, stage in enumerate(stages):
            if stage.shot_scoped:
                continue
            conn.execute(
                """INSERT OR IGNORE INTO job_steps(
                    id, job_id, sequence, stage_key, shot_id, status
                ) VALUES(?, ?, ?, ?, '', 'pending')""",
                (str(uuid.uuid4()), job_id, sequence, stage.key),
            )

def ensure_shot_steps(self, job_id, stages, shot_ids):
    import uuid
    with self.database.transaction() as conn:
        for sequence, stage in enumerate(stages):
            if not stage.shot_scoped:
                continue
            for shot_id in shot_ids:
                conn.execute(
                    """INSERT OR IGNORE INTO job_steps(
                        id, job_id, sequence, stage_key, shot_id, status
                    ) VALUES(?, ?, ?, ?, ?, 'pending')""",
                    (str(uuid.uuid4()), job_id, sequence, stage.key, shot_id),
                )

def next_incomplete_step(self, job_id):
    selected = None
    with self.database.transaction() as conn:
        row = conn.execute(
            """SELECT * FROM job_steps WHERE job_id=? AND status IN ('pending', 'queued', 'retry_wait')
               ORDER BY sequence, shot_id LIMIT 1""",
            (job_id,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE job_steps SET status='running', started_at=? WHERE id=?",
                (utcnow(), row["id"]),
            )
            conn.execute(
                """UPDATE jobs SET current_stage=?, current_shot=?, updated_at=? WHERE id=?""",
                (row["stage_key"], row["shot_id"] or "", utcnow(), job_id),
            )
            selected = dict(row)
            selected["status"] = "running"
    return selected

def upstream_artifact_hashes(self, job_id, step_id):
    with self.database.connect() as conn:
        row = conn.execute("SELECT sequence FROM job_steps WHERE id=?", (step_id,)).fetchone()
        return [item["sha256"] for item in conn.execute(
            """SELECT a.sha256 FROM artifacts a JOIN job_steps s ON s.id=a.step_id
               WHERE a.job_id=? AND a.active=1 AND s.sequence < ? ORDER BY s.sequence, a.id""",
            (job_id, row["sequence"]),
        )]

def progress_after(self, step_id):
    with self.database.connect() as conn:
        job_id = conn.execute("SELECT job_id FROM job_steps WHERE id=?", (step_id,)).fetchone()["job_id"]
        total = conn.execute("SELECT COUNT(*) AS n FROM job_steps WHERE job_id=?", (job_id,)).fetchone()["n"]
        done = conn.execute("SELECT COUNT(*) AS n FROM job_steps WHERE job_id=? AND status='completed'", (job_id,)).fetchone()["n"]
        return min(1.0, (done + 1) / max(1, total))

def mark_completed(self, job_id):
    with self.database.transaction() as conn:
        changed = conn.execute(
            """UPDATE jobs SET status='completed', progress=1, message='制作完成',
               finished_at=?, updated_at=? WHERE id=? AND final_video <> ''""",
            (utcnow(), utcnow(), job_id),
        ).rowcount
    return changed == 1
```

- [ ] **Step 6: Run executor tests and commit**

```powershell
python -m pytest tests/production/test_executor.py -q
git add backend/production backend/orchestration/repository.py tests/production/test_executor.py
git commit -m "feat: execute the complete V5 production stage chain"
```

Expected: stage order is exact; automatic mode never requests review; manual mode requests review after a validated stage.

### Task 6: Prove failure, resume and final media behavior end to end

**Files:**
- Create: `tests/integration/test_real_pipeline_contract.py`
- Create: `tests/integration/test_pipeline_resume.py`
- Create: `tests/integration/conftest.py`

- [ ] **Step 1: Build a deterministic production-adapter fixture**

Create `tests/integration/conftest.py`. It exercises the real repository, worker, service, routes and checkpoint logic while replacing external model calls with deterministic artifact writers:

```python
import json
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backend.orchestration.checkpoints import ArtifactDraft
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.service import JobService
from backend.orchestration.worker import DurableWorker
from backend.production.contracts import ProductionError
from backend.production.executor import ProductionStepRunner
from backend.production.stages import STAGES
from backend.routes.jobs import router


@dataclass
class FakeProductionBackend:
    calls: list[dict] = field(default_factory=list)
    fail_stage: str | None = None

    def handler(self, stage):
        def run(context):
            self.calls.append({"stage": stage, "shot_id": context.step.get("shot_id")})
            if self.fail_stage == stage:
                raise ProductionError("COMFY_NO_OUTPUT", "ComfyUI returned no output")
            root = context.project_dir
            root.mkdir(parents=True, exist_ok=True)
            if stage == "script_plan":
                target = root / "plan.json"
                target.write_text(json.dumps({"shots": [{
                    "shot_id": "shot-0001", "duration": 5, "width": 320, "height": 256,
                }]}), encoding="utf-8")
                return [ArtifactDraft.from_path("project_plan", target, {"shots": 1})]
            if stage in {"first_frame", "last_frame"}:
                target = root / stage / f"{context.step.get('shot_id')}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (320, 256), "#335577").save(target)
                return [ArtifactDraft.from_path(stage, target, {"width": 320, "height": 256})]
            if stage == "shot_video":
                target = root / "video" / f"{context.step.get('shot_id')}.mp4"
                target.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x256:d=5",
                    "-r", "24", "-pix_fmt", "yuv420p", str(target),
                ], check=True, capture_output=True)
                return [ArtifactDraft.from_path("shot_video", target, {"duration": 5})]
            if stage == "compose_export":
                source = root / "video" / "shot-0001.mp4"
                target = root / "final" / "final.mp4"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                return [ArtifactDraft.from_path("final_video", target, {"duration": 5})]
            target = root / "test-artifacts" / f"{stage}-{context.step.get('shot_id') or 'project'}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"stage": stage}), encoding="utf-8")
            return [ArtifactDraft.from_path(stage, target, {})]
        return run


@pytest.fixture
def fake_backend():
    return FakeProductionBackend()


@pytest.fixture
def client(tmp_path, fake_backend, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repository = JobRepository(OrchestrationDatabase(tmp_path / "jobs.db"))
    runner = ProductionStepRunner(repository, adapters={stage.key: fake_backend.handler(stage.key) for stage in STAGES})
    worker = DurableWorker(repository, runner, retry_delays=[0, 0, 0], sleep=lambda _: None)
    app = FastAPI()
    app.state.job_service = JobService(repository, runner)
    app.state.test_worker = worker
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def project_input(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("第一章\n少年推开门。", encoding="utf-8")
    return {
        "project_id": "integration-project", "input_path": str(source), "input_type": "novel",
        "mode": "automatic", "shot_duration": 5, "width": 320, "height": 256,
        "fps": 24, "options": {}, "idempotency_key": f"integration-{uuid.uuid4()}",
        "project_dir": tmp_path / "projects" / "integration-project",
    }


@pytest.fixture
def wait_for_status():
    def wait(client, job_id, expected, limit=80):
        for _ in range(limit):
            client.app.state.test_worker.run_once()
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] == expected:
                return job
        raise AssertionError(f"job {job_id} did not reach {expected}")
    return wait


@pytest.fixture
def probe_video():
    def probe(path):
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(path),
        ], check=True, capture_output=True, text=True)
        return {"duration": float(json.loads(result.stdout)["format"]["duration"])}
    return probe
```

- [ ] **Step 2: Write a failing explicit-failure integration test**

Create `tests/integration/test_real_pipeline_contract.py`:

```python
def test_comfy_failure_stops_at_video_without_creating_substitute(
    client, fake_backend, project_input, wait_for_status
):
    fake_backend.fail_stage = "shot_video"
    payload = {key: value for key, value in project_input.items() if key != "project_dir"}
    job = client.post("/api/jobs", json=payload).json()
    wait_for_status(client, job["id"], "failed")
    restored = client.get(f"/api/jobs/{job['id']}").json()
    assert restored["current_stage"] == "shot_video"
    assert restored["steps"][-1]["error_code"] == "COMFY_NO_OUTPUT"
    assert not list(project_input["project_dir"].rglob("*fallback*"))
```

- [ ] **Step 3: Write a failing resume-only-current-step test**

Create `tests/integration/test_pipeline_resume.py`:

```python
def test_fix_and_continue_reuses_completed_artifacts(
    client, fake_backend, project_input, wait_for_status, probe_video
):
    fake_backend.fail_stage = "shot_video"
    payload = {key: value for key, value in project_input.items() if key != "project_dir"}
    job = client.post("/api/jobs", json=payload).json()
    wait_for_status(client, job["id"], "failed")
    calls_before = list(fake_backend.calls)
    fake_backend.fail_stage = None
    client.post(f"/api/jobs/{job['id']}/retry", json={"step_id": None, "comment": "workflow fixed"})
    wait_for_status(client, job["id"], "completed")
    calls_after = fake_backend.calls[len(calls_before):]
    assert all(call["stage"] != "first_frame" for call in calls_after)
    final = client.get(f"/api/jobs/{job['id']}").json()["final_video"]
    assert probe_video(final)["duration"] >= 5
```

- [ ] **Step 4: Run the integration tests**

```powershell
python -m pytest tests/integration/test_real_pipeline_contract.py tests/integration/test_pipeline_resume.py -q
```

Expected: the first scenario fails at the real fault without substitute files; the second completes after retry without rerunning first-frame generation.

- [ ] **Step 5: Run all backend tests**

```powershell
python -m pytest -q
```

Expected: all repository tests pass. Any test that still expects local fallback output has been removed or rewritten to assert explicit failure.

- [ ] **Step 6: Commit end-to-end production coverage**

```powershell
git add tests backend/production backend/pipeline_v5.py backend/composer.py backend/scheduler/novel.py
git commit -m "test: verify real V5 failure and checkpoint resume"
```

## Plan verification checkpoint

Run:

```powershell
python -m pytest tests/orchestration tests/api tests/production tests/integration -q
rg -n "used local|local.*fallback|return video_paths\[0\]" backend/pipeline_v5.py backend/routes/pipeline.py
```

Expected:

- all tests pass;
- the search returns no production fallback or first-clip substitution paths;
- a valid 5–15 second shot is generated at the exact requested resolution;
- a missing node, missing model, unavailable ComfyUI or invalid output stops the job on the failing step;
- repair and retry starts from the failed step and preserves upstream artifacts;
- final completion requires a validated, decodable movie containing every planned shot.
