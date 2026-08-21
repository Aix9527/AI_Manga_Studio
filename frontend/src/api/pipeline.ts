/**
 * Pipeline API Client — Phase 5 Pipeline Orchestration
 */

import { request } from '@/api/client';

const BASE = '/pipeline';

export interface PipelineStageResult {
  stage: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  message: string;
  data?: Record<string, unknown>;
  duration_ms?: number;
}

export interface PipelineRequest {
  text: string;
  title?: string;
  novel_id?: string;
}

export interface PipelineResponse {
  status: string;
  characters_found: number;
  shots_planned: number;
  prompts_compiled: number;
  duration_ms: number;
  stages: Record<string, string>;
}

export interface CompileShotRequest {
  id?: string;
  scene_id?: string;
  index?: number;
  shot_type: string;
  camera_angle: string;
  camera_movement?: string;
  description: string;
  action?: string;
  dialogue?: string;
  emotion?: string;
  narration?: string;
  duration?: number;
  positive_prompt?: string;
  negative_prompt?: string;
  seed?: number;
  image_model?: string;
  video_model?: string;
  character_ids?: string[];
}

export interface CompiledPrompt {
  positive_prompt: string;
  negative_prompt: string;
  parameters: Record<string, unknown>;
}

export interface PipelineStats {
  version: string;
  phases: Record<string, boolean>;
  modules: Record<string, string[]>;
}

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  return request<T>(`${BASE}${url}`, options);
}

// ── Pipeline Run ──

export function runPipeline(req: PipelineRequest): Promise<PipelineResponse> {
  return api<PipelineResponse>('/run', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ── Compile ──

export function compileSingleShot(
  shotData: CompileShotRequest,
  characterIds?: string[]
): Promise<CompiledPrompt> {
  const ids = characterIds ?? shotData.character_ids ?? [];
  const search = new URLSearchParams();
  for (const id of ids) search.append('character_ids', id);
  const params = search.size ? `?${search.toString()}` : '';
  return api<CompiledPrompt>(`/compile/shot${params}`, {
    method: 'POST',
    body: JSON.stringify({ ...shotData, character_ids: ids }),
  });
}

// ── Stats ──

export function getPipelineStats(): Promise<PipelineStats> {
  return api<PipelineStats>('/stats');
}

// ── Health ──

export function healthCheck(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/health');
}
