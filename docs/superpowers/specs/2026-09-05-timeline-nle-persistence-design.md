# v0.10 Timeline / NLE Persistence Design

Date: 2026-09-05
Status: Approved design
Branch: `feat/v0.10-timeline-nle-persistence`

## 1. Purpose

Replace the current placeholder timeline lanes with a real, persisted, non-destructive NLE while preserving the existing AI production, QC, Job, Artifact, Worker, and FFmpeg execution chain.

The Timeline is an editing/control domain, not a second render engine. It compiles an immutable Timeline Snapshot into a deterministic Canonical Composition Spec, then delegates rendering to the existing composition/export path.

## 2. Approved product decisions

The following decisions are frozen for v0.10:

1. The underlying model is professional free multi-track, while the v0.10 UI initially exposes a magnetic main video track plus dialogue, BGM/SFX, and subtitle tracks.
2. Editing uses a mutable Draft plus immutable Snapshots and a persistent Operation Log.
3. Timeline Clips pin a concrete Artifact version. New AI outputs only produce an upgrade notification; they never silently replace an edited clip.
4. Video, dialogue, and subtitles use Link Groups by default and may be explicitly unlinked for J-cuts, L-cuts, and independent subtitle timing.
5. The backend permits overlap, but the v0.10 main video track allows overlap only when an explicit Transition legalizes it.
6. Undo/Redo uses persistent operations plus periodic Draft checkpoints.
7. Drafts receive lightweight structural preflight checks; formal QC runs only against immutable Snapshots.
8. Export flow is `Snapshot -> Canonical Composition Spec -> existing Job/Worker/FFmpeg`.
9. Persisted time uses integer ticks with rational FPS mapping. Floating-point seconds are not authoritative.
10. The frontend applies edits optimistically only for visual preview; committed operations are backend-authoritative. High-frequency drag events are not persisted individually.

## 3. Architecture

```text
Project
  |
  +-- Artifact Registry
  |     +-- generated video / dialogue / BGM / images
  |
  +-- Timeline
        |
        +-- Draft
        |     +-- Tracks
        |     +-- Clips
        |     +-- Link Groups
        |     +-- Transitions
        |     +-- Subtitle Cues
        |     +-- Operation Log
        |     +-- Draft Checkpoints
        |
        +-- Immutable Snapshot
                  |
                  +-- Formal QC
                  |
                  v
           Timeline Compiler
                  |
                  v
      Canonical Composition Spec
                  |
                  v
       existing Job / Worker / FFmpeg
                  |
                  v
             Export Artifact
```

### 3.1 Domain boundaries

`TimelineRepository` owns SQLite persistence only.

`TimelineService` owns edit semantics, validation, transactions, optimistic concurrency, ripple behavior, linking, transitions, undo/redo, checkpoints, and snapshot creation.

`TimelineCompiler` owns deterministic conversion from immutable Snapshot state to Canonical Composition Spec.

Existing `JobService`, Worker, production providers, QC infrastructure, Artifact lifecycle, and FFmpeg execution remain authoritative for production/render execution.

The Timeline domain must not invoke FFmpeg directly.

## 4. Persistence model

The Timeline domain uses the existing project SQLite database but separate tables from `ProjectAsset`.

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

Default `timebase_hz` is `1_000_000`. Video frame boundaries are derived with rational arithmetic from `fps_num/fps_den`; floating point is not used as the source of truth.

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

Every mutation requires `expected_revision`. A mismatch returns `409 Conflict` and never silently overwrites newer state. Revision numbers always increase, including Undo/Redo.

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

Allowed `track_type` values in v0.10:

- `video`
- `audio`
- `subtitle`

Defined roles include:

- `video.main`
- `video.overlay`
- `audio.dialogue`
- `audio.bgm`
- `audio.sfx`
- `subtitle.primary`
- `subtitle.secondary`

The first UI exposes V1 main video, A1 dialogue, A2 BGM/SFX, and S1 subtitles. The model does not prevent later V2/V3/A3 tracks.

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

