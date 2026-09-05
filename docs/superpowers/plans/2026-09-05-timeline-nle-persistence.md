# v0.10 Timeline / NLE Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder timeline with a persisted non-destructive NLE whose immutable Snapshots pass formal QC and compile deterministically into the existing compose/export runtime.

**Architecture:** Add a focused `backend/timeline/` domain on top of the existing `OrchestrationDatabase` and Project Asset registry. Draft mutations are typed, transactional semantic operations with optimistic revision checks; Snapshots and Composition Specs are immutable; the existing `JobService`, Worker, and FFmpeg path remain the sole render authority. The frontend adds typed Timeline API/store modules and renders backend-authoritative Draft state.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLite/WAL, pytest, React 18, TypeScript 5.5, Zustand 5, Vitest 4, Vite 8.

**Spec:** `docs/superpowers/specs/2026-09-05-timeline-nle-persistence-design.md`

## Global Constraints

- Persist Timeline time at `timebase_hz = 1_000_000`; convert FPS with integer/rational arithmetic only. Floating-point seconds are display/input conveniences, never persisted authority.
- A video frame index maps to ticks using deterministic integer half-up rounding; every video edit is normalized with the same helper before persistence.
- `timeline_snapshots` and `timeline_composition_specs` are immutable after insert.
- Clips pin concrete Artifact IDs and versions. A newer generated Artifact never silently replaces a Timeline Clip.
- `video.main` is magnetic. Ordinary gaps are rejected and overlap is legal only when an explicit Transition validates it.
- Every Draft mutation carries `expected_revision`; stale mutation requests fail with HTTP 409 and never overwrite newer state.
- Undo/Redo revisions remain monotonically increasing.
- Formal QC and review gates cannot be bypassed through Timeline routes.
- Timeline never invokes FFmpeg directly; render execution remains in the existing Job/Worker/FFmpeg chain.
- Existing one-click production remains compatible. A project with no Timeline continues using the current production defaults and export path; Timeline bootstrap never overwrites an existing edited Draft.
- v0.10 UI exposes V1, dialogue, BGM/SFX, and subtitles only. V2/V3 UI, picture-in-picture, nested sequences, multicam, speed ramps, adjustment layers, effect graphs, collaboration, and cloud sync remain out of scope.

---

## File Structure

### New backend domain

- `backend/timeline/__init__.py` — Timeline package exports only.
- `backend/timeline/models.py` — Pydantic Timeline entities, typed operation requests/results, Snapshot/QC/export API schemas.
- `backend/timeline/timebase.py` — deterministic integer tick/frame conversion and snapping helpers.
- `backend/timeline/media.py` — Artifact media identity resolution, duration probing, path/SHA verification.
- `backend/timeline/repository.py` — Timeline SQLite reads/writes only; no editing policy.
- `backend/timeline/preflight.py` — cheap structural Draft validation and newer-Artifact notices.
- `backend/timeline/service.py` — transactional edit engine, optimistic concurrency, ripple/link/split/trim operations, Undo/Redo, checkpoints, Snapshot creation.
- `backend/timeline/qc.py` — immutable-Snapshot QC attempts and effective QC state.
- `backend/timeline/compiler.py` — deterministic Snapshot + output profile to Canonical Composition Spec compiler.
- `backend/timeline/runtime.py` — read-only Worker seam for loading verified Composition Specs and recording timeline export artifact binding.
- `backend/timeline/export_service.py` — QC-gated idempotent export orchestration into `JobService`.
- `backend/timeline/waveform.py` — FFmpeg-based mono peak extraction and SHA-keyed waveform cache.
- `backend/timeline/routes.py` — Timeline lifecycle/edit/Snapshot/QC/export/waveform FastAPI routes.

### Backend files modified at integration seams

- `backend/orchestration/database.py` — Timeline schema, indexes, foreign keys, immutability triggers.
- `backend/orchestration/schemas.py` — add frozen Timeline provenance to `JobSettings`.
- `backend/orchestration/service.py` — add a compose/export-only Timeline Job constructor without changing legacy production Jobs.
- `backend/orchestration/worker.py` — composition stage consumes a verified Timeline Composition Spec when Timeline provenance is present; legacy branch remains unchanged.
- `backend/main.py` — construct Timeline services and mount Timeline router.
- `.github/workflows/unified-studio-ci.yml` — include Timeline backend/tests in triggers, syntax checks, and contract tests.

### New backend tests

- `tests/timeline/test_timebase.py`
- `tests/timeline/test_repository.py`
- `tests/timeline/test_bootstrap_routes.py`
- `tests/timeline/test_edit_operations.py`
- `tests/timeline/test_undo_redo.py`
- `tests/timeline/test_transitions_replacement.py`
- `tests/timeline/test_snapshots.py`
- `tests/timeline/test_qc.py`
- `tests/timeline/test_compiler.py`
- `tests/timeline/test_export.py`
- `tests/timeline/test_waveform.py`

### Frontend files

- `frontend/src/types/timeline.ts` — Timeline API/domain types.
- `frontend/src/api/timeline.ts` — typed Timeline endpoints.
- `frontend/src/state/timelineStore.ts` — project-scoped Draft/Snapshot state, debounced operation queue, revision conflict recovery, critical flush.
- `frontend/src/studio/timeline/TimelineEditor.tsx` — ruler/playhead/tracks/editor interactions.
- `frontend/src/studio/timeline/TimelineTrack.tsx` — real Clip geometry and pointer interaction.
- `frontend/src/studio/timeline/TimelineInspector.tsx` — Clip/audio/subtitle/transition inspector.
- `frontend/src/studio/timeline/TimelineSnapshotPanel.tsx` — Draft preflight, Snapshot QC, export state.
- `frontend/src/styles/timeline.css` — focused NLE styling.
- `frontend/src/studio/TimelineQcWorkspace.tsx` — host the real NLE while preserving preview/problem-job context.

### New/updated frontend tests

- `frontend/src/state/timelineStore.test.ts`
- `frontend/src/studio/TimelineQcWorkspace.test.tsx`
- `frontend/src/studio/TimelineExportGate.test.tsx`
- `frontend/src/studio/TimelineEditor.test.tsx`
- `frontend/src/studio/TimelineSnapshotFlow.test.tsx`

