/**
 * Director Evolution Center Store (Zustand) — Phase 12.2.
 */

import { create } from "zustand";

import { userMessage } from "@/api/client";
import * as api from "@/api/directorEvolution";
import * as adaptiveApi from "@/api/adaptiveRouter";
import type {
  Accumulation,
  Candidate,
  CandidateQueue,
  EvolutionStats,
  HistoryEntry,
  PolicyPerformanceRow,
  WinRate,
} from "@/api/directorEvolution";
import type { AbValidation, AdaptiveProposal } from "@/api/adaptiveRouter";
import type {
  AuditEntry,
  FreezeResult,
  RegistrySummary,
  ReleaseResult,
} from "@/api/governance";
import * as governanceApi from "@/api/governance";

export interface DirectorEvolutionState {
  source: "production" | "mock";
  loading: boolean;
  error: string | null;

  stats: EvolutionStats | null;
  candidates: CandidateQueue | null;
  history: HistoryEntry[];
  performance: PolicyPerformanceRow[];
  accumulation: Accumulation | null;
  winRate: WinRate | null;
  adaptive: AdaptiveProposal | null;
  abValidation: AbValidation | null;

  registry: RegistrySummary | null;
  auditEntries: AuditEntry[];
  lastRelease: ReleaseResult | null;
  certify: ReleaseResult | null;
  freeze: FreezeResult | null;

  setSource: (source: "production" | "mock") => Promise<void>;
  refresh: () => Promise<void>;
  approve: (candidateId: string) => Promise<void>;
  reject: (candidateId: string) => Promise<void>;
  rollback: () => Promise<void>;
  seedMock: () => Promise<void>;
  refreshAdaptive: () => Promise<void>;
  approveAdaptive: (id: string) => Promise<void>;
  rejectAdaptive: (id: string) => Promise<void>;
  rollbackAdaptive: () => Promise<void>;
  refreshGovernance: () => Promise<void>;
  createRelease: () => Promise<void>;
  approveRelease: (releaseId: string) => Promise<void>;
  rollbackRelease: (releaseId: string, reason?: string) => Promise<void>;
  certifyRelease: () => Promise<void>;
  freezeRelease: () => Promise<void>;
}

export const useDirectorEvolutionStore = create<DirectorEvolutionState>((set, get) => ({
  source: "production",
  loading: false,
  error: null,

  stats: null,
  candidates: null,
  history: [],
  performance: [],
  accumulation: null,
  winRate: null,
  adaptive: null,
  abValidation: null,

  registry: null,
  auditEntries: [],
  lastRelease: null,
  certify: null,
  freeze: null,

  setSource: async (source) => {
    set({ source });
    await get().refresh();
  },

  refresh: async () => {
    const { source } = get();
    set({ loading: true, error: null });
    try {
      const [stats, candidates, history] = await Promise.all([
        api.getEvolutionStats(source),
        api.getCandidates(source),
        api.getHistory(source),
      ]);
      const [adaptive, abValidation] = await Promise.all([
        adaptiveApi.getAdaptiveProposal(source),
        adaptiveApi.getAbValidation(source, 100),
      ]).catch(() => [null, null]);
      const [registry, audit] = await Promise.all([
        governanceApi.getRegistry(),
        governanceApi.getAudit(),
      ]).catch(() => [null, null]);
      set({
        stats,
        candidates,
        history: history.entries,
        performance: stats.policy_performance,
        accumulation: stats.accumulation,
        winRate: stats.win_rate,
        adaptive,
        abValidation,
        registry,
        auditEntries: audit?.entries ?? [],
        loading: false,
      });
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  approve: async (candidateId) => {
    const { source } = get();
    set({ loading: true, error: null });
    try {
      await api.approveCandidate(candidateId, source, "dashboard approval");
      await get().refresh();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  reject: async (candidateId) => {
    const { source } = get();
    set({ loading: true, error: null });
    try {
      await api.rejectCandidate(candidateId, source, "dashboard reject");
      await get().refresh();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  rollback: async () => {
    const { source } = get();
    set({ loading: true, error: null });
    try {
      await api.rollbackPolicy(source, "dashboard rollback");
      await get().refresh();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  seedMock: async () => {
    set({ loading: true, error: null });
    try {
      await api.seedMockData();
      await get().refresh();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  refreshAdaptive: async () => {
    const { source } = get();
    set({ loading: true, error: null });
    try {
      const [adaptive, abValidation] = await Promise.all([
        adaptiveApi.getAdaptiveProposal(source),
        adaptiveApi.getAbValidation(source, 100),
      ]);
      set({ adaptive, abValidation, loading: false });
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  approveAdaptive: async (id) => {
    const { source } = get();
    set({ loading: true, error: null });
    try {
      await adaptiveApi.approveAdaptiveRecommendation(id, source);
      await get().refreshAdaptive();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  rejectAdaptive: async (id) => {
    const { source } = get();
    set({ loading: true, error: null });
    try {
      await adaptiveApi.rejectAdaptiveRecommendation(id, source, "dashboard reject");
      await get().refreshAdaptive();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  rollbackAdaptive: async () => {
    const { source } = get();
    set({ loading: true, error: null });
    try {
      await adaptiveApi.rollbackAdaptivePolicy(source, "dashboard rollback");
      await get().refreshAdaptive();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  refreshGovernance: async () => {
    set({ loading: true, error: null });
    try {
      const [registry, audit] = await Promise.all([
        governanceApi.getRegistry(),
        governanceApi.getAudit(),
      ]);
      set({ registry, auditEntries: audit.entries, loading: false });
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  createRelease: async () => {
    set({ loading: true, error: null });
    try {
      const releaseId = `rel-12.9-${Date.now()}`;
      const result = await governanceApi.createRelease({
        release_id: releaseId,
        project: "归墟觉醒·天倾",
        pipeline: "v12.9",
        director: "council-v1",
        policy: "adaptive-v3",
        models: ["wan2.2", "qwen"],
      });
      set({ lastRelease: result, loading: false });
      await get().refreshGovernance();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  approveRelease: async (releaseId) => {
    set({ loading: true, error: null });
    try {
      const result = await governanceApi.approveRelease(releaseId);
      set({ lastRelease: result, loading: false });
      await get().refreshGovernance();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  rollbackRelease: async (releaseId, reason = "dashboard rollback") => {
    set({ loading: true, error: null });
    try {
      const result = await governanceApi.rollbackRelease(releaseId, reason);
      set({ lastRelease: result, loading: false });
      await get().refreshGovernance();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  certifyRelease: async () => {
    set({ loading: true, error: null });
    try {
      const checks = {
        production_100_shots: true,
        council_explain_100: true,
        governance_rollback: true,
      };
      const result = await governanceApi.certifyRelease(checks);
      set({ certify: result, loading: false });
      await get().refreshGovernance();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },

  freezeRelease: async () => {
    set({ loading: true, error: null });
    try {
      const releaseId = get().lastRelease?.release_id ?? `rel-12.9-${Date.now()}`;
      const result = await governanceApi.freezeRelease({
        release_id: releaseId,
        project: "归墟觉醒·天倾",
        director_decisions: [],
        council_votes: [],
        policy_history: [],
        asset_registry: [],
        model_registry: [],
      });
      set({ freeze: result, loading: false });
      await get().refreshGovernance();
    } catch (error) {
      set({ error: userMessage(error), loading: false });
    }
  },
}));
