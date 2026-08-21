# Unified Local Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild AI Manga Studio into a unified local-first production workspace matching the approved UI concepts while reusing the existing FastAPI/job/workspace contracts.

**Architecture:** Replace fragmented top-level React routes with one StudioShell and five focused workspaces. Reuse Zustand workspace/job stores and existing APIs; only create lightweight presentation adapters/sample fallbacks where the backend snapshot does not expose scene/shot metadata yet. Keep advanced node editing isolated in a dedicated `@xyflow/react` canvas.

**Tech Stack:** React 18, TypeScript, React Router 6, Zustand, Ant Design icons, @xyflow/react, Vite, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-21-unified-local-studio-design.md`

## Global Constraints

- Local-first behavior remains the default.
- Existing production APIs and backend orchestration remain authoritative.
- Primary navigation exposes only Project, Story/Assets, Director, Advanced Canvas, Timeline/QC.
- Legacy top-level tool routes redirect to unified workspaces.
- One-click production uses existing automatic job creation and SSE lifecycle.
- Advanced canvas must never be required for the normal production path.

---

### Task 1: Unified application shell and route cutover

**Files:**
- Create: `frontend/src/studio/StudioShell.tsx`
- Create: `frontend/src/studio/studioNavigation.ts`
- Create: `frontend/src/styles/unified-studio.css`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/studio/StudioShell.test.tsx`

**Interfaces:**
- Consumes: React Router `Outlet`, existing `useWorkspaceStore`, `useJobStore`.
- Produces: unified navigation routes `/project`, `/story-assets`, `/director`, `/canvas`, `/timeline`.

- [ ] Write a shell test that renders the five navigation destinations and verifies the old dashboard/tool labels are absent.
- [ ] Run the focused Vitest test and confirm the new shell is missing.
- [ ] Implement navigation, project status, local-mode indicator and workspace outlet.
- [ ] Replace App routing with the five unified workspaces plus legacy redirects.
- [ ] Run focused tests and typecheck.
- [ ] Commit only Task 1 files.

### Task 2: Project Cockpit / one-click production

**Files:**
- Create: `frontend/src/studio/ProjectCockpit.tsx`
- Create: `frontend/src/studio/components/PipelineStep.tsx`
- Create: `frontend/src/studio/components/TaskQueuePanel.tsx`
- Create: `frontend/src/studio/components/LocalStatusStrip.tsx`
- Test: `frontend/src/studio/ProjectCockpit.test.tsx`

**Interfaces:**
- Consumes: `WorkspaceSnapshot`, `api.health()`, `api.createJob()`, `api.uploadInput()`, existing story/character extraction stores, `jobStoreActions()`.
- Produces: one-click production dashboard and automatic production job entry point.

- [ ] Test six pipeline steps, local status area and primary CTA.
- [ ] Test active jobs render in the right queue with progress/status.
- [ ] Reuse existing import/start-production behavior from `ProjectOverview` in the new cockpit.
- [ ] Add accessible progress and failure/retry states.
- [ ] Run focused tests and typecheck.
- [ ] Commit Task 2 files.

### Task 3: Story + Assets workspace

**Files:**
- Create: `frontend/src/studio/StoryAssetsWorkspace.tsx`
- Create: `frontend/src/studio/components/ProjectTree.tsx`
- Create: `frontend/src/studio/components/AssetGrid.tsx`
- Test: `frontend/src/studio/StoryAssetsWorkspace.test.tsx`

**Interfaces:**
- Consumes: story store, character store, `workspaceApi.listAssets()`.
- Produces: unified story/asset surface with Character, Location, Prop, Voice and Style filters.

- [ ] Test story structure and asset category tabs.
- [ ] Implement project tree with graceful fallback when no structured scene data exists.
- [ ] Load workspace assets and map kinds into the five user-facing categories.
- [ ] Add selected-item inspector state.
- [ ] Run focused tests and typecheck.
- [ ] Commit Task 3 files.

### Task 4: Storyboard Director

**Files:**
- Create: `frontend/src/studio/StoryboardDirectorWorkspace.tsx`
- Create: `frontend/src/studio/components/ShotRail.tsx`
- Create: `frontend/src/studio/components/DirectorInspector.tsx`
- Test: `frontend/src/studio/StoryboardDirectorWorkspace.test.tsx`

**Interfaces:**
- Consumes: project assets and recent job artifacts.
- Produces: selected-shot state and director parameter controls.

- [ ] Test hero preview, shot cards, timeline and director parameter labels.
- [ ] Build media-backed shot rail from existing artifacts, with deterministic fallback cards when no artifacts exist.
- [ ] Implement composition, shot scale, camera motion, focal length, lighting, emotion and prompt controls as local shot draft state.
- [ ] Surface QC and version status from asset metadata/quality fields when available.
- [ ] Run focused tests and typecheck.
- [ ] Commit Task 4 files.

### Task 5: Advanced Canvas

**Files:**
- Create: `frontend/src/studio/AdvancedCanvasWorkspace.tsx`
- Create: `frontend/src/studio/canvas/defaultFlow.ts`
- Test: `frontend/src/studio/AdvancedCanvasWorkspace.test.tsx`

**Interfaces:**
- Consumes: `@xyflow/react`.
- Produces: default production graph and selected-node inspector.

- [ ] Test the default chain contains 小说文本, 场景拆解, 角色Bible, 分镜脚本, 关键帧, TI2V视频生成, 配音/字幕, 合成导出.
- [ ] Implement the node canvas with Background, Controls and MiniMap.
- [ ] Add selected-node parameter inspector and professional-mode copy.
- [ ] Add local-only buttons for run-selected/continue/save-template/publish-to-one-click with explicit non-destructive UI state until backend node execution contracts are exposed.
- [ ] Run focused tests and typecheck.
- [ ] Commit Task 5 files.

### Task 6: Timeline + QC workspace

**Files:**
- Create: `frontend/src/studio/TimelineQcWorkspace.tsx`
- Test: `frontend/src/studio/TimelineQcWorkspace.test.tsx`

**Interfaces:**
- Consumes: workspace assets, job store, QC fields on artifacts.
- Produces: timeline blocks, QC summary, failed/review queue and export entry surface.

- [ ] Test timeline, QC summary and export area render.
- [ ] Build timeline from artifact duration metadata when available, otherwise use deterministic 5-second shot blocks.
- [ ] Surface failed/waiting-review jobs with retry/review actions using existing job APIs.
- [ ] Reuse media URLs for preview.
- [ ] Run focused tests and typecheck.
- [ ] Commit Task 6 files.

### Task 7: Full regression and cleanup

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Modify as needed: unified-studio files only.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: production-ready unified frontend branch.

- [ ] Run `npm test -- --run`.
- [ ] Run `npm run typecheck`.
- [ ] Run `npm run build`.
- [ ] Fix only regressions caused by the unified workspace change.
- [ ] Compare route list to spec and verify every legacy tool route redirects.
- [ ] Commit final cleanup.
- [ ] Open a draft PR from `feat/unified-local-studio` to `master` with summary, test evidence and known limitations.