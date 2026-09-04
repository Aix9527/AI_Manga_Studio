# Advanced Canvas Template Persistence v0.9.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement project-local immutable Advanced Canvas templates that can be saved, published/rolled back, resolved by ProjectCockpit one-click production, and recorded in Job provenance without creating a second workflow engine.

**Architecture:** Add template persistence to the existing orchestration SQLite database, keep template repository/service/compiler responsibilities isolated under `backend/workspace`, expose project-scoped APIs through the existing workspace router, and make ProjectCockpit resolve a published compiled policy before calling the existing `createJob()`. Advanced Canvas saves/publishes backend-authoritative versions and tracks dirty state; JobService/worker/provider/QC/review/export remain the sole execution path.

**Tech Stack:** Python 3 / FastAPI / Pydantic / SQLite, React 18 / TypeScript / Zustand / Ant Design / React Flow, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-05-advanced-canvas-template-persistence-design.md`

## Global Constraints

- Project-local templates only; no global template library in v0.9.1.
- Template versions are immutable; save creates a new version.
- Publishing changes only the project published pointer; republishing an older compatible version is rollback.
- No published template means one-click uses the current defaults: `shot_duration=5`, `1080x1920`, `24fps`, `style=anime`, `local_first=true`.
- An invalid published template fails closed and must never silently fall back to defaults.
- Canvas content is editable, but executable policy is backend-validated and backend-compiled.
- `scene` and `storyboard` UI nodes both compile to one canonical `planning` stage.
- Provider policy supports `runtime_default`, `preferred`, and `required`; a required provider cannot silently downgrade.
- Templates cannot bypass QC/review, inject arbitrary executable stages/providers/workflows, or mutate existing Jobs.
- Job settings record creation-time template provenance.

---

### Task 1: Persistence model and immutable version repository

**Files:**
- Modify: `backend/orchestration/database.py`
- Modify: `backend/workspace/models.py`
- Modify: `backend/workspace/repository.py`
- Create: `tests/workspace/test_production_template_repository.py`

**Interfaces:**
- Produces `ProductionTemplateSaveRequest`, `ProductionTemplateVersion`, `ProductionTemplateList`, and repository methods `save_production_template_version(...)`, `list_production_template_versions(...)`, `get_production_template_version(...)`, `get_published_production_template(...)`, `publish_production_template(...)`, `set_production_template_archived(...)`.

- [ ] **Step 1: Write failing repository tests** for v1/v2 numbering, immutability, project isolation, published pointer rollback, and published-version archive rejection.
- [ ] **Step 2: Run** `pytest tests/workspace/test_production_template_repository.py -q` and verify RED because schema/models/repository APIs do not exist.
- [ ] **Step 3: Add database tables** `project_production_templates` and `project_production_template_versions` to `OrchestrationDatabase._schema()` with `UNIQUE(project_id, version)`, published pointer, source/compiled JSON and hashes, active/archive status, timestamps, and lookup indexes.
- [ ] **Step 4: Add Pydantic models** for template content/version/list state and stable status fields.
- [ ] **Step 5: Add repository methods** using `BEGIN IMMEDIATE` for save/publish/archive state changes. Never update historical content/hash columns after insert.
- [ ] **Step 6: Run** `pytest tests/workspace/test_production_template_repository.py -q` and verify GREEN.
- [ ] **Step 7: Commit** `feat: add immutable project production template storage`.

### Task 2: Validator and canonical compiler

**Files:**
- Create: `backend/workspace/template_compiler.py`
- Modify: `backend/workspace/models.py`
- Create: `tests/workspace/test_production_template_compiler.py`

**Interfaces:**
- Produces `TemplateValidationError(code: str, message: str)`, `CanonicalTemplateCompiler.compile(request) -> dict[str, object]`, deterministic JSON normalization/hash helpers, canonical stage/provider policy validation.
- Consumes Stage mappings already represented by Advanced Canvas: `load_input`, `planning`, `character_design`, `visual_generate`, `video_generate`, `audio_tts`, `composition_compose`.

- [ ] **Step 1: Write failing compiler tests** covering default Canvas success, scene/storyboard collapse to one planning stage, unknown executable stage failure, reverse dependency failure, required-stage disable failure, unknown provider failure, H3 `required` unsupported failure, preferred provider allowed path, and QC/review bypass rejection.
- [ ] **Step 2: Run** `pytest tests/workspace/test_production_template_compiler.py -q` and verify RED.
- [ ] **Step 3: Implement deterministic normalization** using sorted-key compact JSON and SHA256 helpers so identical semantic input produces identical hashes.
- [ ] **Step 4: Implement `TemplateValidator`/`CanonicalTemplateCompiler`** with a small explicit canonical stage order and provider capability registry. Do not permit arbitrary paths, URLs, workflow JSON, QC/review overrides, or executable unknown stages.
- [ ] **Step 5: Ensure compiler output contains only whitelisted Job settings/options and canonical `stage_policy`, not raw React Flow presentation data.
- [ ] **Step 6: Run compiler tests** and verify GREEN.
- [ ] **Step 7: Commit** `feat: compile advanced canvas templates into canonical policy`.

### Task 3: Workspace service and API contract

**Files:**
- Modify: `backend/workspace/service.py`
- Modify: `backend/workspace/routes.py`
- Modify: `backend/workspace/models.py`
- Create: `tests/workspace/test_production_template_routes.py`

**Interfaces:**
- Produces service methods `save_production_template`, `list_production_templates`, `get_production_template`, `publish_production_template`, `get_published_production_template`, `archive_production_template`.
- Exposes:
  - `POST /api/workspace/{project_id}/production-templates`
  - `GET /api/workspace/{project_id}/production-templates`
  - `GET /api/workspace/{project_id}/production-templates/{version}`
  - `POST /api/workspace/{project_id}/production-templates/{version}/publish`
  - `GET /api/workspace/{project_id}/production-template/published`

- [ ] **Step 1: Write failing route tests** for save/list/read/publish/rollback, no-published-template explicit response, cross-project lookup failure, invalid template 400/422, missing version 404, and publish conflict 409.
- [ ] **Step 2: Run** `pytest tests/workspace/test_production_template_routes.py -q` and verify RED.
- [ ] **Step 3: Implement service methods** that compile on save, store source+compiled hashes, revalidate hashes/compatibility on publish, and return backend-authoritative models.
- [ ] **Step 4: Add routes and stable error mapping** for `TEMPLATE_VALIDATION_FAILED`, `TEMPLATE_VERSION_NOT_FOUND`, `TEMPLATE_VERSION_CONFLICT`, `TEMPLATE_PUBLISH_CONFLICT`, `TEMPLATE_PROVIDER_POLICY_UNSUPPORTED`, `TEMPLATE_STAGE_POLICY_INVALID`.
- [ ] **Step 5: Run route + repository + compiler tests** and verify GREEN.
- [ ] **Step 6: Commit** `feat: expose project production template APIs`.

### Task 4: Published-template resolver and Job provenance

**Files:**
- Modify: `backend/orchestration/schemas.py`
- Modify: `backend/orchestration/service.py`
- Modify: `backend/workspace/service.py`
- Create: `tests/orchestration/test_project_template_job_resolution.py`

**Interfaces:**
- Produces a backend helper/service contract that converts a published compiled policy into the existing Job create settings without creating a new Job type.
- Job `settings.template` records `source`, `version_id`, `version`, `schema_version`, `sha256`, `compiled_sha256`.

- [ ] **Step 1: Write failing integration tests** for no-template defaults, published v3 settings/provenance, v3 Job remaining unchanged after v4 publication, new Job using v4, and corrupt/invalid published template preventing Job creation.
- [ ] **Step 2: Run** `pytest tests/orchestration/test_project_template_job_resolution.py -q` and verify RED.
- [ ] **Step 3: Add a resolver** that returns either current system defaults plus `source=system_default` provenance or a verified published compiled policy plus project-template provenance.
- [ ] **Step 4: Bind resolved settings into the existing Job creation path** only; do not alter worker stage execution semantics.
- [ ] **Step 5: Run integration tests plus existing stage-execution tests** and verify GREEN.
- [ ] **Step 6: Commit** `feat: resolve published project templates into jobs`.

### Task 5: Frontend template API and Advanced Canvas save/publish UI

**Files:**
- Create: `frontend/src/api/productionTemplates.ts`
- Create: `frontend/src/types/productionTemplates.ts`
- Modify: `frontend/src/studio/AdvancedCanvasWorkspace.tsx`
- Modify: `frontend/src/studio/canvas/defaultFlow.ts`
- Create: `frontend/src/studio/AdvancedCanvasTemplatePersistence.test.tsx`

**Interfaces:**
- Produces frontend methods `saveProductionTemplate(projectId, request)`, `listProductionTemplates(projectId)`, `publishProductionTemplate(projectId, version)`, `getPublishedProductionTemplate(projectId)`.
- Advanced Canvas sends React Flow nodes/edges plus whitelisted production settings; backend remains authoritative.

- [ ] **Step 1: Write failing Vitest cases** for no saved version -> publish disabled, save -> v1, modifying Canvas -> dirty/publish disabled, second save -> v2, publish -> authoritative published v2, historical republish -> rollback.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run AdvancedCanvasTemplatePersistence.test.tsx` and verify RED.
- [ ] **Step 3: Add typed API client and template types** matching backend models.
- [ ] **Step 4: Replace fail-closed placeholder save/publish notices** with real API calls, backend-returned version/published state, and explicit dirty tracking. Publishing never auto-saves dirty Canvas state.
- [ ] **Step 5: Add version-history UI** sufficient to republish a compatible historical version; archive UI may remain minimal if archive endpoint is not user-facing in v0.9.1.
- [ ] **Step 6: Run targeted frontend tests** and verify GREEN.
- [ ] **Step 7: Commit** `feat: persist and publish advanced canvas templates`.

