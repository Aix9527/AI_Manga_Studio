# v0.10 Timeline / NLE Persistence Design

Date: 2026-09-05
Status: Approved design, self-reviewed
Branch: `feat/v0.10-timeline-nle-persistence`

## 1. Purpose

Replace the current placeholder timeline lanes with a real, persisted, non-destructive NLE while preserving the existing AI production, QC, Job, Artifact, Worker, and FFmpeg execution chain.

Timeline is an editing/control domain, not a second render engine. It freezes an immutable Snapshot, formally QC-validates that Snapshot, compiles it into a deterministic Canonical Composition Spec, then delegates rendering to the existing composition/export path.

## 2. Frozen product decisions

1. The underlying model is professional free multi-track; v0.10 UI initially exposes magnetic V1 plus dialogue, BGM/SFX, and subtitle tracks.
2. Editing uses one mutable Draft, immutable Snapshots, a persistent Operation Log, and periodic Draft Checkpoints.
3. Clips pin a concrete Artifact identity/version. New AI outputs never silently replace edited clips.
4. Video, dialogue, and subtitles use Link Groups by default and may be explicitly unlinked for J-cuts, L-cuts, or independent subtitle timing.
5. The backend supports overlap, but v0.10 V1 permits overlap only when an explicit Transition legalizes it.
6. Undo/Redo is persistent and survives reload.
7. Drafts receive cheap structural preflight; formal QC runs against immutable Snapshots.
8. Export is `Snapshot -> QC -> Canonical Composition Spec -> existing Job/Worker/FFmpeg`.
9. Persisted time uses integer ticks with rational FPS mapping; floating-point seconds are never authoritative.
10. Drag/trim movement is local preview only; one semantic operation is committed on pointer release and backend state is authoritative.

## 3. Architecture

```text
Project
  |
  +-- Artifact Registry
  |
  +-- Timeline
        |
        +-- Draft
        |     +-- Tracks / Clips / Link Groups / Transitions / Subtitle Cues
        |     +-- Operation Log
        |     +-- Checkpoints
        |
        +-- Immutable Snapshot
              |
              +-- Snapshot QC records
              |
              +-- Canonical Composition Spec records
                         |
                         v
                  existing Job / Worker / FFmpeg
                         |
                         v
                    Export Artifact
```

### 3.1 Boundaries

`TimelineRepository` owns SQLite persistence only.

`TimelineService` owns edit semantics, transactions, invariants, optimistic concurrency, ripple behavior, linking, transitions, Undo/Redo, checkpoints, and Snapshot creation.

`TimelineQcService` owns formal Snapshot QC state/results. It may create/update QC records, but it never mutates Snapshot state.

`TimelineCompiler` owns deterministic conversion from immutable Snapshot state plus output profile to Canonical Composition Spec.

Existing `JobService`, Worker, production providers, Artifact lifecycle, review gates, and FFmpeg execution remain authoritative for rendering.

Timeline code must not invoke FFmpeg directly.

## 4. Persistence model

Timeline remains in the existing SQLite database but uses its own domain tables.

### 4.1 `timelines`

```text
id                  TEXT PRIMARY KEY
project_id          TEXT NOT NULL
name                TEXT NOT NULL
timebase_hz         INTEGER NOT NULL
fps_num             INTEGER NOT NULL
fps_den             INTEGER NOT NULL
active_draft_id     TEXT
latest_snapshot_no  INTEGER NOT NULL DEFAULT 0
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
```

Default `timebase_hz = 1_000_000`. Video frame positions use integer/rational arithmetic derived from `fps_num/fps_den`.

### 4.2 `timeline_drafts`

```text
id                  TEXT PRIMARY KEY
timeline_id         TEXT NOT NULL
revision            INTEGER NOT NULL
base_snapshot_id    TEXT NULL
head_operation_seq  INTEGER NOT NULL DEFAULT 0
redo_operation_seq  INTEGER NULL
dirty               INTEGER NOT NULL DEFAULT 0
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
```

