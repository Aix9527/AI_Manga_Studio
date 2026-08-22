# H3 Unified + Segmented Reference Runtime Design

## Goal
Integrate the reusable ideas from the uploaded H3 unified-control and segmented-reference workflow packages into AI Manga Studio without vendoring third-party custom-node source code or replacing the existing Native H3 provider.

## Architectural decision
Keep `minimax_h3` as the proven native fallback. Add a first-party `h3_unified` adaptation layer that translates project/shot data into a stable, testable runtime contract. The contract supports five H3 modes (T2VA/I2VA/FL2VA/L2VA/Ref2VA), a semantic nine-slot reference bundle, optional video/audio references, and segmented generation policy including V6 latent continuity metadata.

The repository will not copy third-party ComfyUI custom-node implementation, PowerShell installers, donation assets, or vendor UI code because the uploaded packages contain no explicit LICENSE/NOTICE. Instead, AI Manga Studio will reproduce only interoperability facts and user-owned configuration concepts in original first-party code.

## Components

### `backend/video/h3_unified/reference_bundle.py`
Defines the nine semantic image slots used by H3 reference generation:
1. `character_identity`
2. `secondary_character`
3. `location`
4. `costume`
5. `prop`
6. `expression`
7. `style`
8. `lighting`
9. `storyboard`

The bundle emits only populated references in deterministic order and validates the overall media-reference budget.

### `backend/video/h3_unified/ui_state.py`
Builds a stable JSON-serializable control state independent of the third-party node package. It normalizes mode, prompt, camera/sound direction, aspect ratio, resolution tier, duration, steps, seed, GPU policy, and reference assets.

### `backend/video/h3_unified/segmented.py`
Models the useful evolution of the segmented workflows:
- queue/loop segmentation
- per-segment prompt/duration
- optional dual-sampling metadata
- optional RTX super-resolution metadata
- V6 latent continuity using Motion Context semantics

This module does not depend on Impact Pack/EasyUse. It produces a provider-neutral execution plan that durable workers can execute one segment at a time.

### `backend/video/providers/minimax_h3_unified_provider.py`
Adapter over the existing ComfyUI contract. It accepts the first-party unified request, chooses native H3 fallback when the external unified node is unavailable, and exposes preflight requirements for optional external nodes such as `LtoJ_H3UnifiedControlDesk` and V6 Motion Context nodes.

## Runtime modes
- `t2va`: prompt only
- `i2va`: first-frame/reference image guided
- `fl2va`: first + last frame
- `l2va`: last-frame constrained
- `ref2va`: multimodal references

## Segmented policy
Default long-form policy on 16 GB VRAM:
- 5–10 second segments
- single sampling by default
- dual sampling opt-in
- super-resolution after generation, not during base sampling
- latent continuity only when Motion Context nodes are confirmed by preflight
- otherwise fall back to frame/reference continuity

## Safety / compatibility
- Existing `backend/video/providers/minimax_h3_provider.py` remains unchanged as fallback.
- No new third-party Python package dependency is required for the first-party contract/builders.
- No third-party custom-node code is vendored.
- Preflight reports missing optional ComfyUI node classes instead of failing at import time.
- 5070 Ti 16 GB gets a conservative `balanced_offload_16gb` runtime profile.

## Testing
Unit tests must cover:
- nine-slot ordering and reference-budget enforcement
- mode validation and `ui_state` serialization
- segment duration splitting and prompt mapping
- V6 latent continuity metadata selection/fallback
- provider preflight node requirements and native fallback selection

Integration remains opt-in until live ComfyUI preflight confirms required external node classes.
