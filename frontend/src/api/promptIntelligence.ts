/**
 * Prompt Intelligence API (Phase 13.4-A, GPT spec).
 * Versioned prompt templates + diff + review + approval + A/B test + compose.
 */

import { request } from "@/api/client";

export interface PromptVersionRecord {
  template_id: string;
  version_id: string;
  parent_version: string;
  base_template: string;
  negative_prompt: string;
  quality_tags: string;
  variables: string[];
  notes: string;
  status: "draft" | "approved" | "locked";
  approved_by: string;
  approved_at: string;
  content_hash: string;
  created_at: string;
}

export interface PromptTemplateRecord {
  id: string;
  name: string;
  kind: "character" | "world" | "shot" | "generic";
  description: string;
  active_version: string;
  created_at: string;
  updated_at: string;
  versions: PromptVersionRecord[];
}

export interface PromptReviewRecord {
  id: string;
  template_id: string;
  version_id: string;
  reviewer: string;
  status: "pending" | "approved" | "rejected";
  comments: string;
  created_at: string;
  resolved_at: string;
}

export interface PromptABTestRecord {
  id: string;
  name: string;
  template_id: string;
  base_version: string;
  variant_version: string;
  status: "draft" | "running" | "completed";
  metric: string;
  results: Record<string, { samples: number; wins: number; score: number }>;
  winner: string;
  created_at: string;
  decided_at: string;
}

export interface ComposeResult {
  kind: string;
  template: string;
  version_id: string;
  positive_prompt: string;
  negative_prompt: string;
  source_id: string;
}

export const promptStats = (): Promise<{ templates: number; versions: number; by_kind: Record<string, number>; approved_versions: number; locked_versions: number; reviews: number; ab_tests: number }> =>
  request("/prompt-intelligence/stats");

export const listPromptTemplates = (kind?: string): Promise<{ templates: PromptTemplateRecord[] }> =>
  request(`/prompt-intelligence/templates${kind ? `?kind=${kind}` : ""}`);

export const createPromptTemplate = (body: { name: string; kind: string; base_template: string; negative_prompt?: string; quality_tags?: string; variables?: string[]; description?: string }): Promise<PromptTemplateRecord> =>
  request("/prompt-intelligence/templates", { method: "POST", body: JSON.stringify(body) });

export const getPromptTemplate = (templateId: string): Promise<PromptTemplateRecord> =>
  request(`/prompt-intelligence/templates/${templateId}`);

export const createPromptVersion = (templateId: string, body: { base_template: string; negative_prompt?: string; quality_tags?: string; variables?: string[]; notes?: string; parent_version?: string }): Promise<PromptTemplateRecord> =>
  request(`/prompt-intelligence/templates/${templateId}/versions`, { method: "POST", body: JSON.stringify(body) });

export const setPromptVersionStatus = (templateId: string, versionId: string, body: { status: "approved" | "locked"; approved_by?: string }): Promise<PromptTemplateRecord> =>
  request(`/prompt-intelligence/templates/${templateId}/versions/${versionId}/status`, { method: "POST", body: JSON.stringify(body) });

export const diffPromptVersions = (templateId: string, versionId: string, against: string): Promise<{ template_id: string; from_version: string; to_version: string; diff: string[]; changed: boolean }> =>
  request(`/prompt-intelligence/templates/${templateId}/versions/${versionId}/diff?against=${against}`);

export const addPromptReview = (templateId: string, versionId: string, body: { reviewer: string; status: "pending" | "approved" | "rejected"; comments?: string }): Promise<PromptReviewRecord> =>
  request(`/prompt-intelligence/templates/${templateId}/versions/${versionId}/review`, { method: "POST", body: JSON.stringify(body) });

export const listPromptReviews = (templateId?: string): Promise<{ reviews: PromptReviewRecord[] }> =>
  request(`/prompt-intelligence/reviews${templateId ? `?template_id=${templateId}` : ""}`);

export const listABTests = (): Promise<{ tests: PromptABTestRecord[] }> =>
  request("/prompt-intelligence/ab-tests");

export const createABTest = (body: { template_id: string; base_version: string; variant_version: string; name?: string; metric?: string }): Promise<PromptABTestRecord> =>
  request("/prompt-intelligence/ab-tests", { method: "POST", body: JSON.stringify(body) });

export const recordABResult = (abId: string, body: { arm: "base" | "variant"; success: boolean }): Promise<PromptABTestRecord> =>
  request(`/prompt-intelligence/ab-tests/${abId}/results`, { method: "POST", body: JSON.stringify(body) });

export const decideAB = (abId: string, minSamples = 3): Promise<PromptABTestRecord> =>
  request(`/prompt-intelligence/ab-tests/${abId}/decide`, { method: "POST", body: JSON.stringify({ min_samples: minSamples }) });

export const composeCharacter = (body: { character_id: string; asset_type?: string; asset_key?: string }): Promise<ComposeResult> =>
  request("/prompt-intelligence/compose/character", { method: "POST", body: JSON.stringify(body) });

export const composeWorld = (body: { project_id?: string; world_id?: string; scene_id?: string }): Promise<ComposeResult> =>
  request("/prompt-intelligence/compose/world", { method: "POST", body: JSON.stringify(body) });

export const composeShot = (body: { dna_id?: string; features?: Record<string, string>; top_k?: number }): Promise<ComposeResult> =>
  request("/prompt-intelligence/compose/shot", { method: "POST", body: JSON.stringify(body) });