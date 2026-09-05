export interface TimelineClip {
  id: string;
  track_id: string;
  artifact_id: number | null;
  artifact_version: number | null;
  clip_type: string;
  timeline_start_tick: number;
  duration_tick: number;
  source_in_tick: number;
  source_out_tick: number;
  link_group_id: string | null;
  enabled: boolean;
  locked: boolean;
  shot_id: string;
  scene_id: string;
  media_url: string;
}

export interface TimelineTrack {
  id: string;
  track_type: "video" | "audio" | "subtitle" | string;
  role: string;
  name: string;
  sort_index: number;
  locked: boolean;
  muted: boolean;
  hidden: boolean;
  clips: TimelineClip[];
}

export interface TimelineSubtitleCue {
  id: string;
  track_id: string;
  clip_id: string | null;
  link_group_id: string | null;
  start_tick: number;
  end_tick: number;
  text: string;
  speaker: string;
  style: Record<string, unknown>;
}

export interface TimelineTransition {
  id: string;
  track_id: string;
  from_clip_id: string;
  to_clip_id: string;
  transition_type: string;
  duration_tick: number;
  params: Record<string, unknown>;
}

export interface TimelineDraft {
  timeline_id: string;
  draft_id: string;
  project_id: string;
  revision: number;
  timebase_hz: number;
  fps_num: number;
  fps_den: number;
  tracks: TimelineTrack[];
  subtitle_cues: TimelineSubtitleCue[];
  transitions: TimelineTransition[];
}

export interface TimelineSummary {
  timeline_id: string;
  project_id: string;
  name: string;
  active_draft_id: string;
  revision: number;
  timebase_hz: number;
  fps_num: number;
  fps_den: number;
  latest_snapshot_no: number;
}

export interface TimelinePreflight {
  status: string;
  warnings: Array<Record<string, unknown>>;
}

export type TimelineOperation =
  | { type: "MOVE_CLIP"; clip_id: string; insert_before_clip_id?: string | null; insert_after_clip_id?: string | null }
  | { type: "TRIM_CLIP"; clip_id: string; edge: "left" | "right"; target_source_tick: number }
  | { type: "SPLIT_CLIP"; clip_id: string; timeline_tick: number }
  | { type: "REMOVE_CLIP"; clip_id: string; mode?: "ripple" | "lift" | "linked" }
  | { type: "LINK_CLIPS"; clip_ids: string[] }
  | { type: "UNLINK_CLIPS"; clip_ids: string[] }
  | { type: "ADD_TRANSITION"; from_clip_id: string; to_clip_id: string; transition_type: "crossfade" | "fade_to_black" | "fade_from_black"; duration_tick: number; params?: Record<string, unknown> }
  | { type: "UPDATE_TRANSITION"; transition_id: string; duration_tick?: number | null; params?: Record<string, unknown> | null }
  | { type: "REMOVE_TRANSITION"; transition_id: string }
  | { type: "ADD_SUBTITLE"; track_id: string; start_tick: number; end_tick: number; text: string; speaker?: string; clip_id?: string | null; link_group_id?: string | null; style?: Record<string, unknown> }
  | { type: "UPDATE_SUBTITLE"; cue_id: string; start_tick?: number | null; end_tick?: number | null; text?: string | null; speaker?: string | null; style?: Record<string, unknown> | null }
  | { type: "REMOVE_SUBTITLE"; cue_id: string }
  | { type: "REPLACE_ARTIFACT_VERSION"; clip_ids: string[]; artifact_id: number };

export interface TimelineOperationRequest {
  expected_revision: number;
  operation: TimelineOperation;
}

export interface TimelineMutationResult {
  revision: number;
  operation_seq: number;
  draft: TimelineDraft;
  preflight: TimelinePreflight;
}

export interface TimelineSnapshot {
  id: string;
  timeline_id: string;
  snapshot_no: number;
  source_draft_revision: number;
  state_sha256: string;
  duration_tick: number;
  created_at: string;
}

export interface TimelineQcRun {
  id: string;
  snapshot_id: string;
  attempt: number;
  status: "running" | "passed" | "failed" | "stale";
  report: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
}

export interface TimelineQcStatus {
  snapshot_id: string;
  effective_status: "not_run" | "running" | "passed" | "failed" | "stale";
  attempts: TimelineQcRun[];
}

export interface TimelineOutputProfile {
  width: number;
  height: number;
  fps_num: number;
  fps_den: number;
}

export interface TimelineExportResult {
  snapshot_id: string;
  composition_spec_id?: string | null;
  job_id?: string | null;
  artifact_id?: number | null;
  status: string;
}

export interface WaveformEnvelope {
  artifact_id: number;
  bins: number;
  peaks: number[];
  cache_path: string;
}
