# H3 Unified Runtime Integration Design

## Context

AI Manga Studio already has three MiniMax H3 execution paths:

- `backend/production/minimax_h3_adapter.py` — native `MiniMaxH3Director` FL2VA path.
- `backend/production/spectrum_h3_provider.py` — accelerated FL2VA path.
- `backend/core/runtime/providers/h3.py` + `backend/production/workflows/h3/{standard,reference}.json` — standard and Ref2VA prompt builders.

Two user-supplied ZIPs add useful ideas:

1. **LtoJ H3 unified control desk**: one public ComfyUI node that hides a dynamic five-mode graph (`T2VA`, `I2VA`, `FL2VA`, `L2VA`, `Ref2VA`) behind a JSON `ui_state`, with semantic image/video/audio reference roles.
2. **H3 segmented reference workflows V6**: long-form generation split into 5–15 second segments, using previous-segment joint audio/video latent context instead of feeding the previous tail frame back into H3. The V6 workflows use `MiniMaxH3MotionContext*` nodes to carry motion and audio continuity across runs.

The segmented workflow ZIP explicitly states that its workflow is only allowed for non-commercial use/distribution. The LtoJ ZIP does not include an explicit software license. Therefore **no source code or workflow JSON from either ZIP will be vendored into this public repository**. This integration reimplements the interoperable data contracts and orchestration ideas independently.

The optional H3 Motion Context dependency is a separate external ComfyUI custom-node pack. AI Manga Studio will only integrate against its public node IDs/signatures and will not vendor its GPL source.

## Goals

1. Add a production-safe, reversible `H3 Unified Runtime` without replacing the existing Native/Spectrum H3 providers.
2. Support the five H3 generation modes through a common request contract.
3. Introduce a semantic `ReferenceBundle` for up to 9 images, 3 reference videos and 3 reference audios, while enforcing H3's combined reference-file cap.
4. Parse long-form segment scripts into deterministic 5–15 second H3 segment plans with legal H3 frame counts.
5. Support retry-safe cross-run joint audio/video latent continuity when `MiniMaxH3MotionContext*` nodes are installed.
6. Fall back cleanly when optional external nodes are not installed.
7. Preserve current durable orchestration, QC, fallback and model-lifecycle behavior.
8. Keep 16 GB VRAM as the default safety target: one H3 job at a time, 480p/production-safe defaults, no mandatory dual-sampling or RTX super-resolution dependency.

## Non-goals

- Do not vendor `ltoj_h3_unified_control_desk` source.
- Do not vendor the Impact Pack V4/V5/V6 workflow JSON.
- Do not make Impact Pack, EasyUse, RTX Video Super Resolution, LTX latent helpers, or KJNodes hard production dependencies.
- Do not change the existing Wan2.2 fallback semantics.
- Do not expose arbitrary ComfyUI graph execution to the frontend.
- Do not claim latent continuity is available unless ComfyUI preflight verifies the required node signatures.

## Architecture

```text
Project / Shot
    |
    v
VideoRequest + h3_options
    |
    +-----------------------------+
    | H3UnifiedOptions            |
    | mode / refs / segmentation  |
    +-----------------------------+
    |
    v
UnifiedH3VideoProvider
    |
    +--> bridge runtime available? ----> LtoJ one-node bridge
    |
    +--> segmented request? ------------> Native Ref2VA segment runner
    |                                      + Motion Context when available
    |
    +--> otherwise ----------------------> existing Spectrum / Native H3
    |
    v
MediaArtifact + runtime metadata
```

### File boundaries

#### `backend/production/h3_unified/contracts.py`
Pure dataclasses/enums/constants. No ComfyUI network access.

Produces:

- `H3Mode`
- `H3ImageRole`, `H3VideoRole`, `H3AudioRole`
- `H3ReferenceItem`
- `H3ReferenceBundle`
- `H3SegmentSpec`
- `H3UnifiedOptions`

The contracts enforce maximum counts and provide JSON-safe metadata.

#### `backend/production/h3_unified/reference_bundle.py`
Builds a deterministic semantic reference bundle from project/shot mappings. Image order is fixed:

1. character identity
2. secondary character/opponent
3. environment/location
4. costume
5. key prop
6. expression/state
7. style/material
8. lighting/color
9. storyboard/N-grid

Videos are ordered as action/rhythm, camera/editing, character motion. Audios are ordered as protagonist voice, secondary/opponent voice, narrator/third voice.

Reference inputs are de-duplicated by canonical path while preserving the highest-priority semantic role.

#### `backend/production/h3_unified/segment_planner.py`
Accepts either a single prompt or an integrated script separated by `===`.

Per-segment duration can be written as `& <seconds> &`. Durations are clamped to 5–15 seconds. Frame counts use the H3 legal grid:

```text
frames >= requested_frames
frames % 17 == 5
```

Seeds are deterministic (`base_seed + segment_index`) so failed/retried segments do not shift later segment identities.

#### `backend/production/h3_unified/control_state.py`
Builds an independent JSON state compatible with the installed LtoJ one-node control desk contract without importing or copying the external package.

The bridge state only contains relative uploaded filenames and generation parameters. It never stores secrets or local absolute paths.

#### `backend/production/h3_unified/continuity.py`
Owns the H3 Motion Context capability contract.

Required node IDs:

- `MiniMaxH3MotionContext`
- `MiniMaxH3MotionContextTrim`
- `MiniMaxH3MotionContextSaveLatent`
- `MiniMaxH3MotionContextLoadLatent`

Default continuity settings:

- video context: 22 frames
- audio context: 24 frames
- `match_tail=True`