Every mutation includes `expected_revision`. Mismatch returns `409 Conflict`. Revision is monotonic, including Undo/Redo.

### 4.3 `timeline_tracks`

```text
id                  TEXT PRIMARY KEY
draft_id            TEXT NOT NULL
track_type          TEXT NOT NULL
role                TEXT NOT NULL
name                TEXT NOT NULL
sort_index          INTEGER NOT NULL
locked              INTEGER NOT NULL DEFAULT 0
muted               INTEGER NOT NULL DEFAULT 0
hidden              INTEGER NOT NULL DEFAULT 0
metadata_json       TEXT NOT NULL DEFAULT '{}'
```

Track types: `video`, `audio`, `subtitle`.

Defined roles include `video.main`, `video.overlay`, `audio.dialogue`, `audio.bgm`, `audio.sfx`, `subtitle.primary`, and `subtitle.secondary`.

The initial UI exposes V1, A1 dialogue, A2 BGM/SFX, and S1 subtitles; the model permits later V2/V3/A3 tracks.

### 4.4 `timeline_clips`

```text
id                  TEXT PRIMARY KEY
draft_id            TEXT NOT NULL
track_id            TEXT NOT NULL
artifact_id         INTEGER NULL
artifact_version    INTEGER NULL
clip_type           TEXT NOT NULL
timeline_start_tick INTEGER NOT NULL
duration_tick       INTEGER NOT NULL
source_in_tick      INTEGER NOT NULL DEFAULT 0
source_out_tick     INTEGER NOT NULL
link_group_id       TEXT NULL
enabled             INTEGER NOT NULL DEFAULT 1
locked              INTEGER NOT NULL DEFAULT 0
gain_db             REAL NULL
playback_rate_num   INTEGER NOT NULL DEFAULT 1
playback_rate_den   INTEGER NOT NULL DEFAULT 1
metadata_json       TEXT NOT NULL DEFAULT '{}'
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
```

A Clip pins a concrete Artifact identity/version and never resolves dynamically to the latest active Artifact.

### 4.5 `timeline_link_groups`

```text
id              TEXT PRIMARY KEY
draft_id        TEXT NOT NULL
group_type      TEXT NOT NULL
anchor_clip_id  TEXT
created_at      TEXT NOT NULL
```

Linked members move by a common timeline delta. Unlinking removes only the relationship and does not realign media.

### 4.6 `timeline_transitions`

```text
id                  TEXT PRIMARY KEY
draft_id            TEXT NOT NULL
track_id            TEXT NOT NULL
from_clip_id        TEXT NOT NULL
to_clip_id          TEXT NOT NULL
transition_type     TEXT NOT NULL
duration_tick       INTEGER NOT NULL
params_json         TEXT NOT NULL DEFAULT '{}'
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
```

Initial explicit transitions are `crossfade`, `fade_to_black`, and `fade_from_black`. A plain cut is adjacent Clips with no transition row.

### 4.7 `timeline_subtitle_cues`

```text
id                  TEXT PRIMARY KEY
draft_id            TEXT NOT NULL
track_id            TEXT NOT NULL
clip_id             TEXT NULL
link_group_id       TEXT NULL
start_tick          INTEGER NOT NULL
end_tick            INTEGER NOT NULL
text                TEXT NOT NULL
speaker             TEXT NOT NULL DEFAULT ''
style_json          TEXT NOT NULL DEFAULT '{}'
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
```

Subtitles are first-class editable entities, not hidden inside Clip metadata.

### 4.8 `timeline_operations`

```text
id                  TEXT PRIMARY KEY
draft_id            TEXT NOT NULL
seq                  INTEGER NOT NULL
operation_type      TEXT NOT NULL
payload_json        TEXT NOT NULL
inverse_json        TEXT NOT NULL
branch_state        TEXT NOT NULL DEFAULT 'active'
actor               TEXT NOT NULL DEFAULT 'user'
created_at          TEXT NOT NULL
```

