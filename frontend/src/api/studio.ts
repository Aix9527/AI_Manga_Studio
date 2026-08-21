/**
 * Studio API Client — Phase 10 merge (Director v2 / Chain Runtime / Identity Gate)
 */

import { request } from "@/api/client";

const BASE = "/pipeline";

export interface DirectorPlanRequest {
  text: string;
  novel_id?: string;
  title?: string;
}

export interface ShotDirective {
  shot_id: string;
  shot_intent: string;
  camera: { angle: string; movement: string; distance: string };
  lighting: Record<string, string>;
  emotion_curve: Array<{ t: number; emotion: string; intensity: number }>;
  continuity: { previous_shot: string; constraints: string[] };
  rationale?: string;
  directive_id?: string;
  director_version?: string;
  source_memory_hash?: string;
}

export interface DirectorPlanResponse {
  novel_id: string;
  chapters: number;
  scenes: number;
  shots_total: number;
  sections: Array<Record<string, unknown>>;
  directives: ShotDirective[];
}

export interface ChainLink {
  shot_id: string;
  mode: "keyframe" | "last_frame" | "reset";
  start_image: string;
  last_frame: string;
  continuity_score: number;
  note: string;
}

export interface ChainPlanResponse {
  project: string;
  shots_total: number;
  links: ChainLink[];
  report: { total: number; by_mode: Record<string, number> };
}

export interface ChainStatus {
  project: string;
  completed: string[];
  current: string;
  resume_from: string;
  last_frame: string;
  total_shots: number;
  pending: string[];
  failed: string[];
  manifest_path: string;
}

export interface IdentityVerifyRequest {
  video_path: string;
  character_references: Record<string, number[]>;
  presence_threshold?: number;
  sample_frames?: number;
}

export interface IdentityVerifyResponse {
  video_path: string;
  frames_checked: number;
  per_character: Record<string, { frames_checked: number; frames_present: number; presence_ratio: number; verdict: string }>;
  overall_verdict: string;
  threshold: number;
  presence_threshold: number;
}

export function directorPlan(req: DirectorPlanRequest): Promise<DirectorPlanResponse> {
  return request<DirectorPlanResponse>(`${BASE}/director/plan`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function chainPlan(req: { project_id: string; shots: Record<string, unknown>[] }): Promise<ChainPlanResponse> {
  return request<ChainPlanResponse>(`${BASE}/chain/plan`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function chainStatus(projectId: string): Promise<ChainStatus> {
  return request<ChainStatus>(`${BASE}/chain/status?project_id=${encodeURIComponent(projectId)}`);
}

export function identityVerify(req: IdentityVerifyRequest): Promise<IdentityVerifyResponse> {
  return request<IdentityVerifyResponse>(`${BASE}/identity/verify`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}
