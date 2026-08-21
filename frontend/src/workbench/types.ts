export const STAGE_KEYS = [
  "import",
  "story",
  "character",
  "storyboard",
  "keyframe",
  "video",
  "audio",
  "compose",
  "export",
] as const;

export type StageKey = (typeof STAGE_KEYS)[number];

export interface StageAutomation {
  stage_key: StageKey;
  auto_produce: boolean;
  quality_threshold: number;
  max_quality_retries: number;
  auto_advance: boolean;
  provider_settings: Record<string, unknown>;
}

export interface StageSummary {
  stage_key: StageKey;
  status: string;
  progress: number;
  waiting_review: number;
  automation: StageAutomation;
}

export interface WorkspaceSnapshot {
  project_id: string;
  title: string;
  source_path: string;
  version: string;
  progress: number;
  pending_reviews: number;
  active_jobs: number;
  estimated_minutes: number | null;
  stages: StageSummary[];
  system_health: Record<string, unknown>;
}

export interface ProjectAsset {
  id: number;
  project_id: string;
  job_id: string;
  step_id: string;
  kind: string;
  path: string;
  media_url: string;
  stage_key: string | null;
  scene_id: string;
  shot_id: string;
  version: number;
  parent_artifact_id: number | null;
  active: boolean;
  quality_status: string;
  quality_attempt: number;
  quality_report: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AssetFilters {
  kind?: string;
  stage_key?: string;
  scene_id?: string;
  shot_id?: string;
  quality_status?: string;
  active?: boolean;
}