Clips always pin a concrete Artifact identity/version. They never resolve dynamically to the latest active Artifact.

### 4.5 `timeline_link_groups`

```text
id              TEXT PRIMARY KEY
draft_id        TEXT NOT NULL
group_type      TEXT NOT NULL
anchor_clip_id  TEXT
created_at      TEXT NOT NULL
```

AI-created video, dialogue, and subtitle elements may be linked automatically. A linked move/delete/ripple operation applies a common timeline delta to linked members. `UNLINK` removes only the relationship and does not realign content.

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

Initial transition set:

- crossfade
- fade_to_black
- fade_from_black

A normal cut is represented by adjacent clips with no transition row.

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

Subtitles remain first-class editable entities and are not hidden in Clip metadata.

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

Initial operation types:

- `ADD_CLIP`
- `REMOVE_CLIP`
- `MOVE_CLIP`
- `TRIM_CLIP`
- `SPLIT_CLIP`
- `LINK_CLIPS`
- `UNLINK_CLIPS`
- `ADD_TRACK`
- `REMOVE_TRACK`
- `REORDER_TRACK`
- `ADD_TRANSITION`
- `UPDATE_TRANSITION`
- `REMOVE_TRANSITION`
- `ADD_SUBTITLE`
- `UPDATE_SUBTITLE`
- `REMOVE_SUBTITLE`
- `REPLACE_ARTIFACT_VERSION`

Undo executes an explicit inverse operation. If the user undoes and then performs a new edit, abandoned redo operations remain stored for audit but are no longer part of the active redo chain.

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

Default checkpoint frequency is every 50 committed operations, plus mandatory checkpoints before Snapshot creation and after large batch/ripple operations.

### 4.10 `timeline_snapshots`

```text
id                      TEXT PRIMARY KEY
timeline_id             TEXT NOT NULL
snapshot_no             INTEGER NOT NULL
source_draft_revision   INTEGER NOT NULL
state_json              TEXT NOT NULL
state_sha256            TEXT NOT NULL
duration_tick           INTEGER NOT NULL
qc_status               TEXT NOT NULL
qc_report_json          TEXT NOT NULL DEFAULT '{}'
composition_spec_json   TEXT NULL
composition_spec_sha256 TEXT NULL
created_at              TEXT NOT NULL
```

Snapshots are immutable after creation. Any edit creates a new Draft state and, when requested, a new Snapshot.

Snapshot `state_json` freezes complete tracks, clips, transition, subtitle, timebase, Artifact identity, Artifact version, source path identity, and media SHA256 needed for reproducibility. It must not merely store mutable Draft row IDs.

## 5. Hard invariants

The backend, not only the UI, enforces all of the following:

- `duration_tick > 0`
- `source_out_tick > source_in_tick`
- `timeline_start_tick >= 0`
- source ranges cannot exceed Artifact media duration
- subtitle `end_tick > start_tick`
- every referenced Artifact exists
- Snapshot Artifact sources remain available for historical reproducibility
- Snapshots are immutable
- locked tracks reject mutations
- locked clips reject move/trim/delete
- main V1 gaps are disallowed in magnetic mode
- main V1 overlap is disallowed unless covered by a valid explicit Transition
- Transition duration cannot exceed available source handles
- `expected_revision` mismatch returns `409 Conflict`
- batch replacement/ripple edits are atomic

Artifacts referenced by Snapshots may become inactive or archived, but must not be physically deleted while a reproducible Snapshot depends on them.

## 6. Editing semantics

### 6.1 Magnetic V1

`video.main` behaves as a magnetic story track. Dragging is semantically a reorder/insert operation, not arbitrary coordinate placement. Removing or shortening a main-track clip ripples following main-track clips.

`video.overlay` tracks remain free-positioned at the data-model level for later UI expansion.

### 6.2 Trim

Trim is non-destructive. It changes source range and timeline duration only; it never rewrites the media Artifact.