Segment N saves a fixed latent slot for N. Segment N+1 loads slot N. Fixed indexed slots make re-rolls retry-safe: regenerating segment N+1 never conditions on its own rejected latent.

#### `backend/production/h3_unified/provider.py`
`UnifiedH3VideoProvider` is the production integration point.

Runtime selection:

1. If `h3_options.runtime == "control_desk"` and `LtoJ_H3UnifiedControlDesk` is present, submit a one-node bridge graph.
2. If a segmented plan contains multiple segments, use the native Ref2VA graph builder. Enable Motion Context only when preflight verifies the four required nodes; otherwise continue with independent segments and mark `continuity="unavailable"` in metadata.
3. Otherwise delegate to the existing Spectrum provider by default, or existing Native provider when explicitly requested.

The provider never silently switches to an unverified external custom-node path.

#### `backend/production/h3_unified/workflow_builder.py`
Builds API-format native Ref2VA graphs from the repository's existing `h3/reference.json` template, then adds only the optional continuity nodes needed for segment execution.

For the first segment:

- generate Ref2VA
- decode video/audio
- run `MotionContextTrim` with `trim_frames=0` only when the node is available, so tail audio is duration-aligned
- save AV latent into segment slot 1

For subsequent segments:

- load previous AV latent by fixed clip index
- inject `MiniMaxH3MotionContext` between `MiniMaxH3ReferenceToVideo` conditioning and `BasicGuider`
- decode
- trim duplicated head frames and align audio tail
- save current segment latent into its fixed slot

No Impact Pack queue nodes are used. Python orchestration controls the loop, retries and failure stop behavior.

## `VideoRequest` compatibility

`backend/production/providers.py::VideoRequest` gains one optional field:

```python
h3_options: dict[str, Any] = field(default_factory=dict)
```

Existing callers remain source-compatible. `ChainRuntime._build_request()` forwards `shot.get("h3_options", {})` into the request, allowing project/shot planners to opt into unified H3 without changing generic video providers.

## Preflight

`backend/production/preflight.py` adds two optional capabilities:

- `minimax_h3_control_desk`
- `minimax_h3_motion_context`

The control-desk capability checks the public node ID only. The Motion Context capability checks required input names/descriptors for all four nodes.

Missing optional capabilities are **not** treated as a global H3 failure; the runtime records why a requested optional path cannot be used and chooses a safe fallback.

## 9-image reference support

The current repository Ref2VA template exposes three `LoadImage` slots. The unified builder must support up to nine images without requiring the static template to contain nine loader nodes. It clones `LoadImage` node definitions into deterministic high-numbered node IDs at render time and wires them into `MiniMaxH3ReferenceToVideo.ref_images`.

This avoids a broad rewrite of the existing template and keeps the legacy three-image behavior intact.

## Segment output and continuity layout

For a run named `run_id`:

```text
outputs/minimax_h3_unified/<run_id>/
    segment_0001.mp4
    segment_0002.mp4
    ...

ComfyUI/output/AI_Manga_Studio/H3/context/<run_id>/
    clip_00001.safetensors
    clip_00002.safetensors
    ...
```

The final provider artifact for a multi-segment request is the final segment artifact plus metadata describing all segment paths. Concatenation remains the responsibility of the existing composer/FFmpeg stage so QC and reversible production manifests stay intact.

## Failure behavior

- Invalid five-mode requirements fail before ComfyUI submission (for example FL2VA without both first and last frames).
- More than 12 combined reference files fails before submission.
- A segment parser error identifies the exact segment index.
- Missing LtoJ node with an explicitly requested `control_desk` runtime returns a typed `COMFY_WORKFLOW_INVALID` error unless `allow_fallback=true`.
- Missing Motion Context nodes does not break normal H3. Segmented execution continues without latent continuity when fallback is allowed.
- Any segment generation failure stops later segments. Completed prior segment files and latent slots are retained for resumability.

## 16 GB VRAM defaults

The unified runtime defaults to:

- one H3 job at a time
- 480p generation profile
- 5–10 second ordinary segments
- 12 steps for control-desk bridge only when explicitly used
- 6 steps for existing native Ref2VA production path
- no dual sampling
- no mandatory RTX super-resolution
- existing `ModelLifecycleManager` remains responsible for engine unloading/fallback

The ZIP's V5/V6 dual-sampling and RTX 1.5x enhancement path is intentionally not made the default because it adds significant VRAM pressure and several external dependencies. It can be added later as an explicitly gated enhancement profile.

## Testing

Unit tests cover:

- semantic 9/3/3 reference packing and 12-file cap
- mode validation
- integrated prompt parsing and legal frame alignment
- deterministic seeds and retry-safe segment indexes
- LtoJ bridge state generation
- nine-image native Ref2VA graph expansion
- first-segment and continuation Motion Context graph wiring
- preflight signature detection
- provider runtime fallback behavior without a live GPU
- `ChainRuntime` forwarding `h3_options`

A live ComfyUI test is not required for merge. Live GPU validation remains a separate local gate because GitHub Actions does not have the user's H3 models or RTX 5070 Ti environment.

## Acceptance criteria

1. Existing H3 and Wan tests stay green.
2. Requests without `h3_options` behave exactly as before.
3. A Ref2VA request can carry nine semantic image references in the generated API graph.
4. A long integrated script produces ordered 5–15 second segment specs with H3-legal frame counts.
5. Continuation segment N+1 loads latent slot N and saves slot N+1.
6. Missing optional external nodes never break the existing Native/Spectrum H3 path.
7. No user-supplied non-commercial workflow JSON or unlicensed LtoJ source is committed to the repository.
