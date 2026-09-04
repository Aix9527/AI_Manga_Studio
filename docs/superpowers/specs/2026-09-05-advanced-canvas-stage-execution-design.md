# Advanced Canvas Formal Stage Execution Design

**Status:** Approved architecture, ready for implementation planning

## Goal

Upgrade Advanced Canvas from a configuration/inspection surface into a formal control plane for the existing production Job. The canvas must reuse the current orchestration state machine, worker, SSE, provider routing, QC gates, review gates, artifact versioning and retry semantics. It must not create a second workflow engine or call ComfyUI providers directly from the UI.

## Non-goals

- Do not replace the one-click Project Cockpit production flow.
- Do not create a second Job model or parallel stage state machine.
- Do not bypass `waiting_review`, QC, provider routing, leases, retries or artifact version history.
- Do not silently fall back from MiniMax H3 to another video provider.
- Do not implement the full persisted NLE timeline model in this tranche.

## Existing canonical production stages

The current Job service owns the canonical sequence:

1. `load_input`
2. `planning`
3. `character_design`
4. per-shot `visual_generate`
5. per-shot `hd_redraw`
6. per-shot `video_generate`
7. `audio_tts`
8. `audio_sfx`
9. `composition_compose`
10. `export`

The existing `rollback_preview(job_id, step_id)` already establishes the key invalidation concept: when a target step is chosen, later completed/queued/running steps can be identified as dependent work that must be invalidated.

## Canvas node mapping

The default production canvas remains a presentation layer over the canonical Job:

| Canvas node | Formal orchestration boundary |
| --- | --- |
| `novel` / 小说文本 | `load_input` |
| `scene` / 场景拆解 | `planning` |
| `character` / 角色 Bible | `character_design` |
| `storyboard` / 分镜脚本 | `planning` boundary; future dedicated storyboard stage may replace this mapping |
| `keyframe` / 关键帧 | `visual_generate` |
| `video` / TI2V 视频生成 | `video_generate` |
| `audio` / 配音/字幕 | `audio_tts` |
| `export` / 合成导出 | `composition_compose` |

Per-shot nodes (`keyframe`, `video`) require a concrete `shot_id`; project-level nodes must not accept one unless the backend explicitly supports it.

## Formal backend contract

Add an orchestration command endpoint conceptually equivalent to:

`POST /api/jobs/{job_id}/resume-from-stage`

Request:

```json
{
  "stage_key": "video_generate",
  "shot_id": "shot_003",
  "mode": "continue"
}
```

`mode` has two values:

- `rerun_node`: rerun the target stage boundary and invalidate dependent downstream work, but do not automatically queue unrelated later stages outside the target dependency scope.
- `continue`: rewind to the target boundary and continue the canonical production Job from there through export.

The backend, not the frontend, resolves the request to an exact existing Job step. The UI never submits raw `step_id` for canvas execution.

## State-machine rules

### Allowed source Job states

The command is fail-closed. Initial implementation allows execution only from stable, non-active states where rewinding is deterministic:

- `paused`
- `failed`
- `retry_wait` if represented in the current Job enum/contract
- `completed` only when the repository can safely reactivate the Job and preserve previous artifacts as historical versions

The command must reject:

- `running`
- `queued`
- `waiting_review`
- `cancelled`

`waiting_review` may only move through the existing review endpoint; Canvas cannot approve or bypass it.

### Target resolution

The service resolves `(stage_key, shot_id)` against the Job's existing steps.

- If there is no matching step: HTTP 404/409 style domain conflict; no state changes.
- If multiple matches exist where uniqueness is required: fail closed rather than guessing.
- For per-shot stages, `shot_id` is mandatory.
- For project-level stages, `shot_id` is empty.

### Invalidation

When the target step is selected:

1. Preserve all artifacts physically; never delete historical files solely because of rewind.
2. Mark/reconcile active artifact versions so superseded downstream outputs are no longer treated as current.
3. Reset the target step to `queued`.
4. Invalidate downstream dependent steps according to canonical ordering and shot scope.
5. For `continue`, queue/reopen the Job so the existing worker naturally advances through the remaining canonical stages.
6. For `rerun_node`, only the target/dependency scope is made executable; unrelated downstream work must not be silently launched.