Main-track trim ripples subsequent main-track items. Free tracks do not ripple unrelated content.

### 6.3 Split

Split creates two Clips referencing the same Artifact version with complementary source ranges. No new media is generated.

If linked dialogue or subtitle content crosses the split point, a linked split may split those members as well. Members not covering the split point remain unchanged.

### 6.4 Delete

Supported semantics include `DELETE_RIPPLE`, `DELETE_LIFT`, and linked delete. v0.10 exposes ripple delete for V1 by default; free gap-producing lift delete remains a lower-level/future professional operation.

BGM does not participate in V1 ripple unless the user explicitly links it to a shot.

### 6.5 Link / Unlink

Linking creates a relationship without changing timing. Linked members move together by common delta. Unlinking never snaps or realigns content and therefore preserves J-cut/L-cut timing.

### 6.6 Transitions and overlap

Main-track overlap is legal only if an explicit Transition row validates the overlap. v0.10 UI creates controlled overlap through transitions rather than free manual overlap.

A transition must have sufficient source handles on both adjacent clips. Insufficient handles produce a validation error; the system does not silently freeze or AI-extend frames.

### 6.7 Artifact replacement

New AI versions never alter existing clips automatically. UI reports that a newer Artifact is available.

`REPLACE_ARTIFACT_VERSION` may replace one Clip or all references in a batch. Existing timeline timing and source ranges are preserved only if the new Artifact is long enough. If not, the operation rejects with a structured `replacement_media_too_short` conflict unless the user explicitly selects a future/manual trim-to-fit strategy.

Batch replacement is all-or-nothing.

### 6.8 Undo / Redo

Every committed edit appends an operation and increments Draft revision. Undo applies the stored inverse and also increments revision. Redo reapplies an eligible operation and increments revision.

After Undo, a new edit abandons the old redo branch without deleting its audit history.

### 6.9 Frontend commit behavior

Pointer movement during drag/trim is local ephemeral preview only. A single semantic operation is sent on pointer release. The backend response is authoritative and replaces local committed state.

## 7. Draft preflight and formal QC

Draft preflight is cheap and structural. It may report:

- missing Artifact references
- negative/invalid ranges
- illegal main-track gaps
- illegal overlap
- broken transitions
- broken link groups
- subtitle timing violations
- source-range overflow
- newer Artifact version available

Heavy media checks do not block every edit.

Formal QC runs only on immutable Snapshots and may include:

1. Structural integrity checks.
2. Media checks such as black/static/mosaic, audio presence, clipping/loudness, and subtitle safe area.
3. Production gates such as all required assets passed, no pending QC, no failed QC, and no review bypass.

A Snapshot must be `passed` before export.

If a Snapshot source file disappears or its SHA no longer matches the frozen identity, export fails closed and the Snapshot QC becomes stale/integrity-failed. The renderer must never silently use a different file at the same path.

## 8. Backend API contract

### 8.1 Timeline lifecycle

```text
GET  /api/projects/{project_id}/timeline
POST /api/projects/{project_id}/timeline/initialize
GET  /api/timelines/{timeline_id}/draft
```

Initialization may build the first Draft from existing active project Artifacts when no Timeline exists. It must never overwrite an already edited Timeline.

### 8.2 Operations

```text
POST /api/timelines/{timeline_id}/operations
POST /api/timelines/{timeline_id}/undo
POST /api/timelines/{timeline_id}/redo
```

Operation requests include `expected_revision` and a semantic operation type/payload. Responses include the new revision, operation sequence, authoritative Draft state, and Draft preflight result.

### 8.3 Snapshot lifecycle

```text
POST /api/timelines/{timeline_id}/snapshots
GET  /api/timelines/{timeline_id}/snapshots
GET  /api/timelines/{timeline_id}/snapshots/{snapshot_id}
```

Snapshot creation flushes committed edits, validates all structural invariants and media identities, freezes complete state, and calculates `state_sha256`.

