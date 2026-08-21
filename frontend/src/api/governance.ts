/**
 * Production Governance API — Phase 12.9-A (GPT spec).
 */

import { request } from "@/api/client";

const BASE = "/governance";

export interface RegistrySummary {
  components: Record<string, { name: string; version: string; updated_at: string }>;
  releases: number;
}

export interface AuditEntry {
  id: string;
  action: string;
  created_at: string;
  detail: Record<string, unknown>;
}

export interface ReleaseResult {
  release_id: string;
  manifest?: Record<string, unknown>;
  approved?: boolean;
  rolled_back?: boolean;
  passed?: boolean;
  checks?: Record<string, boolean>;
  audit: AuditEntry;
}

export interface FreezeResult {
  manifest: Record<string, unknown>;
  root: string;
}

export const getRegistry = (): Promise<RegistrySummary> =>
  request<RegistrySummary>(`${BASE}/registry`);

export const getAudit = (action?: string): Promise<{ entries: AuditEntry[] }> =>
  request<{ entries: AuditEntry[] }>(`${BASE}/audit${action ? `?action=${action}` : ""}`);

export const createRelease = (body: {
  release_id: string;
  project?: string;
  pipeline?: string;
  director?: string;
  policy?: string;
  models?: string[];
  meta?: Record<string, unknown>;
}): Promise<ReleaseResult> =>
  request<ReleaseResult>(`${BASE}/release`, { method: "POST", body: JSON.stringify(body) });

export const approveRelease = (releaseId: string): Promise<ReleaseResult> =>
  request<ReleaseResult>(`${BASE}/release/approve`, {
    method: "POST",
    body: JSON.stringify({ release_id: releaseId, approved_by: "dashboard" }),
  });

export const rollbackRelease = (releaseId: string, reason = ""): Promise<ReleaseResult> =>
  request<ReleaseResult>(`${BASE}/release/rollback`, {
    method: "POST",
    body: JSON.stringify({ release_id: releaseId, reason }),
  });

export const certifyRelease = (checks: Record<string, boolean>): Promise<ReleaseResult> =>
  request<ReleaseResult>(`${BASE}/certify`, { method: "POST", body: JSON.stringify({ checks }) });

export const freezeRelease = (body: {
  release_id: string;
  project?: string;
  director_decisions?: unknown[];
  council_votes?: unknown[];
  policy_history?: unknown[];
  asset_registry?: unknown[];
  model_registry?: unknown[];
}): Promise<FreezeResult> =>
  request<FreezeResult>(`${BASE}/freeze`, { method: "POST", body: JSON.stringify(body) });