The exact repository mutation must be atomic at the database transaction level where possible.

## Dependency scope

Per-shot rewinds must avoid invalidating unrelated shots unnecessarily.

Example: rerunning `visual_generate` for `shot_003` must invalidate at minimum:

- `shot_003` `hd_redraw`
- `shot_003` `video_generate`
- global audio/composition/export work that incorporates that shot

It should not invalidate `visual_generate`/`video_generate` outputs for `shot_001` or `shot_002` unless a global dependency explicitly requires it.

Project-level rewinds such as `planning` necessarily invalidate all later per-shot and global production stages.

## Artifact/version behavior

Re-execution must preserve auditability:

- Old artifacts remain queryable/versioned.
- Newly generated artifacts become the active version for their stage/scene/shot lineage.
- Compose/export outputs produced before a rewind are no longer considered current if their inputs were invalidated.
- The existing Workspace asset model remains the source of truth for active/version/quality metadata.

## Provider behavior

The canvas only selects/configures provider intent. Actual execution continues through the existing provider routing inside the worker/runtime.

- `video_generate` may resolve to Wan or MiniMax H3 according to existing formal settings/contracts.
- H3-required requests must remain H3-required; no transparent fallback.
- Provider errors surface through the existing Job failure/retry path.

## Frontend behavior

Advanced Canvas loads the active/recent production Job for the current project and exposes two real actions:

### 运行选中节点

- Resolve the selected canvas node to a formal stage boundary.
- Require a shot selection for shot-scoped nodes.
- Call the formal command with `mode=rerun_node`.
- Subscribe/refresh through the existing Job store/SSE path.
- Show actual returned Job/step status, never optimistic fake-success text.

### 从当前节点继续

- Same target resolution.
- Call with `mode=continue`.
- The canonical worker resumes from the target and advances normally.

### UI hard gates

Buttons are disabled with an explicit reason when:

- no production Job exists;
- Job is active (`running`/`queued`);
- Job is `waiting_review`;
- a shot-scoped node has no `shot_id` selection;
- selected node has no validated orchestration mapping.

## API and domain types

Introduce narrow types rather than overloading generic retry:

- `StageExecutionMode = rerun_node | continue`
- `StageExecutionRequest { stage_key, shot_id?, mode }`
- optionally `StageExecutionPreview` for future UX; implementation may reuse/extend rollback preview internally.

The command returns the updated `JobDetail` so the frontend immediately reconciles against the authoritative state.

## TDD / acceptance criteria

Backend regression tests must prove:

1. `(stage_key, shot_id)` resolves only to an existing Job step.
2. `waiting_review`, `running` and `queued` fail closed with no mutations.
3. Rerunning `visual_generate` for one shot invalidates that shot's downstream video path plus global composition/export, but not unrelated shot generation steps.
4. Rewinding `planning` invalidates all later stages.
5. Historical artifacts are retained while superseded outputs are no longer active/current.
6. `continue` requeues the existing Job; no duplicate Job is created.
7. Repeated/idempotent command handling does not corrupt step state.

Frontend tests must prove:

1. Canvas buttons call the formal stage execution API instead of local-only notices.
2. Active/review Job states disable execution with explicit reasons.
3. Shot-scoped nodes require a concrete shot.
4. Returned Job state flows through the existing Job store.
5. No UI text claims a node executed unless the backend accepted the command.

CI must run the new orchestration tests plus existing Workspace/frontend suites and production build.

## Rollout

Implement on a new feature branch and PR. Do not modify `master` directly. Keep the one-click Project Cockpit behavior unchanged. The feature is complete only after the PR head passes backend orchestration/workspace tests, frontend audit/typecheck/tests/build, and the final diff confirms no direct provider/ComfyUI call was introduced into Advanced Canvas.

## Follow-up work

After this contract is stable, later tranches may add:

- persisted canvas templates;
- richer per-node provider parameters;
- explicit execution preview before rewind;
- full NLE clip/track editing model;
- desktop packaging/release UX.