### 8.4 Snapshot QC

```text
POST /api/timeline-snapshots/{snapshot_id}/qc
GET  /api/timeline-snapshots/{snapshot_id}/qc
```

QC states:

- `not_run`
- `running`
- `passed`
- `failed`
- `stale`

### 8.5 Export

```text
POST /api/timeline-snapshots/{snapshot_id}/export
```

Export validates Snapshot integrity and QC, compiles a Composition Spec, stores compiler provenance, then enters the existing compose/export Job path.

The endpoint is idempotent by `(snapshot_id, composition_spec_sha256)` unless the caller explicitly requests a new render attempt under a supported future rerender mode.

If an equivalent Job is running, return it. If a successful equivalent export Artifact exists, return it. Do not create duplicate full production jobs.

Review states and QC gates remain authoritative and cannot be bypassed through Timeline APIs.

## 9. Canonical Composition Spec

The Timeline Compiler emits a deterministic render-neutral schema, conceptually:

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
2. Resolve Artifact paths.
3. Verify Artifact identity and SHA256.
4. Normalize all time values with integer/rational arithmetic.
5. Resolve transitions and audio/subtitle placement.
6. Emit deterministic serialized data.
7. Calculate `composition_spec_sha256`.

For the same Snapshot, output profile, and compiler version, the resulting Composition Spec SHA must be deterministic.

The compiler does not construct or execute FFmpeg commands. Existing composition execution translates the Canonical Composition Spec into renderer-specific commands.

## 10. Provenance

Jobs created from Timeline export freeze at least:

```text
timeline_id
timeline_snapshot_id
timeline_snapshot_no
timeline_state_sha256
composition_spec_sha256
compiler_version
```

Final Export Artifact metadata stores the same Timeline provenance plus `job_id`.

Any final render must be traceable back to the exact immutable editing state and exact pinned media versions that produced it.

## 11. Frontend NLE design

The existing `/timeline` workspace remains the entry point.

### 11.1 Preview

Preview adds play/pause, current timecode, previous/next frame, cut navigation, selected Clip details, and Snapshot status.

### 11.2 Real timeline lanes

Replace placeholder lane blocks with persisted tracks and Clips:

```text
V1 Main Video : [shot1][shot2][shot3]
A1 Dialogue   :        [voice2][voice3]
A2 BGM/SFX    : [--------- bgm --------]
S1 Subtitle   :        [sub2]  [sub3]
```

Initial UI operations:

- select Clip
- magnetic reorder
- left/right trim
- split at playhead
- ripple delete
- Undo/Redo
- Link/Unlink
- add/remove initial transitions
- dialogue timing adjustment
- BGM/SFX timing adjustment
- subtitle text/timing editing
- Artifact version upgrade action
- Snapshot create/QC/export

### 11.3 Inspector

The right pane switches between Clip, Audio, Subtitle, Transition, and Snapshot/QC inspectors.

### 11.4 Snapping

v0.10 supports snapping to:

- frame boundaries
- Clip start/end
- playhead
- transition boundaries
- subtitle boundaries

Video commits always land on a valid video frame boundary. Audio/subtitles may retain finer tick precision.

### 11.5 Link visualization

Linked content displays an explicit linked state. Independent movement of linked content requires explicit unlink; the UI must not silently break relationships.

### 11.6 New Artifact notifications

A Clip shows its pinned version and a badge when a newer Artifact lineage member exists. Users may replace only the selected Clip, replace all references to the shot/source lineage, or keep the current version.

### 11.7 Waveform

Waveforms are real cached peak data, not placeholders and not raw PCM stored in SQLite. Cache identity includes source Artifact SHA. A changed source invalidates the cache.

### 11.8 Draft vs Snapshot UX

The UI clearly separates:

- Draft Preflight: structural editing issues, dirty state, and newer Artifact notices.
- Selected Snapshot QC: immutable Snapshot number, QC state/report, and export readiness.

The UI must always provide a specific reason when export is disabled.