---

## Slice 1 — Timeline Domain Foundation

### Task 1: Add exact timebase helpers and Timeline schema

**Files:**
- Create: `backend/timeline/__init__.py`
- Create: `backend/timeline/timebase.py`
- Modify: `backend/orchestration/database.py`
- Test: `tests/timeline/test_timebase.py`
- Test: `tests/timeline/test_repository.py`

**Interfaces:**
- Produces: `frame_index_to_tick(frame_index: int, *, ticks_per_second: int, fps_num: int, fps_den: int) -> int`
- Produces: `tick_to_nearest_frame_index(tick: int, *, ticks_per_second: int, fps_num: int, fps_den: int) -> int`
- Produces: `snap_video_tick(tick: int, *, ticks_per_second: int, fps_num: int, fps_den: int) -> int`
- Produces: all Timeline tables from the approved spec plus immutability triggers for `timeline_snapshots` and `timeline_composition_specs`.

- [ ] **Step 1: Write failing timebase tests**

```python
from backend.timeline.timebase import frame_index_to_tick, snap_video_tick


def test_24fps_frame_mapping_is_deterministic_without_float():
    assert frame_index_to_tick(0, ticks_per_second=1_000_000, fps_num=24, fps_den=1) == 0
    assert frame_index_to_tick(1, ticks_per_second=1_000_000, fps_num=24, fps_den=1) == 41667
    assert frame_index_to_tick(24, ticks_per_second=1_000_000, fps_num=24, fps_den=1) == 1_000_000
    assert snap_video_tick(41660, ticks_per_second=1_000_000, fps_num=24, fps_den=1) == 41667
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest -q tests/timeline/test_timebase.py --maxfail=1`

Expected: FAIL because `backend.timeline.timebase` does not exist.

- [ ] **Step 3: Implement deterministic integer frame mapping**

```python
def _round_half_up(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("timebase values must be non-negative and denominator positive")
    return (numerator * 2 + denominator) // (2 * denominator)


def frame_index_to_tick(frame_index: int, *, ticks_per_second: int, fps_num: int, fps_den: int) -> int:
    if frame_index < 0 or ticks_per_second <= 0 or fps_num <= 0 or fps_den <= 0:
        raise ValueError("invalid frame/timebase values")
    return _round_half_up(frame_index * ticks_per_second * fps_den, fps_num)


def tick_to_nearest_frame_index(tick: int, *, ticks_per_second: int, fps_num: int, fps_den: int) -> int:
    if tick < 0:
        raise ValueError("tick must be non-negative")
    return _round_half_up(tick * fps_num, ticks_per_second * fps_den)


def snap_video_tick(tick: int, *, ticks_per_second: int, fps_num: int, fps_den: int) -> int:
    frame = tick_to_nearest_frame_index(
        tick, ticks_per_second=ticks_per_second, fps_num=fps_num, fps_den=fps_den
    )
    return frame_index_to_tick(
        frame, ticks_per_second=ticks_per_second, fps_num=fps_num, fps_den=fps_den
    )
```

- [ ] **Step 4: Write schema/immutability tests**

```python
def test_timeline_schema_contains_all_approved_tables(db):
    expected = {
        "timelines", "timeline_drafts", "timeline_tracks", "timeline_clips",
        "timeline_link_groups", "timeline_transitions", "timeline_subtitle_cues",
        "timeline_operations", "timeline_checkpoints", "timeline_snapshots",
        "timeline_snapshot_qc_runs", "timeline_composition_specs", "timeline_export_bindings",
    }
    with db.connect() as conn:
        actual = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert expected <= actual


def test_snapshot_payload_cannot_be_updated(db, inserted_snapshot):
    with pytest.raises(sqlite3.IntegrityError, match="immutable timeline snapshot"):
        with db.transaction() as conn:
            conn.execute("UPDATE timeline_snapshots SET state_json='{}' WHERE id=?", (inserted_snapshot,))
```

- [ ] **Step 5: Add Timeline tables, indexes, foreign keys, and immutability triggers**

Add the approved columns verbatim from the spec. Add unique/index constraints for project Timeline lookup, Draft sequence, clip track ordering, Snapshot number, QC attempt, Composition Spec SHA, and export binding lookup. Add `BEFORE UPDATE` triggers that `RAISE(ABORT, 'immutable timeline snapshot')` and `RAISE(ABORT, 'immutable timeline composition spec')`.

- [ ] **Step 6: Run Slice 1 foundation tests**

Run: `python -m pytest -q tests/timeline/test_timebase.py tests/timeline/test_repository.py --maxfail=1`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/timeline/__init__.py backend/timeline/timebase.py backend/orchestration/database.py tests/timeline/test_timebase.py tests/timeline/test_repository.py
git commit -m "feat(timeline): add NLE persistence foundation"
```

### Task 2: Add typed models, media identity resolver, repository, bootstrap, and lifecycle routes

**Files:**
- Create: `backend/timeline/models.py`
- Create: `backend/timeline/media.py`
- Create: `backend/timeline/repository.py`
- Create: `backend/timeline/preflight.py`
- Create: `backend/timeline/service.py`
- Create: `backend/timeline/routes.py`
- Modify: `backend/main.py`
- Test: `tests/timeline/test_repository.py`
- Test: `tests/timeline/test_bootstrap_routes.py`

**Interfaces:**
- Produces: `TimelineRepository(db: OrchestrationDatabase, projects_root: str | Path = "projects")`
- Produces: `MediaIdentityResolver.resolve_artifact(artifact_id: int) -> MediaIdentity`
- Produces: `TimelineService.initialize_project(project_id: str) -> TimelineDraftView`
- Produces: `TimelineService.get_project_timeline(project_id: str) -> TimelineSummary | None`
- Produces: lifecycle routes `GET /api/projects/{project_id}/timeline`, `POST /api/projects/{project_id}/timeline/initialize`, `GET /api/timelines/{timeline_id}/draft`.

- [ ] **Step 1: Write failing bootstrap tests**

```python
def test_initialize_orders_active_video_assets_by_production_plan(client, project_with_shots):
    response = client.post(f"/api/projects/{project_with_shots}/timeline/initialize")
    assert response.status_code == 201
    draft = response.json()
    v1 = next(track for track in draft["tracks"] if track["role"] == "video.main")
    assert [clip["shot_id"] for clip in v1["clips"]] == ["shot_001", "shot_002"]
    assert draft["revision"] == 0


