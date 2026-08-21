/**
 * Multi-Project Production Orchestrator API (Phase 13.5-A, GPT spec).
 * Season / Resource / GPU Queue / Budget / Scheduler / Audit.
 */

import { request } from "@/api/client";

export interface Season {
  id: string;
  project_id: string;
  season_no: number;
  name: string;
  target_episodes: number;
  status: string;
  episode_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ProjectResource {
  id: string;
  project_id: string;
  season_id: string;
  gpu_capacity: number;
  gpu_allocated: number;
  budget_allocated: number;
  deadline: string;
  priority: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface BudgetSummary {
  project_id: string;
  spent: number;
  monthly_limit: number;
  ratio: number;
  status: "ok" | "warning" | "exceeded";
  entries: number;
  cost_meter_shots: number;
  cost_meter_gpu_time_s: number;
}

export interface SchedulePlan {
  id: string;
  project_id: string;
  status: string;
  scheduled: string[];
  blocked: Array<{ episode_id: string; reasons: string[] }>;
  parallelism: number;
  reviewer: string;
  created_at: string;
  decided_at: string;
}

export const listSeasons = (projectId?: string): Promise<{ seasons: Season[] }> =>
  request(`/production-orchestrator/seasons${projectId ? `?project_id=${projectId}` : ""}`);

export const createSeason = (body: { project_id: string; season_no?: number; name?: string; target_episodes?: number }): Promise<Season> =>
  request("/production-orchestrator/seasons", { method: "POST", body: JSON.stringify(body) });

export const attachSeasonEpisode = (seasonId: string, episodeId: string): Promise<Season> =>
  request(`/production-orchestrator/seasons/${seasonId}/episodes/${episodeId}`, { method: "POST", body: JSON.stringify({}) });

export const setSeasonStatus = (seasonId: string, status: string): Promise<Season> =>
  request(`/production-orchestrator/seasons/${seasonId}/status`, { method: "POST", body: JSON.stringify({ status }) });

export const seasonStats = (projectId?: string): Promise<{ seasons: number; episodes_attached: number; by_status: Record<string, number> }> =>
  request(`/production-orchestrator/seasons/stats${projectId ? `?project_id=${projectId}` : ""}`);

export const listResources = (projectId?: string): Promise<{ resources: ProjectResource[] }> =>
  request(`/production-orchestrator/resources${projectId ? `?project_id=${projectId}` : ""}`);

export const planResource = (body: { project_id: string; season_id?: string; gpu_capacity?: number; budget_allocated?: number; deadline?: string; priority?: number }): Promise<ProjectResource> =>
  request("/production-orchestrator/resources", { method: "POST", body: JSON.stringify(body) });

export const resourceStats = (): Promise<{ projects: number; resources: number; gpu_capacity: number; gpu_allocated: number; budget_allocated: number }> =>
  request("/production-orchestrator/resources/stats");

export const gpuQueueRecommend = (body: { limit?: number; gpu_capacity?: number }): Promise<{ queued: number; recommended: Array<{ task_id: string; task_type: string; project_id: string; priority: number; score: number; deadline_factor: number; gpu_fit_score: number; retry_penalty: number }>; note: string }> =>
  request("/production-orchestrator/gpu-queue/recommend", { method: "POST", body: JSON.stringify(body) });

export const budgetSummary = (projectId: string): Promise<BudgetSummary> =>
  request(`/production-orchestrator/budgets/${projectId}`);

export const setBudgetPolicy = (projectId: string, body: { monthly_limit: number; episode_limit?: number; warning_threshold?: number; hard_limit?: number; override_requires_approval?: boolean }): Promise<Record<string, unknown>> =>
  request(`/production-orchestrator/budgets/${projectId}/policy`, { method: "POST", body: JSON.stringify(body) });

export const recordBudgetCost = (projectId: string, body: { amount: number; source?: string; note?: string }): Promise<BudgetSummary> =>
  request(`/production-orchestrator/budgets/${projectId}/cost`, { method: "POST", body: JSON.stringify(body) });

export const authorizeBudget = (projectId: string, amount: number): Promise<{ allowed: boolean; status: string; requires_approval: boolean; reason: string }> =>
  request(`/production-orchestrator/budgets/${projectId}/authorize`, { method: "POST", body: JSON.stringify({ amount }) });

export const approveBudgetOverride = (projectId: string, reviewer = "producer"): Promise<{ project_id: string; approved: boolean; reviewer: string }> =>
  request(`/production-orchestrator/budgets/${projectId}/override`, { method: "POST", body: JSON.stringify({ reviewer }) });

export const registerDependency = (body: { episode_id: string; requires?: string[]; previous_episode_asset?: string }): Promise<Record<string, unknown>> =>
  request("/production-orchestrator/schedules/dependencies", { method: "POST", body: JSON.stringify(body) });

export const buildSchedulePlan = (projectId: string, maxParallel = 2): Promise<SchedulePlan> =>
  request("/production-orchestrator/schedules/build", { method: "POST", body: JSON.stringify({ project_id: projectId, max_parallel: maxParallel }) });

export const listSchedulePlans = (projectId?: string): Promise<{ plans: SchedulePlan[] }> =>
  request(`/production-orchestrator/schedules${projectId ? `?project_id=${projectId}` : ""}`);

export const approveSchedulePlan = (planId: string, reviewer = "producer"): Promise<SchedulePlan> =>
  request(`/production-orchestrator/schedules/${planId}/approve`, { method: "POST", body: JSON.stringify({ reviewer }) });

export const dispatchSchedulePlan = (planId: string): Promise<{ plan_id: string; dispatched: string[]; status: string }> =>
  request(`/production-orchestrator/schedules/${planId}/dispatch`, { method: "POST", body: JSON.stringify({}) });

export const orchestratorAudit = (limit = 100): Promise<{ audit: Array<{ action: string; target: string; detail: string; actor: string; at: string }> }> =>
  request(`/production-orchestrator/audit?limit=${limit}`);