## 12. Implementation slices

### Slice 1 — Timeline Domain Foundation

- SQLite schema
- Timeline repository
- models/schemas
- initialize/read Draft
- revision/concurrency
- immutable Snapshot foundation

### Slice 2 — Core Editing Engine

- MOVE
- TRIM
- SPLIT
- RIPPLE_DELETE
- LINK/UNLINK
- Undo/Redo
- checkpoints
- hard invariants and transactionality

### Slice 3 — Real Timeline UI

- persisted Track/Clip rendering
- playhead and zoom
- drag/reorder
- trim
- split
- delete
- Undo/Redo
- Link visualization
- backend-authoritative reconciliation

### Slice 4 — Transition / Subtitle / Artifact Upgrade

- transitions
- subtitle editing
- waveform cache/render
- newer Artifact detection
- replace one/all references

### Slice 5 — Snapshot QC + Composition Export

- Snapshot creation
- formal Snapshot QC
- Canonical Composition Spec compiler
- deterministic SHA
- Job integration
- idempotent export
- export provenance

v0.10 is not considered complete until Slice 5 closes the edit-to-export loop.

## 13. Testing contract

Backend tests must cover at least:

- Timeline initialization
- Draft revision conflict
- main-track ripple move
- trim left/right
- source overflow rejection
- split at exact frame boundary
- linked split
- ripple delete
- linked delete
- Link/Unlink
- illegal overlap rejection
- transition overlap acceptance
- insufficient transition handles rejection
- Artifact version replacement
- replacement-too-short rejection
- batch replacement transaction rollback
- Undo
- Redo
- Undo then new edit abandons redo branch
- checkpoint restore
- Snapshot immutability
- Snapshot SHA determinism
- Artifact hash mismatch
- Snapshot QC gate
- Composition Spec determinism
- duplicate export idempotency
- failed/pending QC export rejection
- waiting-review bypass rejection

Frontend tests must cover at least:

- placeholder lanes removed
- real Draft rendering
- Clip selection
- drag is preview-only until pointer release
- trim preview/commit
- split
- Undo/Redo
- revision-conflict reload
- Link indicator and explicit unlink behavior
- newer Artifact badge
- transition validation
- Snapshot state
- QC state
- precise export-disabled reasons

End-to-end acceptance includes:

```text
Create/import project media
-> initialize Timeline
-> reorder shot
-> trim
-> split
-> edit subtitle
-> add crossfade
-> create Snapshot
-> formal QC
-> export
-> verify final Artifact provenance
```

Recovery acceptance includes:

```text
edit
-> refresh browser
-> Draft restored
-> Undo remains available
```

Integrity acceptance includes:

```text
Snapshot passes QC
-> source Artifact file is externally replaced
-> export fails closed
```

## 14. Explicitly out of scope for v0.10

The following are deliberately deferred:

- V2/V3 professional overlay UI
- picture-in-picture
- nested sequences
- compound clips
- multicam
- speed-ramp UI
- slip/slide/roll edit UI
- adjustment layers
- keyframed effect curves
- effect node graph
- collaboration / CRDT
- cloud Timeline sync
- direct external NLE/Resolve bridge

The persistence model should not prevent later addition of these capabilities, but v0.10 must not implement them indirectly or partially.

## 15. Success criteria

v0.10 succeeds when the `/timeline` workspace is no longer a placeholder representation and becomes a real persisted NLE with:

- non-destructive, revision-safe editing
- reliable Undo/Redo after page reload
- explicit Artifact version pinning
- magnetic V1 behavior with professional multi-track foundations
- transitions, dialogue/BGM/subtitle editing
- immutable versioned Snapshots
- hard Snapshot QC gates
- deterministic Composition Spec compilation
- existing Job/Worker/FFmpeg export integration
- final Artifact provenance that identifies the exact Snapshot and media identities used

The design preserves one authoritative production/render pipeline and does not create a parallel renderer or QC bypass.