def test_initialize_is_idempotent_and_never_overwrites_existing_draft(client, project_with_shots):
    first = client.post(f"/api/projects/{project_with_shots}/timeline/initialize").json()
    second = client.post(f"/api/projects/{project_with_shots}/timeline/initialize").json()
    assert second["timeline_id"] == first["timeline_id"]
    assert second["draft_id"] == first["draft_id"]
```

- [ ] **Step 2: Run bootstrap tests and verify RED**

Run: `python -m pytest -q tests/timeline/test_bootstrap_routes.py --maxfail=1`

Expected: FAIL with 404 or missing Timeline router.

- [ ] **Step 3: Define typed Timeline API models**

Use Pydantic models with exact persisted integer tick fields. Define `TimelineTrackView`, `TimelineClipView`, `TimelineSubtitleCueView`, `TimelineTransitionView`, `TimelineDraftView`, `TimelineSummary`, `TimelinePreflight`, `TimelineSnapshotView`, `TimelineQcRunView`, `TimelineExportRequest`, and `TimelineExportResult`. Include denormalized `shot_id`/`scene_id` in Clip views from Artifact lineage for UI traceability, but keep Artifact ID/version as the pinned source identity.

- [ ] **Step 4: Implement media identity resolution**

`MediaIdentityResolver` must read the Artifact row, resolve its path under the owning project, reject missing files, use the stored Artifact SHA as the expected identity, verify SHA when `verify_sha=True`, and determine duration in ticks from Artifact metadata when a positive duration is present. If duration metadata is absent, invoke local `ffprobe` with JSON output and convert the returned rational/decimal duration to ticks using `Decimal`, never binary float. Return a frozen `MediaIdentity(artifact_id, version, path, sha256, duration_tick, kind, shot_id, scene_id)`.

- [ ] **Step 5: Implement repository bootstrap persistence**

Bootstrap creates one Timeline and Draft, V1/A1/A2/S1 tracks, and active source Clips in a single `BEGIN IMMEDIATE` transaction. V1 source ordering follows `projects/<project_id>/production_plan.json` shot order first and deterministic Artifact ID order for unmatched media. Multiple active versions for the same shot select the highest version only for initial bootstrap. Existing Timeline rows are returned unchanged.

- [ ] **Step 6: Wire lifecycle routes and `app.state.timeline_service`**

Create `TimelineRepository` and `TimelineService` in `backend/main.py`, store them on `app.state`, and mount `backend.timeline.routes.router`. Routes translate missing Timeline to 404, media integrity/validation to 409/422 as defined by typed exceptions, and return backend-authoritative Draft views.

- [ ] **Step 7: Run repository and lifecycle tests**

Run: `python -m pytest -q tests/timeline/test_repository.py tests/timeline/test_bootstrap_routes.py --maxfail=1`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/timeline backend/main.py tests/timeline/test_repository.py tests/timeline/test_bootstrap_routes.py
git commit -m "feat(timeline): bootstrap persisted project timelines"
```

---

## Slice 2 — Core Editing Engine

### Task 3: Implement typed core editing operations with atomic magnetic ripple semantics

**Files:**
- Modify: `backend/timeline/models.py`
- Modify: `backend/timeline/repository.py`
- Modify: `backend/timeline/preflight.py`
- Modify: `backend/timeline/service.py`
- Modify: `backend/timeline/routes.py`
- Test: `tests/timeline/test_edit_operations.py`

**Interfaces:**
- Produces: discriminated `TimelineOperation` union with `MOVE_CLIP`, `TRIM_CLIP`, `SPLIT_CLIP`, `REMOVE_CLIP`, `LINK_CLIPS`, `UNLINK_CLIPS`.
- Produces: `TimelineService.apply_operation(timeline_id: str, request: TimelineOperationRequest) -> TimelineMutationResult`.
- Consumes: Task 1 timebase helpers and Task 2 repository/media resolver.

- [ ] **Step 1: Write failing magnetic operation tests**

```python
def test_move_v1_is_reorder_not_free_position(service, timeline):
    result = service.apply_operation(
        timeline.id,
        TimelineOperationRequest(
            expected_revision=0,
            operation={"type": "MOVE_CLIP", "clip_id": "clip-c", "insert_before_clip_id": "clip-a"},
        ),
    )
    assert [c.id for c in result.draft.main_video_clips] == ["clip-c", "clip-a", "clip-b"]
    assert result.draft.main_video_clips[1].timeline_start_tick == result.draft.main_video_clips[0].end_tick


def test_stale_revision_fails_without_partial_write(service, timeline):
    service.apply_operation(timeline.id, first_request(expected_revision=0))
    with pytest.raises(TimelineRevisionConflict):
        service.apply_operation(timeline.id, second_request(expected_revision=0))
```

Also add focused tests for right/left trim ripple, trim source overflow rejection, exact-frame split, linked move, linked split, ripple delete, locked Clip/Track rejection, and no partial writes after validation failure.

- [ ] **Step 2: Run editing tests and verify RED**

Run: `python -m pytest -q tests/timeline/test_edit_operations.py --maxfail=1`

Expected: FAIL because operation models/service entry point are absent.

- [ ] **Step 3: Define discriminated operation models**

```python
TimelineOperation = Annotated[
    MoveClipOperation
    | TrimClipOperation
    | SplitClipOperation
    | RemoveClipOperation
    | LinkClipsOperation
    | UnlinkClipsOperation,
    Field(discriminator="type"),
]

class TimelineOperationRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    operation: TimelineOperation
```

Use semantic payloads: V1 move uses `insert_before_clip_id`/`insert_after_clip_id`, not a client-authored persisted start tick. Video split/trim ticks are normalized through `snap_video_tick` before mutation.

- [ ] **Step 4: Implement one-transaction operation application**

Inside `BEGIN IMMEDIATE`: verify Timeline/Draft and exact `expected_revision`; load all affected rows; reject locked/invalid source ranges; compute the complete mutation and inverse payload before writes; apply linked-member deltas; renormalize magnetic V1 start ticks; append one operation log row; increment Draft revision exactly once. On any exception the transaction rolls back.

