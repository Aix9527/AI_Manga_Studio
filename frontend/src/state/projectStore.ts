/**
 * Project Store (Zustand)
 * Manages project workspace state
 */

import { create } from 'zustand';

export interface ProjectInfo {
  id: string;
  title: string;
  novel_text: string;
  novel_id?: string;
  created_at?: string;
  updated_at?: string;
}

interface ProjectState {
  // Current project
  project: ProjectInfo | null;

  // Nav state
  activeTab: 'novel' | 'characters' | 'story-graph' | 'storyboard' | 'pipeline';

  // Actions
  setProject: (project: ProjectInfo) => void;
  setNovelText: (text: string) => void;
  setTab: (tab: ProjectState['activeTab']) => void;
  clearProject: () => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  project: null,
  activeTab: 'novel',

  setProject: (project) => set({ project, activeTab: 'novel' }),
  setNovelText: (text) =>
    set((s) => ({
      project: s.project ? { ...s.project, novel_text: text } : null,
    })),
  setTab: (activeTab) => set({ activeTab }),
  clearProject: () =>
    set({
      project: null,
      activeTab: 'novel',
    }),
}));
