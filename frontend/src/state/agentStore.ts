/**
 * Agent Store (Zustand)
 * Manages director/writer/character/critic agent outputs
 */

import { create } from 'zustand';
import { userMessage } from '@/api/client';
import type { ShotBrief, CriticReview, CharacterContext, WriterEnhanceResponse } from '../api/agent';
import * as api from '../api/agent';

interface AgentState {
  // Director output
  plannedShots: ShotBrief[];

  // Critic reviews
  reviews: Record<string, CriticReview>;

  // Character contexts
  characterContexts: Record<string, CharacterContext>;

  // Writer enhancements
  enhancements: Record<string, WriterEnhanceResponse>;

  // Status
  reviewing: boolean;
  error: string | null;

  // Actions
  planSequence: (shots: Parameters<typeof api.planSequence>[0]['shots']) => Promise<void>;
  reviewShot: (shotBrief: ShotBrief) => Promise<CriticReview>;
  reviewAll: (shotBriefs: ShotBrief[]) => Promise<void>;
  getCharacterContext: (characterId: string, shotId: string, emotion?: string) => Promise<CharacterContext>;
  clearAll: () => void;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  plannedShots: [],
  reviews: {},
  characterContexts: {},
  enhancements: {},
  reviewing: false,
  error: null,

  planSequence: async (shots) => {
    set({ error: null });
    try {
      const result = await api.planSequence({ shots });
      set({ plannedShots: result });
    } catch (e: unknown) {
      set({ error: userMessage(e) });
    }
  },

  reviewShot: async (shotBrief) => {
    const review = await api.reviewShot(shotBrief);
    set((s) => ({ reviews: { ...s.reviews, [shotBrief.shot_id]: review } }));
    return review;
  },

  reviewAll: async (shotBriefs) => {
    set({ reviewing: true, error: null });
    try {
      const reviews = await api.reviewSequence(shotBriefs);
      const reviewMap: Record<string, CriticReview> = {};
      for (const r of reviews) {
        reviewMap[r.shot_id] = r;
      }
      set({ reviews: { ...get().reviews, ...reviewMap }, reviewing: false });
    } catch (e: unknown) {
      set({ error: userMessage(e), reviewing: false });
    }
  },

  getCharacterContext: async (characterId, shotId, emotion) => {
    const ctx = await api.getCharacterContext(characterId, shotId, emotion);
    set((s) => ({
      characterContexts: { ...s.characterContexts, [`${characterId}_${shotId}`]: ctx },
    }));
    return ctx;
  },

  clearAll: () =>
    set({
      plannedShots: [],
      reviews: {},
      characterContexts: {},
      enhancements: {},
      error: null,
    }),
}));