- [ ] **Step 5: Add structural preflight to each mutation response**

`preflight_draft()` must report codes for missing Artifact, invalid range, V1 gap, illegal overlap, broken Transition, broken Link Group, invalid subtitle interval, source overflow, and newer Artifact availability. It is informational except hard invariants, which must reject the transaction.

- [ ] **Step 6: Add `POST /api/timelines/{timeline_id}/operations`**

Return `TimelineMutationResult(revision, operation_seq, draft, preflight)`. Map `TimelineRevisionConflict` to HTTP 409 with structured code `TIMELINE_REVISION_CONFLICT`; invariant violations use HTTP 422 with their stable code.

- [ ] **Step 7: Run editing tests**

Run: `python -m pytest -q tests/timeline/test_edit_operations.py --maxfail=1`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/timeline tests/timeline/test_edit_operations.py
git commit -m "feat(timeline): add transactional NLE edit operations"
```

### Task 4: Add persistent Undo/Redo and checkpoints

**Files:**
- Modify: `backend/timeline/repository.py`
- Modify: `backend/timeline/service.py`
- Modify: `backend/timeline/routes.py`
- Test: `tests/timeline/test_undo_redo.py`

**Interfaces:**
- Produces: `TimelineService.undo(timeline_id: str, expected_revision: int) -> TimelineMutationResult`
- Produces: `TimelineService.redo(timeline_id: str, expected_revision: int) -> TimelineMutationResult`
- Produces: `TimelineRepository.save_checkpoint(draft_id: str, operation_seq: int, revision: int, state_json: str, state_sha256: str)`.

- [ ] **Step 1: Write RED tests for persistent history**

```python
def test_undo_restores_state_but_revision_keeps_increasing(service, timeline):
    moved = service.apply_operation(timeline.id, move_request(expected_revision=0))
    undone = service.undo(timeline.id, expected_revision=moved.revision)
    assert undone.revision == moved.revision + 1
    assert clip_order(undone.draft) == ["clip-a", "clip-b", "clip-c"]


def test_new_edit_after_undo_abandons_redo_branch(service, timeline):
    moved = service.apply_operation(timeline.id, move_request(expected_revision=0))
    undone = service.undo(timeline.id, expected_revision=moved.revision)
    service.apply_operation(timeline.id, trim_request(expected_revision=undone.revision))
    with pytest.raises(TimelineRedoUnavailable):
        service.redo(timeline.id, expected_revision=undone.revision + 1)
```

Also test that a new service/repository instance after simulated refresh can still Undo from persisted history.

- [ ] **Step 2: Run Undo/Redo tests and verify RED**

Run: `python -m pytest -q tests/timeline/test_undo_redo.py --maxfail=1`

- [ ] **Step 3: Implement history cursor and branch abandonment**

Store forward and inverse semantic payloads. Undo applies the active head inverse in the same transaction and advances revision; Redo reapplies only the current eligible redo operation and advances revision. A new normal edit after Undo changes the old redo branch rows to `branch_state='abandoned'` before appending the new operation.

- [ ] **Step 4: Implement checkpoint policy**

Create a canonical complete Draft state checkpoint after every 50 committed semantic edits, before Snapshot creation, and after a batch replacement/ripple operation that affects at least 20 persisted entities. Hash with `sha256(canonical_json.encode("utf-8"))`.

- [ ] **Step 5: Add Undo/Redo routes**

Add `POST /api/timelines/{timeline_id}/undo` and `/redo` with body `{ "expected_revision": N }`. Apply the same 409 revision-conflict contract as normal operations.

- [ ] **Step 6: Run Undo/Redo tests**

Run: `python -m pytest -q tests/timeline/test_undo_redo.py --maxfail=1`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/timeline tests/timeline/test_undo_redo.py
git commit -m "feat(timeline): persist undo redo history"
```

---

## Slice 3 — Transitions, Subtitles, Artifact Upgrades, and Real Timeline UI

### Task 5: Add transitions, subtitle operations, Artifact replacement, and waveform backend

**Files:**
- Modify: `backend/timeline/models.py`
- Modify: `backend/timeline/service.py`
- Modify: `backend/timeline/preflight.py`
- Create: `backend/timeline/waveform.py`
- Modify: `backend/timeline/routes.py`
- Test: `tests/timeline/test_transitions_replacement.py`
- Test: `tests/timeline/test_waveform.py`

**Interfaces:**
- Adds operations: `ADD_TRANSITION`, `UPDATE_TRANSITION`, `REMOVE_TRANSITION`, `ADD_SUBTITLE`, `UPDATE_SUBTITLE`, `REMOVE_SUBTITLE`, `REPLACE_ARTIFACT_VERSION`.
- Produces: `WaveformService.get_or_build(project_id: str, artifact_id: int, bins: int = 512) -> WaveformEnvelope`.

- [ ] **Step 1: Write RED transition/replacement tests**

