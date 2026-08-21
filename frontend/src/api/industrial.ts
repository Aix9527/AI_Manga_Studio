/**
 * Industrial AI Drama OS API (Phase 13.1-13.3, GPT spec).
 * Episode / Character Bible v2 / World Bible / Shot DNA / Story Intelligence.
 */

import { request } from "@/api/client";

// ------------------------------------------------------------- Character Bible v2
export interface BibleCompleteness {
  views: number;
  views_required: number;
  expressions: number;
  expressions_required: number;
  actions: number;
  actions_required: number;
  versions: number;
  ratio: number;
}

export interface CharacterBible {
  character_id: string;
  identity: {
    name: string;
    age: number;
    gender: string;
    personality: string[];
    background: string;
    [key: string]: unknown;
  };
  versions: Record<string, { id: string; parent: string; approved: boolean; locked: boolean; [key: string]: unknown }>;
  views: Record<string, { key: string; image_path: string; prompt: string; [key: string]: unknown }>;
  expressions: Record<string, { key: string; image_path: string; prompt: string; [key: string]: unknown }>;
  actions: Record<string, { key: string; description: string; [key: string]: unknown }>;
  completeness: BibleCompleteness;
}

export const createBible = (body: { character_id: string; name?: string; age?: number; gender?: string }): Promise<CharacterBible> =>
  request<CharacterBible>("/characters/bible", { method: "POST", body: JSON.stringify(body) });

export const listBibles = (): Promise<{ bibles: CharacterBible[] }> => request<{ bibles: CharacterBible[] }>("/characters/bible");

export const getBible = (characterId: string): Promise<CharacterBible> => request<CharacterBible>(`/characters/bible/${characterId}`);

export const addBibleVersion = (characterId: string, body: { version_id: string; parent?: string; appearance?: unknown; clothing?: unknown; notes?: string; approved?: boolean }): Promise<CharacterBible> =>
  request<CharacterBible>(`/characters/bible/${characterId}/versions`, { method: "POST", body: JSON.stringify(body) });

export const addBibleView = (characterId: string, body: { key: string; image_path?: string; prompt?: string; seed?: number }): Promise<CharacterBible> =>
  request<CharacterBible>(`/characters/bible/${characterId}/views`, { method: "POST", body: JSON.stringify(body) });

export const addBibleExpression = (characterId: string, body: { key: string; image_path?: string; prompt?: string; seed?: number }): Promise<CharacterBible> =>
  request<CharacterBible>(`/characters/bible/${characterId}/expressions`, { method: "POST", body: JSON.stringify(body) });

export const addBibleAction = (characterId: string, body: { key: string; description?: string; prompt?: string; image_path?: string }): Promise<CharacterBible> =>
  request<CharacterBible>(`/characters/bible/${characterId}/actions`, { method: "POST", body: JSON.stringify(body) });

// ------------------------------------------------------------- World Bible
export interface WorldBible {
  id: string;
  project_id: string;
  name: string;
  era: string;
  technology: string;
  civilization: string;
  power_system: string;
  physics_rules: string[];
  visual_style: string;
  color_language: string;
  [key: string]: unknown;
}

export interface SceneBible {
  id: string;
  project_id: string;
  world_id: string;
  name: string;
  location: string;
  time: string;
  weather: string;
  architecture: string;
  camera_rules: string[];
  lighting_rules: string[];
  forbidden_elements: string[];
  [key: string]: unknown;
}

export const listWorlds = (projectId?: string): Promise<{ worlds: WorldBible[] }> =>
  request<{ worlds: WorldBible[] }>(`/world/worlds${projectId ? `?project_id=${projectId}` : ""}`);

export const createWorld = (body: Partial<WorldBible>): Promise<WorldBible> =>
  request<WorldBible>("/world/worlds", { method: "POST", body: JSON.stringify(body) });

