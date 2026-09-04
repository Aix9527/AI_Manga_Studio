// V5 API type definitions

export type JobStatus =
  | "draft"
  | "queued"
  | "running"
  | "waiting_review"
  | "retry_wait"
  | "failed"
  | "paused"
  | "completed"
  | "cancelled";

export type StepStatus =
  | "pending"
  | "queued"
  | "running"
  | "waiting_review"
  | "retry_wait"
  | "failed"
  | "completed"
  | "invalidated"
  | "cancelled";

export interface JobSummary {
  id: string;
  project_id: string;
  status: JobStatus;
  mode: string;
  desired_state: string;
  current_stage: string;
  current_shot: string;
  progress: number;
  message: string;
  final_video: string;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface StepInfo {
  id: string;
  stage_key: string;
  shot_id: string | null;
  status: StepStatus;
  attempt: number;
  progress: number;
  error_code: string;
  error_message: string;
  quality_attempt: number;
  ui_stage_key: string;
  quality_report: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
}

export interface ArtifactInfo {
  id: number | null;
  project_id: string;
  kind: string;
  path: string;
  sha256: string;
  stage_key: string;
  scene_id: string;
  shot_id: string;
  version: number;
  parent_artifact_id: number | null;
  active: boolean;
  quality_status: string;
  metadata: Record<string, unknown>;
  media_url: string;
}

export interface JobDetail extends JobSummary {
  steps: StepInfo[];
  artifacts: ArtifactInfo[];
}

export interface JobListResponse {
  items: JobSummary[];
}

export interface JobCreateRequest {
  project_id: string;
  input_path: string;
  input_type?: string;
  mode?: "automatic" | "manual_review";
  shot_duration?: number;
  width?: number;
  height?: number;
  fps?: number;
  options?: Record<string, unknown>;
  idempotency_key?: string;
}

export interface RetryRequest {
  step_id?: string;
  comment?: string;
}

export interface ReviewRequest {
  action: "approve" | "edit" | "retry" | "rollback";
  comment?: string;
  patch?: Record<string, unknown>;
}

export type StageExecutionMode = "rerun_node" | "continue";

export interface StageExecutionRequest {
  stage_key: string;
  shot_id?: string;
  mode: StageExecutionMode;
}

export interface RollbackPreview {
  step_id: string;
  invalidated_step_ids: string[];
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface ScannedProject {
  name: string;
  source_path: string;
  file_count: number;
  total_size: number;
  has_outputs: boolean;
  last_modified: string;
}