Test explicit crossfade authorizes exactly its overlap, ordinary V1 overlap is rejected, insufficient handles return `TRANSITION_HANDLE_INSUFFICIENT`, subtitle end must exceed start, single replacement preserves timing, too-short replacement returns `replacement_media_too_short`, and replace-all rolls back every Clip if one target is incompatible.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest -q tests/timeline/test_transitions_replacement.py --maxfail=1`

- [ ] **Step 3: Implement controlled transition overlap**

Calculate available left/right handles from frozen source duration and current `source_in_tick`/`source_out_tick`. `ADD_TRANSITION` may shift the adjacent Clip boundaries/start positions only as required by the explicit transition and then records a `timeline_transitions` row. No other V1 operation may leave overlap.

- [ ] **Step 4: Implement first-class subtitle operations**

Persist subtitle text, speaker, timing, and style JSON in `timeline_subtitle_cues`; do not hide text edits inside Clip metadata. Linked subtitles move by the same delta as their anchor group unless explicitly unlinked.

- [ ] **Step 5: Implement atomic Artifact replacement**

Resolve the requested new Artifact identity before mutation. For each target Clip require `new_media.duration_tick >= source_out_tick`. Preserve Timeline start/duration/source range/Link Group. Replace one or all requested matching references in one immediate transaction; do not auto-trim.

- [ ] **Step 6: Write RED waveform tests**

Test cache path is SHA-keyed, repeated request reuses the cache, changed Artifact SHA builds a different cache, and response contains exactly the requested maximum bins with normalized peak values in `[0, 1]`.

- [ ] **Step 7: Implement waveform extraction**

Invoke local FFmpeg as `ffmpeg -v error -i <source> -vn -ac 1 -ar 8000 -f f32le pipe:1`, parse little-endian float32 samples, calculate absolute maxima per deterministic bucket, and save JSON under `projects/<project_id>/.timeline_cache/waveforms/<artifact_sha256>-<bins>.json`. Never store PCM/waveform arrays in SQLite.

- [ ] **Step 8: Add waveform endpoint and run tests**

Add `GET /api/timelines/{timeline_id}/artifacts/{artifact_id}/waveform?bins=512` after verifying the Artifact belongs to the Timeline project.

Run: `python -m pytest -q tests/timeline/test_transitions_replacement.py tests/timeline/test_waveform.py --maxfail=1`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/timeline tests/timeline/test_transitions_replacement.py tests/timeline/test_waveform.py
git commit -m "feat(timeline): add transitions subtitles and media upgrades"
```

### Task 6: Add typed frontend API/store with debounced persistence and conflict recovery

**Files:**
- Create: `frontend/src/types/timeline.ts`
- Create: `frontend/src/api/timeline.ts`
- Create: `frontend/src/state/timelineStore.ts`
- Test: `frontend/src/state/timelineStore.test.ts`

**Interfaces:**
- Produces: `timelineApi.getProjectTimeline`, `initialize`, `getDraft`, `applyOperation`, `undo`, `redo`, `createSnapshot`, `listSnapshots`, `runQc`, `getQc`, `exportSnapshot`, `getWaveform`.
- Produces: `useTimelineStore` state with `loadProject(projectId)`, `scheduleOperation(operation)`, `flushPending()`, `commitCritical(operation)`, `undo()`, `redo()`, `createSnapshot()`, `runQc(snapshotId)`, `exportSnapshot(snapshotId, outputProfile)`.

- [ ] **Step 1: Write RED store tests**

```ts
it("keeps pointer-end edits local until the debounce expires, then commits once", async () => {
  store.getState().scheduleOperation(moveClip);
  expect(timelineApi.applyOperation).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(200);
  expect(timelineApi.applyOperation).toHaveBeenCalledTimes(1);
});

it("flushes queued edits before snapshot creation", async () => {
  store.getState().scheduleOperation(trimClip);
  await store.getState().createSnapshot();
  expect(timelineApi.applyOperation).toHaveBeenCalledBefore(timelineApi.createSnapshot as any);
});
```

Also test a 409 `ApiError` reloads authoritative Draft and surfaces a conflict flag instead of retrying the stale operation automatically; project switching must ignore late responses from the previous project.

- [ ] **Step 2: Run store tests and verify RED**

Run from `frontend`: `npm test -- --run src/state/timelineStore.test.ts`

- [ ] **Step 3: Define frontend Timeline types matching backend names exactly**

Use integer `number` ticks and exact operation discriminators. Do not invent frontend-only persisted fields. Keep transient `selectedClipId`, `playheadTick`, `zoom`, and drag preview state outside API types.

- [ ] **Step 4: Implement typed Timeline API**

Use the existing `request<T>()` wrapper. All paths include the `/api`-relative routes from the approved spec. `applyOperation` sends `{expected_revision, operation}` and consumes the backend authoritative `draft` and `preflight` result.

- [ ] **Step 5: Implement serialized 200 ms operation debounce**

Normal pointer-end move/trim operations enter a FIFO queue and flush after 200 ms. Consecutive unflushed MOVE operations for the same Clip may coalesce to the latest semantic destination; different operation types never reorder. `split`, `delete`, `link/unlink`, transition edits, subtitle commits, Artifact replacement, Snapshot, QC/export, project switch, and explicit Undo/Redo first `await flushPending()`.

- [ ] **Step 6: Implement 409 recovery**

On `ApiError.status === 409` with code `TIMELINE_REVISION_CONFLICT`, discard the stale queued request, re-fetch the Draft, replace local committed state, and set a user-visible conflict message. Do not silently replay the stale operation.

- [ ] **Step 7: Run frontend store tests and typecheck**

Run: `npm test -- --run src/state/timelineStore.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/timeline.ts frontend/src/api/timeline.ts frontend/src/state/timelineStore.ts frontend/src/state/timelineStore.test.ts
git commit -m "feat(timeline): add typed frontend NLE state"
```

### Task 7: Replace placeholder lanes with the real V1/A1/A2/S1 editor

**Files:**
- Create: `frontend/src/studio/timeline/TimelineEditor.tsx`
- Create: `frontend/src/studio/timeline/TimelineTrack.tsx`
- Create: `frontend/src/studio/timeline/TimelineInspector.tsx`
- Create: `frontend/src/styles/timeline.css`
- Modify: `frontend/src/studio/TimelineQcWorkspace.tsx`
- Test: `frontend/src/studio/TimelineQcWorkspace.test.tsx`
- Test: `frontend/src/studio/TimelineEditor.test.tsx`

**Interfaces:**
- Consumes: Task 6 `useTimelineStore` and typed operations.
- Produces: real ruler/playhead, V1/A1/A2/S1 rows, Clip selection, magnetic V1 drag/reorder, trim handles, split at playhead, ripple delete, link/unlink, snapping, real preview selection.

- [ ] **Step 1: Write RED tests proving placeholders are gone**

```tsx
it("renders real backend tracks instead of decorative placeholder lanes", async () => {
  render(<TimelineQcWorkspace />);
  expect(await screen.findByTestId("timeline-track-video.main")).toBeInTheDocument();
  expect(screen.getByTestId("timeline-clip-clip-001")).toHaveTextContent("shot_001");
  expect(document.querySelectorAll(".timeline-lane__blocks > i")).toHaveLength(0);
});
```