### Task 6: ProjectCockpit one-click template consumption

**Files:**
- Modify: `frontend/src/studio/ProjectCockpit.tsx`
- Modify: `frontend/src/api/productionTemplates.ts`
- Create: `frontend/src/studio/ProjectCockpitTemplateResolution.test.tsx`

**Interfaces:**
- ProjectCockpit resolves published template state before the existing `jobStoreActions().createJob(...)` call.
- No template preserves exact legacy defaults; valid template supplies compiled production settings; published-template resolver errors block Job creation.

- [ ] **Step 1: Write failing tests** for system-default label/request, published-template label/request, invalid published template preventing `createJob`, and a regression guard that published templates cannot be bypassed by hardcoded request settings.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run ProjectCockpitTemplateResolution.test.tsx` and verify RED.
- [ ] **Step 3: Update `startOneClick()`** to fetch authoritative published-template resolution before `createJob()`. Keep input preparation and the existing Job creation call; do not create another execution endpoint.
- [ ] **Step 4: Show template source/version summary** near one-click production controls and surface resolver failures clearly.
- [ ] **Step 5: Run targeted tests** and verify GREEN.
- [ ] **Step 6: Commit** `feat: use published canvas template for one-click production`.

### Task 7: CI, regression suite, self-review, and release-ready PR

**Files:**
- Modify: `.github/workflows/unified-studio-ci.yml`
- Modify as needed only to fix discovered regressions; no unrelated refactors.

**Interfaces:**
- CI must execute new workspace/orchestration template tests and full frontend test/build suite while retaining existing stage-execution coverage.

- [ ] **Step 1: Add new backend test files to CI** and ensure frontend full Vitest/build already includes new tests.
- [ ] **Step 2: Run/trigger backend regression set** covering workspace templates, director/runtime binding, orchestration stage execution, job resolution, routes, and terminal summary behavior.
- [ ] **Step 3: Run/trigger frontend** `npm audit`, typecheck, full Vitest, and production build.
- [ ] **Step 4: Review changed files** specifically for a second workflow engine, silent provider downgrade, QC/review bypass, mutable historical templates, invalid-template silent fallback, or template publication mutating existing Jobs.
- [ ] **Step 5: Fix only verified defects and rerun affected tests.**
- [ ] **Step 6: Create PR** from `feat/v0.9.1-template-persistence` to `master` with spec, TDD evidence, changed-file summary, compatibility statement, and CI evidence.