Initial operations: `ADD_CLIP`, `REMOVE_CLIP`, `MOVE_CLIP`, `TRIM_CLIP`, `SPLIT_CLIP`, `LINK_CLIPS`, `UNLINK_CLIPS`, `ADD_TRACK`, `REMOVE_TRACK`, `REORDER_TRACK`, `ADD_TRANSITION`, `UPDATE_TRANSITION`, `REMOVE_TRANSITION`, `ADD_SUBTITLE`, `UPDATE_SUBTITLE`, `REMOVE_SUBTITLE`, and `REPLACE_ARTIFACT_VERSION`.

Undo executes the stored inverse. Undo followed by a new edit marks the old redo branch abandoned rather than deleting its audit history.

### 4.9 `timeline_checkpoints`

```text
id                  TEXT PRIMARY KEY
draft_id            TEXT NOT NULL
operation_seq       INTEGER NOT NULL
revision            INTEGER NOT NULL
state_json          TEXT NOT NULL
state_sha256        TEXT NOT NULL
created_at          TEXT NOT NULL
```

Default checkpoint frequency is every 50 committed operations, plus before Snapshot creation and after large batch/ripple operations.

### 4.10 `timeline_snapshots` — immutable payload only

```text
id                    TEXT PRIMARY KEY
timeline_id           TEXT NOT NULL
snapshot_no           INTEGER NOT NULL
source_draft_revision INTEGER NOT NULL
state_json            TEXT NOT NULL
state_sha256          TEXT NOT NULL
duration_tick         INTEGER NOT NULL
created_at            TEXT NOT NULL
```

After insert, these rows are immutable. Snapshot creation freezes complete track/clip/transition/subtitle/timebase state and every source Artifact identity/version/path identity/SHA needed for reproducibility. A Snapshot does not merely store mutable Draft row IDs.

### 4.11 `timeline_snapshot_qc_runs`

```text
id              TEXT PRIMARY KEY
snapshot_id     TEXT NOT NULL
attempt         INTEGER NOT NULL
status          TEXT NOT NULL
report_json     TEXT NOT NULL DEFAULT '{}'
started_at      TEXT NOT NULL
completed_at    TEXT NULL
created_at      TEXT NOT NULL
UNIQUE(snapshot_id, attempt)
```

QC state is mutable operational data associated with a Snapshot; it is not stored inside the immutable Snapshot payload. Effective QC status is the latest QC attempt.

Allowed states: `running`, `passed`, `failed`, `stale`.

### 4.12 `timeline_composition_specs`

```text
id                      TEXT PRIMARY KEY
snapshot_id             TEXT NOT NULL
output_profile_json     TEXT NOT NULL
compiler_version        TEXT NOT NULL
spec_json               TEXT NOT NULL
spec_sha256             TEXT NOT NULL
created_at              TEXT NOT NULL
UNIQUE(snapshot_id, spec_sha256)
```

A Composition Spec is immutable once compiled. Different output profiles or compiler versions may create different spec records for the same immutable Snapshot.

### 4.13 `timeline_export_bindings`

```text
id                  TEXT PRIMARY KEY
composition_spec_id TEXT NOT NULL
job_id              TEXT NOT NULL
artifact_id         INTEGER NULL
status              TEXT NOT NULL
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
```

This operational binding lets export executions progress without mutating either Snapshot or Composition Spec.

## 5. Hard invariants

Backend invariants include:

- `duration_tick > 0`
- `source_out_tick > source_in_tick`
- `timeline_start_tick >= 0`
- source ranges do not exceed source Artifact duration
- subtitle `end_tick > start_tick`
- referenced Artifacts exist
- Snapshot source identities remain available for historical reproducibility
- Snapshot payload rows are immutable after insert
- Composition Spec rows are immutable after insert
- locked tracks reject mutations
- locked Clips reject move/trim/delete
- magnetic V1 has no ordinary gaps
- V1 overlap requires a valid explicit Transition
- Transition duration does not exceed available handles
- `expected_revision` mismatch returns `409 Conflict`
- ripple/batch operations are atomic