Add tests that drag preview does not call the API on pointer move, pointer up schedules exactly one semantic MOVE, trim calls one TRIM operation, split uses the current playhead, and backend-returned geometry replaces optimistic geometry.

- [ ] **Step 2: Run editor tests and verify RED**

Run: `npm test -- --run src/studio/TimelineQcWorkspace.test.tsx src/studio/TimelineEditor.test.tsx`

- [ ] **Step 3: Implement deterministic geometry helpers in the editor**

Convert persisted ticks to CSS positions using a local pixels-per-second zoom scalar only for rendering; never persist those floats. Use `snap_video_tick` equivalent frontend rational math for preview, but accept backend normalized ticks as final authority.

- [ ] **Step 4: Implement real V1/A1/A2/S1 rendering and interactions**

V1 drag chooses semantic insertion before/after another Clip. Trim handles preview source range and duration, then schedule one TRIM on pointer release. Split/delete/link/unlink are critical immediate operations after queue flush. Free audio/subtitle tracks keep absolute tick placement. Linked members display a link indicator and move preview by shared delta.

- [ ] **Step 5: Preserve real media preview and project-switch race safety**

Selecting a Timeline Clip resolves its pinned Artifact media URL for preview. When `projectId` changes, cancel transient drag/selection, flush the previous project queue, and load/initialize the new project's Timeline without allowing old responses to overwrite it.

- [ ] **Step 6: Add focused Timeline CSS and import it from `TimelineQcWorkspace.tsx`**

Style track labels, ruler, playhead, real Clip widths, trim handles, link badges, warning badges, disabled/locked states, and horizontal scrolling. Keep existing Studio tokens; do not rewrite unrelated unified Studio CSS.

- [ ] **Step 7: Run editor tests, typecheck, and build**

Run: `npm test -- --run src/studio/TimelineQcWorkspace.test.tsx src/studio/TimelineEditor.test.tsx && npm run typecheck && npm run build`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/studio/TimelineQcWorkspace.tsx frontend/src/studio/timeline frontend/src/styles/timeline.css frontend/src/studio/TimelineQcWorkspace.test.tsx frontend/src/studio/TimelineEditor.test.tsx
git commit -m "feat(timeline): replace placeholder lanes with real NLE editor"
```

---

## Slice 4 — Immutable Snapshot and Formal QC

### Task 8: Freeze reproducible Snapshots and formal QC attempts

**Files:**
- Modify: `backend/timeline/repository.py`
- Modify: `backend/timeline/service.py`
- Create: `backend/timeline/qc.py`
- Modify: `backend/timeline/routes.py`
- Test: `tests/timeline/test_snapshots.py`
- Test: `tests/timeline/test_qc.py`

**Interfaces:**
- Produces: `TimelineService.create_snapshot(timeline_id: str) -> TimelineSnapshotView`
- Produces: `TimelineQcService.run(snapshot_id: str) -> TimelineQcRunView`
- Produces: `TimelineQcService.get_status(snapshot_id: str) -> TimelineQcStatusView`.

- [ ] **Step 1: Write RED Snapshot tests**

Test Snapshot state freezes complete tracks/clips/transitions/subtitles/timebase and each source `artifact_id`, `artifact_version`, resolved path identity, and SHA; repeated canonicalization of the same state gives the same `state_sha256`; modifying Draft afterward never changes the Snapshot row; direct SQL UPDATE is rejected by Task 1 trigger.

- [ ] **Step 2: Run Snapshot tests and verify RED**

Run: `python -m pytest -q tests/timeline/test_snapshots.py --maxfail=1`

- [ ] **Step 3: Implement canonical Snapshot creation**

Before insert, create a Draft checkpoint, run hard structural validation, resolve/verify every source Artifact identity, and serialize with `json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`. Allocate `snapshot_no` under `BEGIN IMMEDIATE`; insert exactly once; never update the Snapshot payload afterward.

- [ ] **Step 4: Write RED formal QC tests**

Test: latest required Artifact `quality_status` failed causes failed Snapshot QC; unreviewed/pending causes failed/non-exportable report; missing file or SHA mismatch records `stale`; passed sources plus structural integrity produce `passed`; each rerun creates attempt N+1 without changing Snapshot.

- [ ] **Step 5: Implement `TimelineQcService`**

Formal v0.10 QC reuses existing Artifact quality status/report evidence plus Timeline structural/media-integrity checks. It must not invent a parallel heavy vision model. Insert a `running` QC attempt, evaluate immutable Snapshot content, then update only the QC-run row to `passed`, `failed`, or `stale` with structured report codes. Snapshot rows remain untouched.

- [ ] **Step 6: Add Snapshot/QC routes**

Implement the approved Snapshot create/list/get routes and QC POST/GET routes. Exportability is derived from the latest valid QC attempt and a fresh source-integrity verification, not a mutable Snapshot flag.

- [ ] **Step 7: Run Snapshot/QC tests**

Run: `python -m pytest -q tests/timeline/test_snapshots.py tests/timeline/test_qc.py --maxfail=1`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/timeline tests/timeline/test_snapshots.py tests/timeline/test_qc.py
git commit -m "feat(timeline): add immutable snapshots and formal QC"
```

---

## Slice 5 — Deterministic Composition and Export Closure

### Task 9: Compile deterministic Composition Specs and create compose/export-only Jobs

**Files:**
- Create: `backend/timeline/compiler.py`
- Create: `backend/timeline/runtime.py`
- Create: `backend/timeline/export_service.py`
- Modify: `backend/timeline/routes.py`
- Modify: `backend/orchestration/schemas.py`
- Modify: `backend/orchestration/service.py`
- Modify: `backend/orchestration/worker.py`
- Modify: `backend/main.py`
- Test: `tests/timeline/test_compiler.py`
- Test: `tests/timeline/test_export.py`

**Interfaces:**
- Produces: `TimelineCompiler.compile(snapshot_id: str, output_profile: TimelineOutputProfile) -> TimelineCompositionSpecView`
- Produces: `JobService.create_timeline_export(data: JobCreate, settings: JobSettings) -> JobDetail` with exactly `composition_compose` and `export` steps.
- Produces: `TimelineExportService.export(snapshot_id: str, request: TimelineExportRequest) -> TimelineExportResult`.
- Produces: `load_timeline_composition_spec(db, composition_spec_id: str) -> dict[str, Any]` for Worker use.

