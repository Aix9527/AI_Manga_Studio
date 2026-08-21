/**
 * Adaptive Director Router API — Phase 12.6 (GPT spec).
 */

import { request } from "@/api/client";

const BASE = "/director/adaptive";

export interface AdaptiveRecommendation {
  id: string;
  cell: string;
  genre: string;
  scene_type: string;
  role: "primary" | "fallback";
  director: string;
  pvs: number;
  delta_to_next: number;
  samples: number;
  status: "pending" | "approved" | "rejected";
  reason: string;
  evidence: {
    shots: number;
    pvs: Record<string, number>;
    memory: { present: boolean; rows: number } | Record<string, never>;
  };
}

export interface AdaptiveProposal {
  source: string;
  count: number;
  cells: number;
  scope_isolation: { checked: number; violations: number; isolated: boolean };
  production_value_weights: Record<string, number>;
  recommendations: AdaptiveRecommendation[];
}

export interface AbValidation {
  shots: number;
  before: { director_route: Record<string, string>; avg_quality: number; avg_cost: number };
  after: {
    adaptive_primary: Record<string, Record<string, string>>;
    avg_quality: number;
    avg_cost: number;
  };
  quality_gain_pct: number;
  cost_reduction_pct: number;
  cost_delta_pct: number;
  passed: boolean;
  gate: { quality_gain_min: number; cost_reduction_min: number };
}

export interface AdaptiveLogEntry {
  id: string;
  action: string;
  created_at: string;
  cell?: string;
  primary?: string;
  fallback?: string;
  reason?: string;
}

export const getAdaptiveProposal = (source = "mock"): Promise<AdaptiveProposal> =>
  request<AdaptiveProposal>(`${BASE}/proposal?source=${source}`);

export const approveAdaptiveRecommendation = (id: string, source = "mock"): Promise<{ cell: string }> =>
  request<{ cell: string }>(`${BASE}/recommendations/${encodeURIComponent(id)}/approve?source=${source}`, {
    method: "POST",
    body: JSON.stringify({ reason: "dashboard approval" }),
  });

export const rejectAdaptiveRecommendation = (id: string, source = "mock", reason = ""): Promise<{ cell: string }> =>
  request<{ cell: string }>(`${BASE}/recommendations/${encodeURIComponent(id)}/reject?source=${source}`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const rollbackAdaptivePolicy = (source = "mock", reason = ""): Promise<{ restored_version: number }> =>
  request<{ restored_version: number }>(`${BASE}/rollback?source=${source}`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const getAbValidation = (source = "mock", limit = 100): Promise<AbValidation> =>
  request<AbValidation>(`${BASE}/ab-validation?source=${source}&limit=${limit}`);
