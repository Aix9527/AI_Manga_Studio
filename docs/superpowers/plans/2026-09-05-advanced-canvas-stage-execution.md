# Advanced Canvas Stage Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Advanced Canvas execute formal stages on the existing production Job without creating a second workflow engine or bypassing QC/review/provider rules.

**Architecture:** Add a narrow `resume-from-stage` orchestration command that resolves a canvas stage boundary to an existing Job step, rewinds only the necessary dependency scope, preserves artifact history, and requeues the same Job when appropriate. The frontend maps validated canvas nodes to canonical stage keys and routes both canvas execution buttons through the existing Job store/API so returned authoritative Job state replaces local fake-success notices.

**Tech Stack:** FastAPI, Pydantic, SQLite, React 18, TypeScript, Zustand, React Flow, Vitest/Testing Library, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-advanced-canvas-stage-execution-design.md`

## Global Constraints

- Reuse the current orchestration Job, worker, SSE, provider routing, QC/review gates and artifact versioning.
- Do not create a second workflow engine or call ComfyUI/provider endpoints directly from Advanced Canvas.
- `waiting_review`, `running`, `queued` and `cancelled` are fail-closed execution states.
- Per-shot `visual_generate` and `video_generate` require a concrete `shot_id`.
- H3-required requests must not silently fall back to Wan or another provider.
- Historical artifacts stay physically/queryably preserved; superseded downstream outputs must not remain current.
- Project Cockpit one-click production behavior must remain unchanged.

---

### Task 1: Define the stage-execution domain contract

**Files:**
- Modify: `backend/orchestration/schemas.py`
- Test: `tests/orchestration/test_stage_execution.py`

**Interfaces:**
- Produces `StageExecutionMode = Literal["rerun_node", "continue"]`.
- Produces `StageExecutionRequest(stage_key: str, shot_id: str = "", mode: StageExecutionMode)`.
- Later tasks consume `JobService.execute_from_stage(job_id: str, request: StageExecutionRequest) -> JobDetail`.

- [ ] **Step 1: Write failing schema/service-facing tests** proving valid mode parsing, invalid mode rejection and per-shot validation delegated to service.
- [ ] **Step 2: Run the focused backend test in CI and confirm RED** because `StageExecutionRequest` / `execute_from_stage` do not exist.
- [ ] **Step 3: Add the minimal Pydantic request types** without altering existing retry/review request models.
- [ ] **Step 4: Re-run the focused test until schema cases pass and service cases remain RED for the expected missing method.**
- [ ] **Step 5: Commit** `test: define formal stage execution contract` / `feat: add stage execution request schema`.

### Task 2: Resolve targets and compute dependency-scoped invalidation

**Files:**
- Modify: `backend/orchestration/service.py`
- Modify: `backend/orchestration/repository.py` only if an atomic helper is needed.
- Test: `tests/orchestration/test_stage_execution.py`

**Interfaces:**
- Consumes `StageExecutionRequest`.
- Produces exact target resolution by `(stage_key, shot_id)` against `repo.get_job_steps(job_id)`.
- Produces dependency rules:
  - project stage `planning` invalidates all later per-shot/global steps;
  - shot `visual_generate` invalidates same-shot `hd_redraw` + `video_generate` and global `audio_tts`, `audio_sfx`, `composition_compose`, `export`;
  - shot `video_generate` invalidates same target and global audio/compose/export while leaving unrelated shot generation intact;
  - global `audio_tts` invalidates `audio_sfx`, compose and export;
  - global `composition_compose` invalidates export.

- [ ] **Step 1: Add RED tests** for missing target, duplicate target fail-closed, missing shot on shot-scoped stage, one-shot invalidation and planning-wide invalidation.
- [ ] **Step 2: Confirm RED in GitHub Actions** with no unrelated suite failure.
- [ ] **Step 3: Implement private helpers** such as `_resolve_stage_execution_target(...)` and `_stage_execution_invalidated_step_ids(...)`; keep canonical order derived from existing Job steps rather than duplicating a second production graph.
- [ ] **Step 4: Re-run focused tests** and verify unrelated shot steps remain untouched in one-shot rewinds.
- [ ] **Step 5: Commit** `feat: resolve canvas stage execution scope`.

### Task 3: Apply safe rewind mutations and reactivate the existing Job

**Files:**
- Modify: `backend/orchestration/service.py`
- Modify: `backend/orchestration/repository.py`
- Test: `tests/orchestration/test_stage_execution.py`
- Test: existing Workspace asset/version tests as regression coverage.

**Interfaces:**
- Produces `JobService.execute_from_stage(...) -> JobDetail`.
- Allowed source states: `paused`, `failed`, `retry_wait` when supported, and `completed` only if transition/repository semantics can safely reactivate it.
- Rejects `running`, `queued`, `waiting_review`, `cancelled` before mutation.
- `continue`: target becomes queued, dependent scope invalidated, same Job becomes queued for normal worker continuation.
- `rerun_node`: target/dependency scope is rewound without launching unrelated work; returned JobDetail remains authoritative.

- [ ] **Step 1: Add RED tests** for state hard-gates, same Job id preservation, no duplicate Job row, and repeated command safety.
- [ ] **Step 2: Add RED artifact/version test** proving historical artifact records remain while superseded downstream outputs are no longer treated as current/active.
- [ ] **Step 3: Implement one repository transaction/helper** that resets target/dependent step statuses and reconciles active downstream artifacts without deleting files/rows.
- [ ] **Step 4: Implement `execute_from_stage`** with state validation, target resolution, scoped invalidation, mutation, broadcast event `stage_execution_requested`, and authoritative `JobDetail` return.
- [ ] **Step 5: Run orchestration + workspace tests** and verify all pass.
- [ ] **Step 6: Commit** `feat: execute production job from canvas stage`.

### Task 4: Expose the formal `/resume-from-stage` API

**Files:**
- Modify: `backend/routes/jobs.py`
- Test: `tests/orchestration/test_stage_execution_routes.py`

**Interfaces:**
- Produces `POST /api/jobs/{job_id}/resume-from-stage`.
- Body: `{ "stage_key": string, "shot_id"?: string, "mode": "rerun_node" | "continue" }`.
- Returns `JobDetail` on success.
- Maps missing target/job to 404 where appropriate and illegal state/ambiguous target to 409; validation errors remain 422.

- [ ] **Step 1: Add RED route tests** for success shape, missing shot, running/review conflict and unknown target.
- [ ] **Step 2: Confirm RED** before route implementation.
- [ ] **Step 3: Add the route** using the existing `get_service(request)` pattern; do not add provider logic to the route.
- [ ] **Step 4: Run route + orchestration tests** until GREEN.
- [ ] **Step 5: Commit** `feat: expose resume-from-stage job command`.

### Task 5: Add frontend API/store support

**Files:**
- Modify: frontend job API module used by `jobStore.ts`.
- Modify: `frontend/src/state/jobStore.ts`.
- Modify/create shared frontend type for `StageExecutionRequest` if needed.
- Test: `frontend/src/state/jobStore.test.ts` or focused adjacent API/store test.

**Interfaces:**
- Produces `api.executeFromStage(jobId, request) -> Promise<JobDetail>`.
- Produces `jobStoreActions().executeFromStage(jobId, request) -> Promise<JobDetail>` using the existing `updateJob(...)` reconciliation path.

- [ ] **Step 1: Add RED frontend store/API test** proving returned Job replaces/updates the same store entry.
- [ ] **Step 2: Confirm typecheck/test RED** for the missing action.
- [ ] **Step 3: Implement API and store action** without a separate canvas-local job cache.
- [ ] **Step 4: Run frontend typecheck + focused test** to GREEN.
- [ ] **Step 5: Commit** `feat: add stage execution job action`.

### Task 6: Wire Advanced Canvas to real Job execution

**Files:**
- Modify: `frontend/src/studio/canvas/defaultFlow.ts`
- Modify: `frontend/src/studio/AdvancedCanvasWorkspace.tsx`
- Modify: `frontend/src/studio/AdvancedCanvasExecutionContract.test.tsx`
- Add/update focused canvas execution tests.

**Interfaces:**
- Extend validated node metadata with `stageKey` and `shotScoped` rather than maintaining a second mapping in the component.
- Canvas selects the active/recent Job for the current project from `jobStore`.
- `运行选中节点` sends `mode: "rerun_node"`.
- `从当前节点继续` sends `mode: "continue"`.
- Shot-scoped nodes require a concrete shot selection sourced from the Job/asset context; no synthetic `shot_001` default.

- [ ] **Step 1: Replace old “delegated execution” expectation with RED tests** asserting the formal action is called with the mapped stage key and mode.
- [ ] **Step 2: Add RED hard-gate tests** for no Job, active Job, `waiting_review`, missing shot and unmapped node.
- [ ] **Step 3: Add stage metadata to default flow** for all eight default nodes according to the approved spec.
- [ ] **Step 4: Wire buttons through `jobStoreActions().executeFromStage`** and display success/status only after backend acceptance; on rejection display `userMessage(error)`.
- [ ] **Step 5: Run full frontend tests/typecheck/build** and ensure no direct ComfyUI/provider call appears in the canvas component.
- [ ] **Step 6: Commit** `feat: make advanced canvas control production jobs`.

### Task 7: CI/release verification and PR

**Files:**
- Modify `.github/workflows/unified-studio-ci.yml` only if `tests/orchestration/test_stage_execution*.py` are not already covered.
- Update this plan with verified evidence after GREEN.

**Interfaces:**
- CI must cover backend orchestration/workspace tests plus frontend audit/typecheck/full tests/build.

- [ ] **Step 1: Open a draft PR from `feat/v0.9-advanced-canvas-stage-execution` to `master`** after RED tests exist so GitHub Actions captures RED evidence.
- [ ] **Step 2: Finish GREEN implementation commits.**
- [ ] **Step 3: Verify final PR head**: backend orchestration/workspace tests PASS; frontend dependency audit, typecheck, full Vitest suite and production build PASS.
- [ ] **Step 4: Review final diff** and confirm Advanced Canvas contains no direct provider/ComfyUI request and Project Cockpit production behavior is unchanged.
- [ ] **Step 5: Update PR body with exact behavior, RED/GREEN run IDs and limitations.**
- [ ] **Step 6: Merge only after the same final head SHA is GREEN, then re-read `master` to confirm endpoint and canvas binding are present.**