- [ ] **Step 1: Write RED compiler determinism tests**

```python
def test_same_snapshot_and_output_profile_compile_to_identical_sha(compiler, snapshot_id):
    first = compiler.compile(snapshot_id, portrait_24fps())
    second = compiler.compile(snapshot_id, portrait_24fps())
    assert first.spec_sha256 == second.spec_sha256
    assert first.spec_json == second.spec_json


def test_output_profile_changes_spec_sha(compiler, snapshot_id):
    assert compiler.compile(snapshot_id, portrait_24fps()).spec_sha256 != compiler.compile(snapshot_id, landscape_24fps()).spec_sha256
```

Also test media path/SHA re-verification and exact integer/rational timing in the compiled schema.

- [ ] **Step 2: Run compiler tests and verify RED**

Run: `python -m pytest -q tests/timeline/test_compiler.py --maxfail=1`

- [ ] **Step 3: Implement canonical compiler**

Resolve the immutable Snapshot, verify source path/SHA, include `schema_version=1`, `compiler_version='timeline-compose/v1'`, timebase/FPS rational values, all output width/height/FPS values, duration, video/audio/subtitle tracks, transitions, Clip IDs, Artifact IDs/versions/SHAs, source paths, and integer timing. Canonically serialize and insert-or-return the immutable Composition Spec by Snapshot/SHA.

- [ ] **Step 4: Write RED export-gate/idempotency tests**

Test no QC, failed QC, stale QC, and pending required source evidence all block export; passed QC creates a Job with only `composition_compose` and `export`; second identical request returns the same running binding; a completed identical export returns the existing Artifact binding; Job settings freeze `timeline_id`, `snapshot_id`, `snapshot_no`, `state_sha256`, `composition_spec_id`, `composition_spec_sha256`, and compiler version.

- [ ] **Step 5: Add Timeline provenance to `JobSettings` and export-only Job constructor**

```python
class JobSettings(BaseModel):
    # existing fields unchanged
    timeline: dict[str, Any] = Field(default_factory=dict)
```

Refactor `JobService.create()` only enough to share a private `_create_with_stage_plan(...)`; keep legacy `create()` behavior/stage plan unchanged. Add `create_timeline_export()` that writes a Job with `input_type='timeline_snapshot'`, Timeline provenance, and stage plan:

```python
[
    {"stage_key": "composition_compose", "shot_id": ""},
    {"stage_key": "export", "shot_id": ""},
]
```

- [ ] **Step 6: Implement idempotent `TimelineExportService`**

Force fresh source-integrity verification and latest QC `passed`; compile/resolve the immutable spec; look up existing binding by `composition_spec_id`; return running/queued/retryable binding or successful Artifact when present; otherwise create one export-only Job and one binding transactionally. Never create a full AI generation pipeline from this endpoint.

- [ ] **Step 7: Add Worker Timeline composition seam without changing legacy behavior**

At `composition_compose`, if `settings["timeline"]["composition_spec_id"]` exists, call `load_timeline_composition_spec(self.repo.db, spec_id)`, verify its SHA matches frozen Job provenance, and pass that canonical track/clip/transition/audio/subtitle description into the existing FFmpeg composition implementation. If no Timeline provenance exists, execute the existing legacy `_run_composition` branch byte-for-byte in behavior. After Timeline export Artifact registration, call `record_timeline_export_artifact(...)` to bind Artifact ID to the export binding.

- [ ] **Step 8: Add `POST /api/timeline-snapshots/{snapshot_id}/export` and run tests**

Run: `python -m pytest -q tests/timeline/test_compiler.py tests/timeline/test_export.py tests/orchestration/test_stage_execution.py tests/orchestration/test_stage_execution_job_reset.py --maxfail=1`

Expected: PASS; existing stage-execution behavior remains green.

- [ ] **Step 9: Commit**

```bash
git add backend/timeline backend/orchestration/schemas.py backend/orchestration/service.py backend/orchestration/worker.py backend/main.py tests/timeline/test_compiler.py tests/timeline/test_export.py
git commit -m "feat(timeline): compile snapshots into production export jobs"
```

### Task 10: Complete transition/subtitle/version/Snapshot/QC/export UI

**Files:**
- Create: `frontend/src/studio/timeline/TimelineSnapshotPanel.tsx`
- Modify: `frontend/src/studio/timeline/TimelineEditor.tsx`
- Modify: `frontend/src/studio/timeline/TimelineInspector.tsx`
- Modify: `frontend/src/studio/TimelineQcWorkspace.tsx`
- Modify: `frontend/src/studio/TimelineExportGate.test.tsx`
- Create: `frontend/src/studio/TimelineSnapshotFlow.test.tsx`

**Interfaces:**
- Consumes: formal Snapshot/QC/export APIs from Tasks 8–9 and waveform/replacement APIs from Task 5.
- Produces: controlled transition UI, editable subtitle timing/text, waveform envelope rendering, newer-Artifact badge/replace actions, Snapshot creation/history, formal QC state, Snapshot-bound export.

- [ ] **Step 1: Rewrite export-gate tests against Snapshot QC**

Keep one explicit legacy test proving projects without a Timeline retain the existing v0.9 export behavior. Add Timeline-mode tests proving `not_run`, failed, and stale Snapshot QC disable export; `passed` enables export; Timeline export calls `timelineApi.exportSnapshot` and never `retryJob`/`resumeJob` for unrelated production Jobs.

- [ ] **Step 2: Write RED Snapshot flow tests**

Test queued edits flush before “创建版本”; Snapshot appears as `Snapshot #N`; QC status transitions render; source-integrity stale error is visible; export output profile values are sent to the formal export endpoint; Artifact upgrade badge offers current/all/keep and no replacement happens without a user action.

- [ ] **Step 3: Run UI flow tests and verify RED**

Run: `npm test -- --run src/studio/TimelineExportGate.test.tsx src/studio/TimelineSnapshotFlow.test.tsx`

- [ ] **Step 4: Implement Transition/Subtitle/Artifact upgrade inspector controls**