export const listScenes = (projectId?: string): Promise<{ scenes: SceneBible[] }> =>
  request<{ scenes: SceneBible[] }>(`/world/scenes${projectId ? `?project_id=${projectId}` : ""}`);

export const createScene = (body: Partial<SceneBible>): Promise<SceneBible> =>
  request<SceneBible>("/world/scenes", { method: "POST", body: JSON.stringify(body) });

export const environmentSummary = (projectId: string): Promise<{ project_id: string; entries: number; by_kind: Record<string, number>; updated_at: string }> =>
  request(`/world/environment/${projectId}`);

// ------------------------------------------------------------- Shot DNA
export interface ShotDNA {
  id: string;
  category: string;
  scene: string;
  camera: Record<string, unknown>;
  lens: string;
  lighting: string;
  composition: string;
  emotion: string;
  style: string;
  tags: string[];
  prompt_template: string;
  success_rate: number;
  usage_count: number;
}

export interface RetrievalResult {
  query: Record<string, unknown>;
  hits: Array<ShotDNA & { score: number; matched: string[] }>;
  is_hit: boolean;
}

export const listShotDna = (category?: string): Promise<{ items: ShotDNA[] }> =>
  request<{ items: ShotDNA[] }>(`/shot-dna${category ? `?category=${category}` : ""}`);

export const shotDnaStats = (): Promise<{ total: number; by_category: Record<string, number>; avg_success_rate: number; total_usage: number }> =>
  request("/shot-dna/stats");

export const retrieveShotDna = (body: { category?: string; scene?: string; emotion?: string; camera_movement?: string; lighting?: string; top_k?: number }): Promise<RetrievalResult> =>
  request<RetrievalResult>("/shot-dna/retrieve", { method: "POST", body: JSON.stringify(body) });

export const addShotDna = (body: Partial<ShotDNA>): Promise<ShotDNA> =>
  request<ShotDNA>("/shot-dna", { method: "POST", body: JSON.stringify(body) });

// ------------------------------------------------------------- Readiness gate
export interface ReadinessReport {
  project_id: string;
  ready: boolean;
  missing: string[];
  gates: Record<string, { pass: boolean; [key: string]: unknown }>;
}

export const projectReadiness = (projectId: string): Promise<ReadinessReport> =>
  request<ReadinessReport>(`/episodes/readiness/${projectId}`);

// ------------------------------------------------------------- Production Readiness Matrix (13.4-B)
export interface MatrixGate {
  status: "READY" | "BLOCKED" | "WARNING";
  required: boolean;
  checks: number;
  missing: string[];
  recommended_actions: string[];
  evidence: string[];
  checked_at: string;
}

export interface ReadinessMatrix {
  project_id: string;
  status: "READY" | "BLOCKED" | "WARNING";
  gates: Record<string, MatrixGate>;
}

export const productionReadinessMatrix = (projectId: string): Promise<ReadinessMatrix> =>
  request<ReadinessMatrix>(`/readiness-matrix/${projectId}`);

// ------------------------------------------------------------- Story Intelligence
export const executiveProducerPlan = (body: { novel_text: string; project_id: string; platform?: string; budget?: number; target_episodes?: number; target_duration?: number; write_episodes?: boolean }): Promise<{ plan: Record<string, unknown>; pipeline_estimate: Record<string, unknown> }> =>
  request("/intelligence/executive-producer", { method: "POST", body: JSON.stringify(body) });

export const episodePlannerRun = (projectId: string): Promise<{ project_id: string; total: number; planned: number; hook_coverage: number }> =>
  request("/intelligence/episode-planner", { method: "POST", body: JSON.stringify({ project_id: projectId }) });

export const retentionScore = (body: { hook?: string; conflict?: string; climax?: string; ending?: string; retention_strategy?: string }): Promise<{ hook_score: number; emotion_curve: number; cliffhanger_score: number; share_probability: number; formula_check: Record<string, boolean> }> =>
  request("/intelligence/retention/score", { method: "POST", body: JSON.stringify(body) });