Artifacts referenced by immutable Snapshots may become inactive or archived, but they must not be physically deleted while those Snapshots require them for reproducibility.

## 6. Editing contract

### 6.1 Magnetic V1

`video.main` is a magnetic story track. Dragging is reorder/insert semantics rather than arbitrary coordinate placement. Shortening/removing a V1 Clip ripples later V1 Clips. Future `video.overlay` tracks remain free-positioned.

### 6.2 Trim

Trim is non-destructive and changes source range/timeline duration only. V1 trim ripples later V1 content; free tracks do not ripple unrelated media.

### 6.3 Split

Split produces two Clips that reference the same pinned Artifact version with complementary source ranges. No new media is generated. Linked dialogue/subtitle content crossing the split point may be split in the same transaction.

### 6.4 Delete

The model recognizes ripple delete, lift delete, and linked delete. v0.10 exposes ripple delete by default for V1. BGM/SFX does not ripple with V1 unless explicitly linked.

### 6.5 Link / Unlink

Linking creates a relationship without changing timing. Unlinking removes only that relationship, preserving existing J-cut/L-cut timing.

### 6.6 Transition overlap

V1 overlap is legal only where an explicit Transition validates it. Transition creation requires enough unused source handle on both sides. Insufficient handles fail validation; the system does not silently freeze or AI-extend frames.

### 6.7 Artifact replacement

New AI versions only produce upgrade notices. `REPLACE_ARTIFACT_VERSION` can replace one Clip or all relevant references. Existing timing/source ranges are preserved only when the new media supports them. Otherwise the operation fails with structured `replacement_media_too_short`. Batch replacement is all-or-nothing.

### 6.8 Undo / Redo

Every successful operation and every Undo/Redo increments Draft revision. Undo applies an explicit inverse. A new edit after Undo abandons the previous redo branch while retaining audit history.

### 6.9 Frontend commit behavior

Pointer movement is ephemeral local preview. One semantic operation is committed on pointer release. Backend returned Draft state always replaces local committed state.

## 7. Draft preflight and formal Snapshot QC

Draft preflight is cheap and structural. It reports missing Artifact references, invalid ranges, illegal V1 gaps/overlap, broken transitions/link groups, subtitle timing problems, source overflow, and newer Artifact availability.

Heavy media checks are not run on every drag.

Formal QC always targets an immutable Snapshot. It includes structural integrity, media quality checks where supported, and production gates including no pending/failed required QC and no review bypass.

A Snapshot is exportable only when its latest valid QC attempt is `passed` and source integrity still verifies at export time.

If a source disappears or its SHA differs from the Snapshot-frozen identity, export fails closed. A new QC run records `stale`; no Snapshot payload is mutated.

## 8. Backend API contract

### 8.1 Timeline lifecycle

```text
GET  /api/projects/{project_id}/timeline
POST /api/projects/{project_id}/timeline/initialize
GET  /api/timelines/{timeline_id}/draft
```

Initialization may create the first Draft from existing active project Artifacts only if no Timeline exists. It never overwrites edited Timeline state.

### 8.2 Operations

```text
POST /api/timelines/{timeline_id}/operations
POST /api/timelines/{timeline_id}/undo
POST /api/timelines/{timeline_id}/redo
```

Requests include `expected_revision`. Responses include the new revision, operation sequence, authoritative Draft, and structural preflight.

### 8.3 Snapshot lifecycle

```text
POST /api/timelines/{timeline_id}/snapshots
GET  /api/timelines/{timeline_id}/snapshots
GET  /api/timelines/{timeline_id}/snapshots/{snapshot_id}
```