Only expose cut/default, crossfade, fade-to-black/from-black controls supported by v0.10. Disable unavailable transition durations using backend validation response. Subtitle editing commits text/timing as first-class operations. Display `vN → vN+1 available`; keep old version unless the user explicitly chooses replace-current or replace-all.

- [ ] **Step 5: Render waveform envelopes**

Fetch the SHA-keyed cached envelope only for visible audio Clips, draw lightweight SVG/canvas peaks, and never block Timeline edit availability if waveform extraction fails; show a non-blocking waveform warning instead.

- [ ] **Step 6: Implement Snapshot/QC/export panel**

Show Draft revision/dirty/pending-save indicator, structural preflight, Snapshot list, effective formal QC status, and export provenance. `创建版本`, QC, and export always await `flushPending()`. Export button is enabled only for selected Snapshot latest QC `passed` and no current integrity error.

- [ ] **Step 7: Run frontend Timeline tests, typecheck, and build**

Run:

```bash
npm test -- --run src/state/timelineStore.test.ts src/studio/TimelineQcWorkspace.test.tsx src/studio/TimelineEditor.test.tsx src/studio/TimelineExportGate.test.tsx src/studio/TimelineSnapshotFlow.test.tsx
npm run typecheck
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/studio frontend/src/state/timelineStore.ts frontend/src/api/timeline.ts frontend/src/types/timeline.ts frontend/src/styles/timeline.css
git commit -m "feat(timeline): close professional NLE snapshot workflow"
```

### Task 11: Extend CI and run final regression gates

**Files:**
- Modify: `.github/workflows/unified-studio-ci.yml`
- Test: all `tests/timeline/**` and Timeline frontend tests.

**Interfaces:**
- Produces: CI coverage for all v0.10 files and regression gates required before PR/merge.

- [ ] **Step 1: Write the CI path/syntax expectations before changing workflow**

The workflow must trigger on:

```yaml
- "backend/timeline/**"
- "tests/timeline/**"
- "backend/main.py"
```

in both PR and `master` push path filters, in addition to the existing paths.

- [ ] **Step 2: Extend backend syntax check**

Add every `backend/timeline/*.py` module plus existing orchestration/workspace integration files to the `python -m py_compile` command. Do not remove current files from the syntax gate.

- [ ] **Step 3: Extend backend contract tests**

Append:

```bash
python -m pytest -q tests/timeline \
  tests/workspace/test_project_assets.py \
  tests/workspace/test_director_settings.py \
  tests/workspace/test_director_runtime_binding.py \
  tests/workspace/test_production_template_repository.py \
  tests/workspace/test_production_template_compiler.py \
  tests/workspace/test_production_template_routes.py \
  tests/orchestration/test_project_template_job_resolution.py \
  tests/orchestration/test_template_provider_runtime.py \
  tests/orchestration/test_stage_execution.py \
  tests/orchestration/test_stage_execution_routes.py \
  tests/orchestration/test_stage_execution_job_reset.py \
  --disable-warnings --maxfail=1
```

- [ ] **Step 4: Run complete local backend regression**

Run: `python -m pytest -q tests/timeline tests/workspace tests/orchestration --disable-warnings --maxfail=1`

Expected: PASS.

- [ ] **Step 5: Run complete frontend quality gate**

From `frontend` run:

```bash
npm audit
npm run typecheck
npm test -- --run
npm run build
```

Expected: all commands succeed.

- [ ] **Step 6: Run explicit v0.10 acceptance scenarios**

Verify with automated integration tests or a deterministic test fixture:

```text
bootstrap existing project
→ reorder V1 shot
→ trim
→ split
→ edit subtitle
→ add crossfade
→ refresh/reload Draft
→ Undo still works
→ create immutable Snapshot
→ formal QC passes
→ export creates compose/export-only Job
→ Export Artifact metadata traces to exact Snapshot/spec SHA
```

and the fail-closed scenario:

```text
Snapshot QC passes
→ source media bytes are replaced externally
→ export re-verifies SHA
→ export is rejected
→ a new QC attempt records stale
→ no render Job is created
```

- [ ] **Step 7: Commit CI closure**

```bash
git add .github/workflows/unified-studio-ci.yml
git commit -m "ci: gate v0.10 timeline NLE contracts"
```

- [ ] **Step 8: Final verification before PR**

Record the exact feature-branch HEAD SHA, confirm no uncommitted generated files, then require both repository workflows that apply to this branch to be green before requesting merge. Do not claim v0.10 complete from local/unit tests alone when branch CI evidence is available.

---

## Self-Review Checklist

Before implementation is declared complete, verify every line below against the approved spec:

- [ ] All 13 approved Timeline persistence tables exist with the specified responsibilities.
- [ ] Snapshot and Composition Spec payloads cannot be mutated after insert.
- [ ] Time persistence uses integer ticks and rational FPS helpers only.
- [ ] V1 magnetic reorder/trim/delete remains contiguous except explicit Transition overlap.
- [ ] Link Groups preserve relative timing and unlink does not realign J/L cuts.
- [ ] Undo/Redo survives reload and revision always increases.
- [ ] Operation logging/checkpoints are persistent and redo branches are abandoned, not silently rewritten.
- [ ] New Artifact versions never alter Clips without explicit user replacement.
- [ ] Too-short replacement and insufficient transition handles fail without partial mutation.
- [ ] Draft preflight is lightweight and formal QC runs only against immutable Snapshot state.
- [ ] Snapshot QC/source integrity gates export and review gates remain authoritative.
- [ ] Compiler output is deterministic and all render-affecting output profile values participate in the spec SHA.
- [ ] Timeline export creates only compose/export execution, never the whole AI generation pipeline.
- [ ] Legacy one-click and no-Timeline projects remain compatible.
- [ ] Placeholder lanes are removed and V1/A1/A2/S1 render real persisted state.
- [ ] Debounced frontend operations flush before critical actions and stale revisions are never silently replayed.
- [ ] Waveform data is cache-only and never persisted as PCM/peak blobs in SQLite.
- [ ] No V2/V3 UI, nested sequences, multicam, effect graph, collaboration, or cloud-sync scope slipped into v0.10.
- [ ] Unified Studio CI covers `backend/timeline/**`, `tests/timeline/**`, backend integration seams, frontend typecheck/tests/build, and existing regression suites.
