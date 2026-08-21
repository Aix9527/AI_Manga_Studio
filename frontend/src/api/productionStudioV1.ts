/**
 * AI_Manga_Studio v1.0 前端 API 绑定（Phase 1-9 聚合）。
 */

import { request } from "@/api/client";

// ------------------------------------------------------------- Phase 1 Production OS
export interface ProductionProject {
  id: string;
  name: string;
  state: string;
  tasks: Array<{ id: string; task_type: string; agent_type: string; status: string; priority: number }>;
  progress: number;
}

export const v1CreateProject = (body: Record<string, unknown>): Promise<ProductionProject> =>
  request("/production/create", { method: "POST", body: JSON.stringify(body) });

export const v1StartProject = (id: string): Promise<Record<string, unknown>> =>
  request(`/production/start/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify({}) });

export const v1AdvanceProject = (id: string, body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request(`/production/advance/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify(body) });

export const v1ProjectStatus = (id: string): Promise<Record<string, unknown>> =>
  request(`/production/status/${encodeURIComponent(id)}`);

export const v1Projects = (): Promise<{ projects: ProductionProject[] }> =>
  request("/production/projects");

// ------------------------------------------------------------- Phase 2 Creative Agents
export const v1ShotBible = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/creative/shot-bible", { method: "POST", body: JSON.stringify(body) });

// ------------------------------------------------------------- Phase 3-9 /api/v1
export const v1CinemaScore = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/v1/consistency/cinema-score", { method: "POST", body: JSON.stringify(body) });

export const v1Repair = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/v1/consistency/repair", { method: "POST", body: JSON.stringify(body) });

export const v1SeasonPlan = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/v1/studio/season-plan", { method: "POST", body: JSON.stringify(body) });

export const v1EvolutionLearn = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/v1/evolution/learn", { method: "POST", body: JSON.stringify(body) });

export const v1EvolutionDirect = (pattern: string): Promise<Record<string, unknown>> =>
  request(`/v1/evolution/direct/${encodeURIComponent(pattern)}`);

export const v1CeoDecide = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/v1/company/ceo-decide", { method: "POST", body: JSON.stringify(body) });

export const v1Certify = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/v1/infra/certify", { method: "POST", body: JSON.stringify(body) });

export const v1Workers = (): Promise<{ workers: Array<Record<string, unknown>> }> =>
  request("/v1/infra/workers");

export const v1Templates = (): Promise<Record<string, string[]>> => request("/v1/company/templates");

export const v1Shots = (): Promise<{ shots: Array<{ id: string; provider: string; thumb: string; duration_s: string }> }> =>
  request("/v1/shots");