Snapshot creation validates all invariants and media identities, freezes state, computes SHA256, inserts once, and never updates the Snapshot payload afterward.

### 8.4 Snapshot QC

```text
POST /api/timeline-snapshots/{snapshot_id}/qc
GET  /api/timeline-snapshots/{snapshot_id}/qc
```

`POST` creates a new QC attempt. `GET` returns attempts plus effective/latest status.

### 8.5 Export

```text
POST /api/timeline-snapshots/{snapshot_id}/export
```

Export requires a valid passed QC attempt, re-verifies source integrity, compiles or resolves an immutable Composition Spec for the requested output profile, and then enters the existing compose/export Job path.

Export idempotency is keyed by `composition_spec_id/spec_sha256`. If an equivalent execution is running, return it. If a successful equivalent Export Artifact exists, return it. Do not create duplicate full production jobs.

QC and review states cannot be bypassed through Timeline APIs.

## 9. Canonical Composition Spec

Conceptual schema:

```json
{
  "schema_version": 1,
  "timeline_snapshot_id": "snap_xxx",
  "timeline_state_sha256": "...",
  "compiler_version": "timeline-compose/v1",
  "timebase": {
    "ticks_per_second": 1000000,
    "fps_num": 24,
    "fps_den": 1
  },
  "output": {
    "width": 1080,
    "height": 1920,
    "fps_num": 24,
    "fps_den": 1
  },
  "duration_tick": 42800000,
  "video_tracks": [],
  "audio_tracks": [],
  "subtitle_tracks": [],
  "transitions": []
}
```

Each media entry freezes at least Clip ID, Artifact ID/version, Artifact SHA256, resolved source path, timeline start, source in/out, and duration.

Compiler responsibilities:

1. Validate immutable Snapshot state.
2. Resolve and verify Artifact paths/SHA.
3. Normalize timing using integer/rational arithmetic.
4. Resolve transition, audio, and subtitle placement.
5. Include all render-affecting output profile values.
6. Emit deterministic canonical serialized data.
7. Calculate `spec_sha256`.

For identical Snapshot state, output profile, and compiler version, `spec_sha256` must be deterministic.

The compiler does not create or execute FFmpeg commands. Existing composition execution translates the spec into renderer-specific commands.

## 10. Provenance

Timeline export Jobs freeze:

```text
timeline_id
snapshot_id
snapshot_no
snapshot_state_sha256
composition_spec_id
composition_spec_sha256
compiler_version
```

Final Export Artifact metadata stores the same Timeline provenance plus `job_id`.

Every render must be traceable to the exact immutable Snapshot and pinned media identities used.

## 11. Frontend NLE

The existing `/timeline` workspace remains the entry point.

### 11.1 Preview

Add play/pause, timecode, previous/next frame, cut navigation, selected Clip information, and Snapshot status.

### 11.2 Real lanes

Replace placeholder blocks with persisted data:

```text
V1 Main Video : [shot1][shot2][shot3]
A1 Dialogue   :        [voice2][voice3]
A2 BGM/SFX    : [--------- bgm --------]
S1 Subtitle   :        [sub2]  [sub3]
```

Initial UI operations: Clip selection, magnetic reorder, trim, split, ripple delete, Undo/Redo, Link/Unlink, transition add/remove, dialogue/BGM timing adjustment, subtitle text/timing editing, Artifact version replacement, Snapshot creation/QC/export.

### 11.3 Inspector

Right pane switches between Clip, Audio, Subtitle, Transition, and Snapshot/QC inspectors.

### 11.4 Snapping

Support frame boundaries, Clip start/end, playhead, transition boundaries, and subtitle boundaries. Video commits land on exact valid frame boundaries; audio/subtitles may retain finer tick precision.

### 11.5 Link UX

Linked content displays explicit link state. Independent movement of linked content requires explicit unlink; UI does not silently break the relationship.

