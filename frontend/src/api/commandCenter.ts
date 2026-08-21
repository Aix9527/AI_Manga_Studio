/**
 * Command Center API (Phase 14.3, GPT spec).
 * KG + Digital Twin + Production Intelligence 融合层。
 */

import { request } from "@/api/client";

export interface CommandCenterOverview {
  mode: string;
  governance: { auto_control: boolean; auto_apply: boolean; auto_deploy: boolean; human_approval: boolean };
  production_state: {
    task_total: number; active_tasks: number; worker_count: number; queue_depth: number;
    waiting_human: number; assignment_active: number; gpu_usage: number; worker_idle_rate: number;
  };
  prediction: Array<{ scenario: string; label: string; eta_hours: number; cost: number; bottleneck: string }>;
  timeline_summary: { blocked_total: number; rework_total: number; waiting_human_total: number; parallel_episodes: number };
  knowledge_graph: { nodes: number; edges: number };
  intelligence: { pi_candidates: Array<Record<string, unknown>> };
  risks: Array<Record<string, unknown>>;
  approvals_pending: { waiting_human: number; pi_candidates: number; risk_candidates: number };
  audit_coverage: number;
  note: string;
}

export const ccOverview = (): Promise<CommandCenterOverview> => request("/command-center/overview");
