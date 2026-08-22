# H3 Unified + Segmented Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-party H3 unified runtime contract, semantic 9-image reference bundle, segmented/V6 continuity planning, and opt-in provider/router integration without vendoring unlicensed third-party node code.

**Architecture:** Existing Native H3 stays the fallback. New modules under `backend/video/h3_unified/` convert AI Manga Studio shot metadata into a stable JSON state and segment execution plan. `H3UnifiedProvider` performs ComfyUI node preflight and emits either the external single-node workflow or a native-fallback decision. Router integration is opt-in until live preflight passes.

**Tech Stack:** Python 3.12, dataclasses, FastAPI, pytest, existing ComfyUI adapter/runtime router.

**Spec:** `docs/superpowers/specs/2026-08-22-h3-unified-segmented-runtime-design.md`

## Global Constraints
- Do not vendor uploaded third-party Python/JS/PowerShell code because no LICENSE/NOTICE is present.
- Do not alter the existing `MiniMaxH3Provider` fallback behavior.
- Maximum unified reference files: 12.
- H3 segment duration: 5–15 seconds for segmented production mode.
- 16 GB GPUs default to single-sample + post-generation upscale + balanced offload.
- Latent continuity is enabled only when all Motion Context node classes are present.

---

### Task 1: Reference bundle and unified state

**Files:**
- Create: `backend/video/h3_unified/__init__.py`
- Create: `backend/video/h3_unified/reference_bundle.py`
- Create: `backend/video/h3_unified/ui_state.py`
- Create: `tests/video/test_h3_unified.py`

**Interfaces:**
- Produces: `H3ReferenceBundle`, `H3Mode`, `H3UnifiedRequest`, `build_ui_state()`.

- [ ] Write tests for 9-slot deterministic ordering, 12-file limit, mode validation, 16 GB profile, and serializable control state.
- [ ] Run tests and confirm RED because modules do not exist.
- [ ] Implement minimal dataclasses/validation.
- [ ] Run tests and confirm GREEN.
- [ ] Commit.

### Task 2: Segmented/V6 execution planning

**Files:**
- Create: `backend/video/h3_unified/segmented.py`
- Extend: `tests/video/test_h3_unified.py`

**Interfaces:**
- Produces: `H3SegmentPolicy`, `H3Segment`, `H3SegmentPlan`, `build_segment_plan()`.

- [ ] Add RED tests for 32-second splitting, per-segment prompts, conservative 16 GB defaults, dual-sample opt-in, and latent continuity fallback.
- [ ] Implement the provider-neutral plan without Impact/EasyUse dependencies.
- [ ] Verify GREEN and commit.

### Task 3: Provider preflight and workflow selection

**Files:**
- Create: `backend/video/providers/minimax_h3_unified_provider.py`
- Extend: `tests/video/test_h3_unified.py`

**Interfaces:**
- Produces: `H3UnifiedProvider.preflight(object_info)`, `.build_external_workflow(request)`, `.select_continuity(...)`.

- [ ] Add RED tests for unified-node detection, Motion Context node detection, and native fallback when external nodes are absent.
- [ ] Implement minimal provider selection/workflow builder.
- [ ] Verify GREEN and commit.

### Task 4: Runtime API and opt-in router integration

**Files:**
- Modify: `backend/api/runtime_api.py`
- Modify: `backend/core/runtime/router.py`
- Create: `tests/video/test_h3_unified_router.py`

**Interfaces:**
- Adds: `POST /runtime/h3/unified/state`, `POST /runtime/h3/segments/plan` through the existing router mount.
- Adds opt-in routing fields: `h3_unified: true` or `intent: long_reference`.

- [ ] Add RED routing/API tests.
- [ ] Implement opt-in routing only; default H3 behavior remains unchanged.
- [ ] Verify GREEN and commit.

### Task 5: Backend CI

**Files:**
- Create: `.github/workflows/h3-backend-ci.yml`

- [ ] Run on PR changes to `backend/video/h3_unified/**`, provider/router/runtime API files, and H3 tests.
- [ ] Install `requirements.txt` and run only H3 unified tests.
- [ ] Confirm workflow GREEN before marking PR ready.