### 11.6 Artifact upgrade UX

Clips show pinned version and newer-version availability. User may replace selected Clip, replace all compatible references, or keep the current version.

### 11.7 Waveform

Waveforms use cached peak data keyed by source Artifact SHA. Raw PCM is not stored in SQLite. Cache invalidates when source identity changes.

### 11.8 Draft vs Snapshot UX

UI separates Draft Preflight from Selected Snapshot QC and always explains why export is disabled.

## 12. Implementation slices

### Slice 1 — Timeline Domain Foundation

SQLite schema, repository, models/schemas, initialization/read, revision/concurrency, immutable Snapshot foundation.

### Slice 2 — Core Editing Engine

MOVE, TRIM, SPLIT, RIPPLE_DELETE, LINK/UNLINK, Undo/Redo, checkpoints, invariants, and transactionality.

### Slice 3 — Real Timeline UI

Persisted Track/Clip rendering, playhead/zoom, drag, trim, split, delete, Undo/Redo, Link state, and backend-authoritative reconciliation.

### Slice 4 — Transition / Subtitle / Artifact Upgrade

Transitions, subtitle editing, waveform cache/render, newer Artifact detection, and replace one/all references.

### Slice 5 — Snapshot QC + Composition Export

Snapshot creation, formal QC records, deterministic Composition Spec compilation, existing Job integration, idempotent export, and export provenance.

v0.10 is not complete until Slice 5 closes the full edit-to-export loop.

## 13. Testing contract

Backend coverage must include Timeline initialization; revision conflict; ripple move; trim; source overflow rejection; exact-frame and linked split; ripple/linked delete; Link/Unlink; illegal overlap rejection; transition overlap and insufficient-handle behavior; Artifact replacement and atomic rollback; Undo/Redo and abandoned redo branches; checkpoint restore; Snapshot payload immutability/SHA determinism; QC records not mutating Snapshot payload; Composition Specs not mutating Snapshot payload; Artifact hash mismatch; Snapshot QC gate; Composition Spec determinism; duplicate export idempotency; pending/failed QC rejection; and waiting-review bypass rejection.

Frontend coverage must include removal of placeholder lanes; real Draft rendering; Clip selection; preview-only dragging until pointer release; trim; split; Undo/Redo; revision-conflict reload; Link state/explicit unlink; Artifact upgrade badge; transition validation; Snapshot/QC state; and precise export-disabled reasons.

End-to-end acceptance:

```text
Create/import project media
-> initialize Timeline
-> reorder shot
-> trim
-> split
-> edit subtitle
-> add crossfade
-> create immutable Snapshot
-> formal QC
-> export
-> verify final Artifact provenance
```

Recovery acceptance:

```text
edit -> refresh browser -> Draft restored -> Undo still works
```

Integrity acceptance:

```text
Snapshot passes QC
-> source Artifact file is externally replaced
-> export fails closed
-> Snapshot state_sha256 remains unchanged
```

## 14. Explicitly out of scope for v0.10

- V2/V3 professional overlay UI
- picture-in-picture
- nested/compound sequences
- multicam
- speed-ramp UI
- slip/slide/roll edit UI
- adjustment layers
- keyframed effect curves
- effect node graph
- collaboration / CRDT
- cloud Timeline sync
- direct external NLE/Resolve bridge

The persistence model must not prevent later addition of these capabilities, but v0.10 must not partially implement them.

## 15. Success criteria

v0.10 succeeds when `/timeline` becomes a real persisted NLE with non-destructive revision-safe editing, reload-safe Undo/Redo, explicit Artifact version pinning, magnetic V1 on a professional multi-track foundation, transitions/audio/subtitle editing, immutable Snapshots, formal QC gates, deterministic Composition Specs, existing Job/Worker/FFmpeg export integration, and exact final-Artifact provenance.

The system retains one authoritative production/render pipeline and creates no parallel renderer or QC/review bypass.