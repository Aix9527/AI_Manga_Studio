# H3 Unified Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-safe unified MiniMax H3 runtime that supports five-mode state, semantic multi-reference bundles, long-form segment planning, and optional AV latent continuity while preserving current Native/Spectrum H3 fallbacks.

**Architecture:** Keep the existing H3 providers intact and add a new `backend.production.h3_unified` package. Generic callers pass optional `h3_options` through `VideoRequest`; the unified provider chooses a one-node external control-desk bridge, a native segmented Ref2VA path, or the existing providers. Long-form continuity is built in Python orchestration and only activates after ComfyUI preflight verifies Motion Context nodes.

**Tech Stack:** Python 3.12, dataclasses/enums, existing `ComfyUIAdapter`, existing `WorkflowTemplate`, pytest, JSON ComfyUI API graphs.

**Spec:** `docs/superpowers/specs/2026-08-22-h3-unified-runtime-design.md`

## Global Constraints

- Do not vendor source code from `ltoj_h3_unified_control_desk`.
- Do not vendor user-supplied Impact Pack V4/V5/V6 workflow JSON.
- Keep Motion Context an optional external ComfyUI capability.
- Keep existing `minimax_h3`, `minimax_h3_spectrum`, Wan fallback and model lifecycle behavior source-compatible.
- Default target is RTX 5070 Ti 16 GB: one H3 job, 480p-safe defaults, no mandatory dual sampling or RTX super-resolution.
- Every new runtime branch must have a unit-test RED/GREEN cycle before production code is considered complete.

---

### Task 1: Unified H3 contracts and semantic references

**Files:**
- Create: `backend/production/h3_unified/__init__.py`
- Create: `backend/production/h3_unified/contracts.py`
- Create: `backend/production/h3_unified/reference_bundle.py`
- Create: `tests/production/test_h3_unified_contracts.py`

**Interfaces:**
- Produces `H3Mode`, `H3ReferenceBundle`, `H3ReferenceItem`, `H3UnifiedOptions`, `H3SegmentSpec`.
- Produces `build_reference_bundle(image_roles, videos, audios) -> H3ReferenceBundle`.

- [ ] **Step 1: Write failing tests** for five-mode validation, role order, de-duplication, per-kind limits and combined 12-file limit.
- [ ] **Step 2: Run targeted tests** and verify missing-module failures.
- [ ] **Step 3: Implement contracts and bundle builder** with immutable tuples and JSON-safe serialization.
- [ ] **Step 4: Run targeted tests** and verify PASS.
- [ ] **Step 5: Commit** `feat(h3): add unified contracts and reference bundle`.

### Task 2: Segment planner and H3 legal frame grid

**Files:**
- Create: `backend/production/h3_unified/segment_planner.py`
- Create: `tests/production/test_h3_segment_planner.py`

**Interfaces:**
- Produces `align_h3_frames(duration_s: float, fps: int = 24) -> int`.
- Produces `parse_segment_script(script: str, base_seed: int, fps: int = 24) -> tuple[H3SegmentSpec, ...]`.

- [ ] **Step 1: Write failing tests** for `===` segmentation, `& seconds &` parsing, 5–15 second clamp, `frames % 17 == 5`, deterministic seeds and error segment index.
- [ ] **Step 2: Run targeted tests** and verify RED.
- [ ] **Step 3: Implement parser** without importing Impact Pack or external workflow code.
- [ ] **Step 4: Run targeted tests** and verify PASS.
- [ ] **Step 5: Commit** `feat(h3): add segmented prompt planner`.

### Task 3: LtoJ control-desk compatible state builder

**Files:**
- Create: `backend/production/h3_unified/control_state.py`
- Create: `tests/production/test_h3_control_state.py`

**Interfaces:**
- Produces `build_control_desk_state(options, bundle, uploaded_files, shot_meta) -> dict`.
- Produces `build_control_desk_workflow(state) -> dict[str, dict]` using only `LtoJ_H3UnifiedControlDesk`.

- [ ] **Step 1: Write failing tests** for T2VA/I2VA/FL2VA/L2VA/Ref2VA state requirements and semantic slot order.
- [ ] **Step 2: Run targeted tests** and verify RED.
- [ ] **Step 3: Implement independent JSON builder** matching the external public state schema, with relative filenames only.
- [ ] **Step 4: Run targeted tests** and verify PASS.
- [ ] **Step 5: Commit** `feat(h3): add unified control-desk bridge state`.

### Task 4: Native Ref2VA graph expansion and Motion Context wiring

**Files:**
- Create: `backend/production/h3_unified/workflow_builder.py`
- Create: `backend/production/h3_unified/continuity.py`
- Create: `tests/production/test_h3_unified_workflow_builder.py`

**Interfaces:**
- Produces `expand_reference_images(workflow, refs) -> workflow` supporting nine images.
- Produces `add_motion_context(workflow, *, run_id, segment_index, fps, context_frames=22, audio_context_frames=24) -> workflow`.
- Produces `MOTION_CONTEXT_NODE_SIGNATURES` for preflight reuse.

