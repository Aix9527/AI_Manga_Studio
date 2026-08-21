/**
 * Digital Twin API (Phase 14.2, GPT spec).
 * mode=simulation_and_visibility_only / auto_control=false。
 */

import { request } from "@/api/client";

export interface DTState {
  tasks: Record<string, number>;
  task_total: number;
  active_tasks: number;
  workers: Record<string, { tasks: number; active: number; gpu_time_s: number }>;
  worker_count: number;
  worker_idle_rate: number;
  gpu_time_s_total: number;
  assignments: Record<string, number>;
  assignment_active: number;
  waiting_human: number;
  queue_depth: number;
}

export interface DTTimeline {
  episodes: Array<{
    episode_id: string;
    stages: Array<{
      stage: string; role: string; status: string; started_at: string; completed_at: string;
      duration_s: number | null; attempt: number; rework_count: number; blocked_reason: string;
    }>;
    blocked_count: number; rework_count: number; waiting_human: number;
  }>;
  blocked_total: number;
  rework_total: number;
  waiting_human_total: number;
}

export interface DTHeatmap {
  gpu: { usage: number; vram_mb: number; queue_length: number; worker_idle_rate: number; active_tasks: number };
  production: {
    parallel_episodes: number;
    assignment_density: number;
    stage_density: Record<string, number>;
    retry_hotspots: Record<string, number>;
  };
}

export interface DTSimulationRow {
  scenario: string;
  label: string;
  eta_s: number;
  eta_hours: number;
  cost: number;
  bottleneck: string;
  assumptions: Record<string, unknown>;
}

export interface DTRiskCandidate {
  id: string;
  risk_type: string;
  target_type: string;
  target_id: string;
  severity: string;
  evidence: Record<string, unknown>;
  suggestion: string;
  status: string;
  project_id: string;
  created_at: string;
}

export const dtOverview = (): Promise<{ mode: string; auto_control: boolean; state: DTState; timeline_summary: Record<string, number> }> =>
  request("/digital-twin/overview");

export const dtState = (): Promise<DTState> => request("/digital-twin/state");

export const dtTimeline = (): Promise<DTTimeline> => request("/digital-twin/timeline");

export const dtHeatmap = (): Promise<DTHeatmap> => request("/digital-twin/heatmap");

export const dtScenarios = (): Promise<Record<string, { label: string }>> => request("/digital-twin/scenarios");

export const dtSimulate = (scenarios?: string[]): Promise<{ results: DTSimulationRow[]; auto_control: boolean }> =>
  request("/digital-twin/simulate", { method: "POST", body: JSON.stringify({ scenarios: scenarios ?? [] }) });

export const dtPredict = (body: Record<string, unknown> = {}): Promise<{ candidates: DTRiskCandidate[]; count: number; auto_control: boolean }> =>
  request("/digital-twin/predict", { method: "POST", body: JSON.stringify(body) });

export const dtRiskCandidates = (status?: string): Promise<{ candidates: DTRiskCandidate[] }> =>
  request(`/digital-twin/risk-candidates${status ? `?status=${status}` : ""}`);

export const dtDismissRisk = (id: string, body: Record<string, unknown>): Promise<DTRiskCandidate> =>
  request(`/digital-twin/risk-candidates/${encodeURIComponent(id)}/dismiss`, { method: "POST", body: JSON.stringify(body) });
