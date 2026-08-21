/**
 * Director Evolution Center API — Phase 12.2 (GPT spec).
 */

import { request } from "@/api/client";

const BASE = "/director/evolution";

export interface Accumulation {
  shots: number;
  projects: number;
  episodes: number;
  feedback_records: number;
  revisions: number;
  targets: { shots: number; projects: number; feedback_records: number };
}

export interface PolicyPerformanceRow {
  scene_type: string;
  director: string;
  shots: number;
  avg_score: number | null;
  avg_cost: number | null;
  avg_generation_time: number | null;
  avg_human_score: number | null;
  revisions: number;
}

export interface WinRate {
  counts: Record<string, number>;
  by_scene_type: Array<{ scene_type: string; winner: string; avg_score: number | null; shots: number }>;
}

export interface EvolutionStats {
  source: string;
  policy_version: number | string;
  routes: Record<string, string>;
  policy_learning: Record<string, unknown>;
  accumulation: Accumulation;
  policy_performance: PolicyPerformanceRow[];
  win_rate: WinRate;
}

export interface Candidate {
  id: string;
  scene_type: string;
  from_director: string;
  to_director: string;
  samples_from: number;
  samples_to: number;
  avg_from: number;
  avg_to: number;
  score_delta: number;
  confidence: number;
  reason: string;
}

export interface CandidateQueue {
  mode: string;
  min_samples: number;
  confidence_threshold: number;
  count: number;
  candidates: Candidate[];
}

export interface HistoryEntry {
  id: string;
  action: string;
  created_at: string;
  candidate?: Candidate;
  policy_version_before?: string | number;
  policy_version_after?: string | number;
  diff?: Array<{ scene_type: string; route_before: string; route_after: string }>;
  affected_shots?: number;
  score_delta?: number;
  confidence?: number;
  approved_by?: string;
  rejected_by?: string;
  reason?: string;
  rolled_back_by?: string;
}

export interface ActionResult {
  log: HistoryEntry;
  diff?: Array<{ scene_type: string; route_before: string; route_after: string }>;
  restored_version?: number;
}

export const getEvolutionStats = (source = "production"): Promise<EvolutionStats> =>
  request<EvolutionStats>(`${BASE}/stats?source=${source}`);

export const getCandidates = (source = "production"): Promise<CandidateQueue> =>
  request<CandidateQueue>(`${BASE}/candidates?source=${source}`);

export const getHistory = (source = "production"): Promise<{ entries: HistoryEntry[] }> =>
  request<{ entries: HistoryEntry[] }>(`${BASE}/history?source=${source}`);

export const approveCandidate = (candidateId: string, source = "production", reason = ""): Promise<ActionResult> =>
  request<ActionResult>(`${BASE}/candidates/${encodeURIComponent(candidateId)}/approve?source=${source}`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const rejectCandidate = (candidateId: string, source = "production", reason = ""): Promise<HistoryEntry> =>
  request<HistoryEntry>(`${BASE}/candidates/${encodeURIComponent(candidateId)}/reject?source=${source}`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const rollbackPolicy = (source = "production", reason = ""): Promise<ActionResult> =>
  request<ActionResult>(`${BASE}/rollback?source=${source}`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const seedMockData = (): Promise<{ source: string; accumulation: Accumulation }> =>
  request<{ source: string; accumulation: Accumulation }>(`${BASE}/mock-data`, { method: "POST" });