- [ ] **Step 1: Write failing tests** from the repository-owned `h3/reference.json`: nine image loaders, fixed latent slot indexes, first segment save-only, continuation load/inject/trim/save wiring.
- [ ] **Step 2: Run targeted tests** and verify RED.
- [ ] **Step 3: Implement pure graph transformations** with deterministic node IDs; do not use Impact queue nodes.
- [ ] **Step 4: Run targeted tests** and verify PASS.
- [ ] **Step 5: Commit** `feat(h3): add latent continuity graph builder`.

### Task 5: Optional capability preflight

**Files:**
- Modify: `backend/production/preflight.py`
- Modify: `tests/production/test_preflight.py`

**Interfaces:**
- Add provider capabilities `minimax_h3_control_desk` and `minimax_h3_motion_context`.
- Reuse `MOTION_CONTEXT_NODE_SIGNATURES` from the unified package.

- [ ] **Step 1: Add failing tests** for missing/valid LtoJ node and Motion Context signatures.
- [ ] **Step 2: Run tests** and verify RED.
- [ ] **Step 3: Implement capability checks** while leaving `minimax_h3_ref2va` semantics unchanged.
- [ ] **Step 4: Run preflight tests** and verify PASS.
- [ ] **Step 5: Commit** `feat(h3): preflight unified H3 capabilities`.

### Task 6: VideoRequest plumbing and ChainRuntime forwarding

**Files:**
- Modify: `backend/production/providers.py`
- Modify: `backend/video/runtime.py`
- Create or modify: `tests/video/test_runtime_h3_options.py`

**Interfaces:**
- `VideoRequest.h3_options: dict[str, Any]` defaults to an empty dict.
- `ChainRuntime._build_request()` forwards `shot["h3_options"]` without mutation.

- [ ] **Step 1: Write failing test** that a shot-level H3 option bundle reaches `VideoRequest` intact.
- [ ] **Step 2: Run targeted test** and verify RED.
- [ ] **Step 3: Add backward-compatible dataclass field and forwarding**.
- [ ] **Step 4: Run existing VideoRequest/runtime tests** and verify PASS.
- [ ] **Step 5: Commit** `feat(h3): carry unified options through video requests`.

### Task 7: Unified provider runtime selection

**Files:**
- Create: `backend/production/h3_unified/provider.py`
- Create: `tests/production/test_h3_unified_provider.py`
- Modify: `backend/production/dual_engine_provider.py`

**Interfaces:**
- Produces `UnifiedH3VideoProvider.generate(VideoRequest) -> MediaArtifact`.
- `DualEngineVideoProvider(h3_provider="unified")` selects it without changing the current default unless explicitly configured.

- [ ] **Step 1: Write failing fake-adapter tests** for control-desk success, missing-control-desk fallback, normal Spectrum delegation, segmented stop-on-failure and metadata.
- [ ] **Step 2: Run targeted tests** and verify RED.
- [ ] **Step 3: Implement provider selection and segment execution** using existing adapter/provider APIs.
- [ ] **Step 4: Run provider + dual-engine tests** and verify PASS.
- [ ] **Step 5: Commit** `feat(h3): add unified H3 production provider`.

### Task 8: Runtime metadata and operational documentation

**Files:**
- Create: `docs/h3-unified-runtime.md`
- Modify: `README.md`
- Create: `tests/production/test_h3_unified_docs_contract.py` only if a machine-readable config example is added.

**Interfaces:**
- Document `h3_options` examples for five modes, nine-reference roles, segmented script format and local preflight commands.
- Explicitly state that LtoJ and Motion Context custom nodes are optional external installations and are not bundled.

- [ ] **Step 1: Add documentation** with 16 GB safe defaults and fallback behavior.
- [ ] **Step 2: Verify no ZIP-origin source/workflow files are present in the diff**.
- [ ] **Step 3: Commit** `docs: document unified H3 runtime`.

### Task 9: Full verification and PR

**Files:**
- Create: `.github/workflows/h3-unified-ci.yml` if existing CI does not execute backend unit tests.

**Interfaces:**
- No new production interface.

- [ ] **Step 1: Run targeted H3 unit suite**.
- [ ] **Step 2: Run existing production/video unit tests affected by the changes**.
- [ ] **Step 3: Run frontend unified-studio CI baseline if any frontend file changed**.
- [ ] **Step 4: Create a PR from `feat/h3-unified-runtime` to `master` and record exact CI evidence**.
- [ ] **Step 5: Keep PR unmerged until explicit user instruction**.

## Self-review

- Spec coverage: all five modes, 9/3/3 references, 12-file cap, V6-style segmentation, optional latent continuity, 16 GB guardrails and fallback are mapped to tasks.
- Placeholder scan: no implementation step depends on TODO/TBD behavior.
- Type consistency: `H3UnifiedOptions` flows through `VideoRequest.h3_options`; `H3SegmentSpec` is produced by the planner and consumed by the provider; Motion Context signatures are shared by workflow builder and preflight.
