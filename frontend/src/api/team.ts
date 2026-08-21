/**
 * Team Collaboration API (Phase 13.5-C, GPT spec).
 * 9 角色制作团队 + 状态机 + 定向返工 + 人工审批门。
 */

import { request } from "@/api/client";

export interface TeamInfo {
  id: string;
  project_id: string;
  season_id: string;
  name: string;
  members: string[];
  role_bindings: Record<string, string[]>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TeamAssignment {
  id: string;
  project_id: string;
  season_id: string;
  episode_id: string;
  stage: string;
  role: string;
  assignee_type: string;
  assignee_id: string;
  status: string;
  input_artifacts: Array<Record<string, unknown>>;
  output_artifacts: Array<Record<string, unknown>>;
  dependencies: string[];
  task_id: string;
  checkpoint_id: string;
  attempt: number;
  max_attempts: number;
  rework_count: number;
  blocked_reason: string;
  deadline: string;
  created_at: string;
  started_at: string;
  completed_at: string;
}

export interface ReviewRecord {
  id: string;
  assignment_id: string;
  reviewer_role: string;
  reviewer_id: string;
  verdict: string;
  rule_results: Record<string, unknown>;
  evidence: Record<string, unknown>;
  comments: string;
  next_stage: string;
  created_at: string;
}

export interface TeamAuditRow {
  id: string;
  project_id: string;
  episode_id: string;
  assignment_id: string;
  event: string;
  actor: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  reason: string;
  evidence: Record<string, unknown>;
  timestamp: string;
}

export interface TeamStats {
  teams: number;
  assignments: number;
  reviews: number;
  audit_records: number;
  audit_coverage: number;
  by_status: Record<string, number>;
  new_queue_count: number;
  illegal_transitions: number;
  infinite_rework: number;
  governance: {
    human_approval: boolean;
    rollback: boolean;
    audit: boolean;
    auto_learning: boolean;
    auto_apply: boolean;
    auto_deploy: boolean;
    auto_budget_change: boolean;
  };
}

export interface FlowEpisode {
  episode_id: string;
  stages: Record<string, {
    stage: string;
    status: string;
    role: string;
    assignment_id: string;
    assignee_id: string;
    attempt: number;
    rework_count: number;
    started_at: string;
    completed_at: string;
  }>;
  assignments: number;
  rework_count: number;
  waiting_human: number;
}

export interface FlowView {
  project_id: string;
  episodes: FlowEpisode[];
}

export const createTeam = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/team", { method: "POST", body: JSON.stringify(body) });

export const teamStats = (): Promise<TeamStats> =>
  request("/team/stats");

export const getTeam = (projectId: string): Promise<{ team: TeamInfo; active_assignments: TeamAssignment[] }> =>
  request(`/team/${encodeURIComponent(projectId)}`);

export const assignTask = (projectId: string, episodeId: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/${encodeURIComponent(projectId)}/episodes/${encodeURIComponent(episodeId)}/assign`, { method: "POST", body: JSON.stringify(body) });

export const listAssignments = (params: Record<string, string> = {}): Promise<{ assignments: TeamAssignment[] }> => {
  const query = new URLSearchParams(params).toString();
  return request(`/team/assignments${query ? `?${query}` : ""}`);
};

export const getAssignment = (id: string): Promise<{ assignment: TeamAssignment; reviews: ReviewRecord[]; audit: TeamAuditRow[] }> =>
  request(`/team/assignments/${encodeURIComponent(id)}`);

export const startAssignment = (id: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/assignments/${encodeURIComponent(id)}/start`, { method: "POST", body: JSON.stringify(body) });

export const reviewAssignment = (id: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/assignments/${encodeURIComponent(id)}/review`, { method: "POST", body: JSON.stringify(body) });

export const reworkAssignment = (id: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/assignments/${encodeURIComponent(id)}/rework`, { method: "POST", body: JSON.stringify(body) });

export const escalateAssignment = (id: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/assignments/${encodeURIComponent(id)}/escalate`, { method: "POST", body: JSON.stringify(body) });

export const blockAssignment = (id: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/assignments/${encodeURIComponent(id)}/block`, { method: "POST", body: JSON.stringify(body) });

export const unblockAssignment = (id: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/assignments/${encodeURIComponent(id)}/unblock`, { method: "POST", body: JSON.stringify(body) });

export const failAssignment = (id: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/assignments/${encodeURIComponent(id)}/fail`, { method: "POST", body: JSON.stringify(body) });

export const completeAssignment = (id: string, body: Record<string, unknown>): Promise<TeamAssignment> =>
  request(`/team/assignments/${encodeURIComponent(id)}/complete`, { method: "POST", body: JSON.stringify(body) });

export const teamFlow = (projectId: string): Promise<FlowView> =>
  request(`/team/${encodeURIComponent(projectId)}/flow`);

export const teamArtifacts = (projectId: string, episodeId: string): Promise<Record<string, unknown>> =>
  request(`/team/${encodeURIComponent(projectId)}/episodes/${encodeURIComponent(episodeId)}/artifacts`);

export const teamAudit = (projectId: string): Promise<{ audit: TeamAuditRow[] }> =>
  request(`/team/${encodeURIComponent(projectId)}/audit`);
