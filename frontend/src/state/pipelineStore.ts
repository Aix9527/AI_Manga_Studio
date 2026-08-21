/**
 * Pipeline Store (Zustand)
 * Manages pipeline execution state and compiled prompts
 */

import { create } from 'zustand';
import { userMessage } from '@/api/client';
import type { PipelineResponse, CompiledPrompt, PipelineRequest } from '../api/pipeline';
import * as api from '../api/pipeline';

interface PipelineState {
  // Results
  lastRun: PipelineResponse | null;
  compiledPrompts: CompiledPrompt[];

  // Status
  running: boolean;
  error: string | null;

  // Actions
  runPipeline: (req: PipelineRequest) => Promise<void>;
  compileSingleShot: (shotData: Parameters<typeof api.compileSingleShot>[0]) => Promise<CompiledPrompt>;
  clearAll: () => void;
}

export const usePipelineStore = create<PipelineState>((set) => ({
  lastRun: null,
  compiledPrompts: [],
  running: false,
  error: null,

  runPipeline: async (req) => {
    set({ running: true, error: null });
    try {
      const result = await api.runPipeline(req);
      set({ lastRun: result, running: false });
    } catch (e: unknown) {
      set({ error: userMessage(e), running: false });
    }
  },

  compileSingleShot: async (shotData) => {
    try {
      const prompt = await api.compileSingleShot(shotData);
      set((s) => ({ compiledPrompts: [...s.compiledPrompts, prompt], error: null }));
      return prompt;
    } catch (error) {
      set({ error: userMessage(error) });
      throw error;
    }
  },

  clearAll: () =>
    set({
      lastRun: null,
      compiledPrompts: [],
      error: null,
    }),
}));
