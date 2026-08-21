/**
 * Prompt OS API (Phase 13.6, GPT spec).
 * 十引擎 / Prompt DNA / ShotDesign 8 层 / Compiler / Evolution.
 */

import { request } from "@/api/client";

export interface DNARecord {
  id: string;
  kind: string;
  name: string;
  description: string;
  values: Record<string, unknown>;
  tags: string[];
  usage_count: number;
  success_score: number;
  created_at: string;
  updated_at: string;
}

export interface ShotDesignRecord {
  id: string;
  version: string;
  parent_version: string;
  layers: Record<string, unknown>;
  continuity_contract: {
    characters: Record<string, unknown>;
    props: Record<string, unknown>;
    space: Record<string, unknown>;
    constraints: string[];
  };
  transition_in: string;
  transition_out: string;
  duration_seconds: number;
  negative_words: string[];
  status: string;
  approved_by: string;
  approved_at: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface EngineRecord {
  key: string;
  name: string;
  description: string;
  input_schema: Record<string, string>;
  output_schema: Record<string, string>;
  status: string;
  version: string;
  created_at: string;
}

export interface LeaderboardRow {
  shot_design_id: string;
  samples: number;
  score: number;
  completion: number;
  like: number;
  comment: number;
  favorite: number;
  views: number;
}

export interface EvolutionRecord {
  id: string;
  shot_design_id: string;
  score: number;
  samples: number;
  status: string;
  suggested_layers: Record<string, string>;
  reason: string;
  reviewer: string;
  decided_at: string;
  applied_version: string;
  created_at: string;
}

export interface PromptOSStats {
  engines: number;
  engines_active: number;
  dna: { entries: number; by_kind: Record<string, number>; kinds: string[] };
  shot_designs: number;
  evolution: {
    metrics: number;
    records: number;
    by_status: Record<string, number>;
    weights: Record<string, number>;
    min_samples: number;
    min_score: number;
    auto_learning: boolean;
    auto_apply: boolean;
  };
  layers: string[];
}

export const promptOsStats = (): Promise<PromptOSStats> => request("/prompt-os/stats");

export const listEngines = (): Promise<{ engines: EngineRecord[] }> => request("/prompt-os/engines");

export const runEngine = (key: string, body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request(`/prompt-os/engines/${key}/run`, { method: "POST", body: JSON.stringify(body) });

export const listDna = (kind?: string): Promise<{ entries: DNARecord[] }> =>
  request(`/prompt-os/dna${kind ? `?kind=${kind}` : ""}`);

export const addDna = (body: Partial<DNARecord>): Promise<DNARecord> =>
  request("/prompt-os/dna", { method: "POST", body: JSON.stringify(body) });

export const compileShot = (body: Record<string, unknown>): Promise<ShotDesignRecord> =>
  request("/prompt-os/compile", { method: "POST", body: JSON.stringify(body) });

export const compileSequence = (loglines: string[]): Promise<{ shots: ShotDesignRecord[] }> =>
  request("/prompt-os/compile/sequence", { method: "POST", body: JSON.stringify(loglines) });

export const listShotDesigns = (): Promise<{ shots: ShotDesignRecord[] }> => request("/prompt-os/shot-designs");

export const setShotDesignStatus = (id: string, status: string, approvedBy = "human"): Promise<ShotDesignRecord> =>
  request(`/prompt-os/shot-designs/${id}/status`, { method: "POST", body: JSON.stringify({ status, approved_by: approvedBy }) });

export const deriveShotDesignVersion = (id: string, overrides: Record<string, unknown> = {}, notes = ""): Promise<ShotDesignRecord> =>
  request(`/prompt-os/shot-designs/${id}/versions`, { method: "POST", body: JSON.stringify({ overrides, notes }) });

export const recordMetric = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/prompt-os/metrics", { method: "POST", body: JSON.stringify(body) });

export const evolutionLeaderboard = (limit = 20): Promise<{ leaderboard: LeaderboardRow[] }> =>
  request(`/prompt-os/leaderboard?limit=${limit}`);

export const proposeCandidates = (): Promise<{ candidates: EvolutionRecord[] }> =>
  request("/prompt-os/evolution/candidates", { method: "POST", body: JSON.stringify({}) });

export const listEvolutionRecords = (status?: string): Promise<{ records: EvolutionRecord[] }> =>
  request(`/prompt-os/evolution${status ? `?status=${status}` : ""}`);

export const reviewCandidate = (id: string, decision: string, reviewer = "human"): Promise<EvolutionRecord> =>
  request(`/prompt-os/evolution/${id}/review`, { method: "POST", body: JSON.stringify({ decision, reviewer }) });

export const applyCandidate = (id: string): Promise<EvolutionRecord> =>
  request(`/prompt-os/evolution/${id}/apply`, { method: "POST", body: JSON.stringify({}) });