/**
 * Asset Feedback Loop API (Phase 13.4-C, GPT spec).
 * Events (Critic/IdentityGate/QC) -> Candidates -> Human Review -> New Version.
 */

import { request } from "@/api/client";

export interface FeedbackEvent {
  id: string;
  kind: "critic" | "identity_gate" | "qc";
  source: string;
  target_type: string;
  target_id: string;
  project_id: string;
  severity: "low" | "medium" | "high";
  issues: string[];
  metrics: Record<string, unknown>;
  created_at: string;
}

export interface FeedbackCandidate {
  id: string;
  target_type: string;
  target_id: string;
  project_id: string;
  suggested_changes: Record<string, unknown>;
  evidence: Record<string, unknown>;
  reason: string;
  status: "proposed" | "approved" | "rejected" | "applied";
  reviewer: string;
  created_at: string;
  decided_at: string;
  applied_at: string;
}

export interface FeedbackStats {
  events: number;
  by_kind: Record<string, number>;
  by_target_type: Record<string, number>;
  candidates: number;
  by_status: Record<string, number>;
}

export const feedbackStats = (): Promise<FeedbackStats> => request("/feedback/stats");

export const listFeedbackEvents = (targetType?: string): Promise<{ events: FeedbackEvent[] }> =>
  request(`/feedback/events${targetType ? `?target_type=${targetType}` : ""}`);

export const recordFeedbackEvent = (body: { kind: string; target_type: string; target_id: string; source?: string; project_id?: string; severity?: string; issues?: string[]; metrics?: Record<string, unknown> }): Promise<FeedbackEvent> =>
  request("/feedback/events", { method: "POST", body: JSON.stringify(body) });

export const recordShotOutcome = (dnaId: string, body: { success?: boolean; quality?: number; human_score?: number; source?: string }): Promise<Record<string, unknown>> =>
  request(`/feedback/shots/${dnaId}/outcomes`, { method: "POST", body: JSON.stringify(body) });

export const listFeedbackCandidates = (status?: string): Promise<{ candidates: FeedbackCandidate[] }> =>
  request(`/feedback/candidates${status ? `?status=${status}` : ""}`);

export const autoProposeCandidates = (minSamples = 10): Promise<{ candidates: FeedbackCandidate[] }> =>
  request(`/feedback/candidates/auto?min_samples=${minSamples}`, { method: "POST", body: JSON.stringify({}) });

export const reviewCandidate = (candidateId: string, decision: "approve" | "reject", reviewer = "导演"): Promise<FeedbackCandidate> =>
  request(`/feedback/candidates/${candidateId}/review`, { method: "POST", body: JSON.stringify({ decision, reviewer }) });

export const applyCandidate = (candidateId: string): Promise<FeedbackCandidate> =>
  request(`/feedback/candidates/${candidateId}/apply`, { method: "POST", body: JSON.stringify({}) });