/**
 * Production Intelligence API (Phase 13.5-B, GPT spec).
 * B1 EventWarehouse / B2 Analytics / B3 IntelligenceCenter / B4 Candidates.
 */

import { request } from "@/api/client";

export interface WarehouseStats {
  events: number;
  events_by_type: Record<string, number>;
  audit_coverage: number;
  shot_metrics: number;
  episode_metrics: number;
}

export interface CostIntelligence {
  project_id: string;
  planned: number;
  actual: number;
  variance: number;
  factors: Array<{ factor: string; cost: number }>;
  unexplained: number;
  explanation_rate: number;
}

export interface CycleIntelligence {
  project_id: string;
  lead_time_s: number;
  segments: Record<string, number>;
  ratios: Record<string, number>;
}

export interface Overview {
  project_id: string;
  episodes: number;
  shots: number;
  success_rate: number;
  avg_quality: number;
  total_cost: number;
  revision_rate: number;
  cost: CostIntelligence;
  cycle: CycleIntelligence;
}

export interface EpisodeROI {
  episode_id: string;
  project_id: string;
  retention: number;
  hook_score: number;
  cliffhanger: number;
  avg_qc: number;
  failure_rate: number;
  cost_actual: number;
  cost_planned: number;
  roi: number;
  lead_time_s: number;
}

export interface RiskItem {
  risk_type: string;
  target_id: string;
  value: number;
  severity: number;
  message: string;
}

export interface DirectorRow {
  director: string;
  shots: number;
  success_rate: number;
  avg_quality: number;
  avg_revision: number;
  total_cost: number;
}

export interface PromptROIRow {
  prompt_version: string;
  usage: number;
  success_rate: number;
  avg_quality: number;
  revision_rate: number;
}

export interface AnalyticsCandidate {
  id: string;
  target_type: string;
  target_id: string;
  project_id: string;
  suggested_changes: Record<string, unknown>;
  evidence: Record<string, unknown>;
  reason: string;
  status: string;
  reviewer: string;
  created_at: string;
  decided_at: string;
  applied_at: string;
}

export interface ProductionIntelligenceStats {
  warehouse: WarehouseStats;
  candidates: { candidates: number; by_status: Record<string, number>; auto_learning: boolean; auto_apply: boolean };
  governance: {
    auto_learning: boolean;
    auto_apply: boolean;
    auto_deploy: boolean;
    human_approval: boolean;
    rollback: boolean;
    audit: boolean;
  };
}

export const productionIntelligenceStats = (): Promise<ProductionIntelligenceStats> =>
  request("/production-intelligence/stats");

export const recordProductionEvent = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/production-intelligence/events", { method: "POST", body: JSON.stringify(body) });

export const listProductionEvents = (params: Record<string, string> = {}): Promise<{ events: Array<Record<string, unknown>> }> => {
  const query = new URLSearchParams(params).toString();
  return request(`/production-intelligence/events${query ? `?${query}` : ""}`);
};

export const overview = (projectId?: string): Promise<Overview> =>
  request(`/production-intelligence/overview${projectId ? `?project_id=${projectId}` : ""}`);

export const costIntelligence = (projectId?: string): Promise<CostIntelligence> =>
  request(`/production-intelligence/analytics/cost${projectId ? `?project_id=${projectId}` : ""}`);

export const cycleIntelligence = (projectId?: string): Promise<CycleIntelligence> =>
  request(`/production-intelligence/analytics/cycle${projectId ? `?project_id=${projectId}` : ""}`);

export const directorIntelligence = (projectId?: string): Promise<{ directors: DirectorRow[] }> =>
  request(`/production-intelligence/analytics/directors${projectId ? `?project_id=${projectId}` : ""}`);

export const promptRoi = (projectId?: string): Promise<{ prompts: PromptROIRow[] }> =>
  request(`/production-intelligence/analytics/prompt-roi${projectId ? `?project_id=${projectId}` : ""}`);

export const episodeRoi = (projectId?: string): Promise<{ episodes: EpisodeROI[] }> =>
  request(`/production-intelligence/episode-roi${projectId ? `?project_id=${projectId}` : ""}`);

export const riskRadar = (projectId?: string): Promise<{ risks: RiskItem[] }> =>
  request(`/production-intelligence/risk-radar${projectId ? `?project_id=${projectId}` : ""}`);

export const optimizationCandidates = (projectId?: string): Promise<{ suggestions: AnalyticsCandidate[] }> =>
  request(`/production-intelligence/optimization-candidates${projectId ? `?project_id=${projectId}` : ""}`);

export const proposeAnalyticsCandidates = (projectId?: string): Promise<{ candidates: AnalyticsCandidate[] }> =>
  request(`/production-intelligence/candidates${projectId ? `?project_id=${projectId}` : ""}`, { method: "POST", body: JSON.stringify({}) });

export const listAnalyticsCandidates = (status?: string): Promise<{ candidates: AnalyticsCandidate[] }> =>
  request(`/production-intelligence/candidates${status ? `?status=${status}` : ""}`);

export const reviewAnalyticsCandidate = (id: string, decision: string, reviewer = "human"): Promise<AnalyticsCandidate> =>
  request(`/production-intelligence/candidates/${id}/review`, { method: "POST", body: JSON.stringify({ decision, reviewer }) });

export const applyAnalyticsCandidate = (id: string): Promise<AnalyticsCandidate> =>
  request(`/production-intelligence/candidates/${id}/apply`, { method: "POST", body: JSON.stringify({}) });