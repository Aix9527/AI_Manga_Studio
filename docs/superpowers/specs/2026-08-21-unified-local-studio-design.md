# AI Manga Studio Unified Local Studio Design

## Goal

Replace the fragmented multi-page visualization layer with a local-first, one-stop filmmaking workspace that matches the approved UI concepts: a unified project cockpit, story/assets workspace, storyboard director, advanced node canvas, and timeline/QC workspace.

## Product principles

1. **Local first** — project data, generated media, cache, logs and model execution stay local by default.
2. **One-stop production** — the default path is import → story/assets → storyboard → keyframe/video → audio/subtitles → compose → QC → export.
3. **One-click for normal work** — advanced provider/model parameters are hidden behind sensible defaults.
4. **Observable and reversible** — every job exposes state, progress, retry and history; shot-level work keeps versions and QC state.
5. **Professional mode remains available** — node editing is preserved as an Advanced Canvas rather than the main entry point.

## Information architecture

The old UI exposes many separate top-level pages such as creator, studio, evolution, industrial, prompt OS, knowledge graph, digital twin and command center. These routes are removed from the primary navigation and replaced by five production surfaces:

- `/project` — Project Cockpit / 一键成片
- `/story-assets` — Story + Assets
- `/director` — Storyboard Director
- `/canvas` — Advanced Canvas
- `/timeline` — Timeline + QC + Export

Utility routes remain available through redirects where necessary for compatibility, but users no longer navigate through fragmented tool pages.

## Domain model

The UI is centered on four production objects:

- **Project** — title, source path, global settings, version and progress.
- **Episode** — episodic production unit.
- **Scene** — location/time/emotion context and ordered shots.
- **Shot** — framing, camera, references, generation prompt, media versions, QC state.

Reusable assets are managed independently and referenced by scenes/shots:

- Character
- Location
- Prop
- Voice
- Style

## Reuse of existing backend

No backend rewrite is required for this phase. The new UI reuses the existing contracts and stores:

- `/api/workspace/:projectId` for project/stage snapshot
- `/api/jobs` for one-click production tasks and lifecycle operations
- `/api/workspace/:projectId/assets` for generated assets
- existing story/character stores for novel parsing and character extraction
- existing SSE job event flow for progress updates

This preserves production behavior while replacing the navigation, visual hierarchy and user workflow.

## Screen design

### 1. Project Cockpit

The first screen mirrors the approved “一站式一键成片” concept.

Layout:

- left project tree / current project summary
- center six-step pipeline cards
- large `开始一键生成` CTA
- local environment status strip
- recent shot/media rail
- right live task queue

One-click production uses the existing automatic job API. The screen clearly exposes current progress, active jobs, QC state and retry paths.

### 2. Story + Assets

A split workspace combines story structure and reusable assets.

- left: Episode → Scene → Shot tree
- center: story/scene cards and asset grids
- right: selected asset/scene inspector

Characters, locations, props, voice and style are presented as persistent project assets rather than separate tools.

### 3. Storyboard Director

The director workspace follows the approved mockup:

- large hero-frame preview
- scene shot strip
- compact scene timeline
- right director inspector
- shot version + QC panel

Director controls include composition, shot scale, camera movement, focal length, lighting, emotion, reference frames and execution prompt. Generation actions operate at shot scope.

### 4. Advanced Canvas

The existing `@xyflow/react` dependency is used for a professional node canvas.

Default flow:

`小说文本 → 场景拆解 → 角色Bible → 分镜脚本 → 关键帧 → TI2V视频 → 配音/字幕 → 合成导出`

The canvas is explicitly labelled `专业精修 / 本地可控 / 节点可回放` and is not part of the beginner flow.

### 5. Timeline + QC

The final workspace combines:

- shot timeline
- media/artifact preview
- QC summary
- failed/review jobs
- export state

This removes the need to jump between separate quality and export pages.

## Visual system

Keep the existing dark theme but standardize it around the approved concept:

- background: `#090d12`
- surfaces: `#11161d` / `#171e27`
- primary accent: violet/blue `#7c5cff` / `#4f7cff`
- success: `#3ddc97`
- warning: `#f2bd5a`
- danger: `#ff6b6b`
- border: `#263142`

Use restrained glow only for active production states and selected nodes/shots.

## Interaction rules

- The selected project drives all workspace state.
- Jobs subscribe to SSE while active.
- Errors use existing `userMessage()` normalization.
- Primary actions remain accessible with keyboard focus and semantic buttons.
- Old routes redirect into the closest unified workspace.
- Advanced controls never block the one-click path.

## Testing

Frontend acceptance coverage must verify:

1. unified navigation contains only the new production surfaces;
2. project cockpit renders pipeline and local status from existing workspace/job state;
3. one-click CTA creates an automatic production job after input import is available;
4. storyboard director exposes shot-level controls and QC/version surfaces;
5. advanced canvas renders the expected default node chain;
6. legacy tool routes redirect to unified workspaces.

## Scope boundary

This phase restructures the UI and orchestration entry points only. It does not replace working ComfyUI workflows, model routing, production persistence, QC engines or FFmpeg composition logic.