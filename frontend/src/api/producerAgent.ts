/**
 * AI Producer Agent API (Phase 14.4, GPT spec).
 * 规划 / 资源建议 / 风险解释 / 制作报告（仅建议，不自动批准/调度）。
 */

import { request } from "@/api/client";

export interface ProducerPlan {
  project_id: string;
  steps: Array<{ priority: number; action: string; detail: string; evidence: Record<string, unknown> }>;
  summary: { active_tasks: number; waiting_human: number; blocked: number; parallel_episodes: number };
  auto_approve: boolean;
  note: string;
}

export interface ResourceSuggestion {
  suggestions: Array<{ kind: string; suggestion: string; evidence: Record<string, unknown> }>;
  auto_schedule: boolean;
  note: string;
}

export interface RiskExplanation {
  candidate: Record<string, unknown>;
  explanation: string;
  evidence: Record<string, unknown>;
  related_graph_nodes: Array<Record<string, unknown>>;
  suggestion: string;
  auto_fix: boolean;
  note: string;
}

export interface ProducerReport {
  project_id: string;
  production_state: Record<string, unknown>;
  prediction: Array<Record<string, unknown>>;
  timeline_summary: Record<string, unknown>;
  knowledge_graph: Record<string, unknown>;
  risks: Array<Record<string, unknown>>;
  optimization_candidates: Array<Record<string, unknown>>;
  plan: Array<Record<string, unknown>>;
  resource_suggestions: Array<Record<string, unknown>>;
  approvals_pending: Record<string, unknown>;
  governance: Record<string, unknown>;
  note: string;
}

export const producerPlan = (projectId?: string): Promise<ProducerPlan> =>
  request(`/producer-agent/plan${projectId ? `?project_id=${projectId}` : ""}`);

export const producerResource = (): Promise<ResourceSuggestion> =>
  request("/producer-agent/resource-suggestion");

export const producerExplainRisk = (candidateId: string): Promise<RiskExplanation> =>
  request(`/producer-agent/risk/${encodeURIComponent(candidateId)}/explain`);

export const producerReport = (projectId?: string): Promise<ProducerReport> =>
  request(`/producer-agent/report${projectId ? `?project_id=${projectId}` : ""}`);
