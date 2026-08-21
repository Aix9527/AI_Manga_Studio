/**
 * Story Store (Zustand)
 * Manages story graph, scene structure, timeline
 */

import { create } from 'zustand';
import { ApiError, userMessage } from '@/api/client';
import type { StoryGraph, SceneData, ShotData, ShotUpdate, TimelineEvent } from '../api/story';
import * as api from '../api/story';

interface StoryState {
  // Data
  graph: StoryGraph | null;
  scenes: SceneData[];
  shots: ShotData[];
  storyboardNovelId: string | null;
  timeline: TimelineEvent[];

  // Status
  loading: boolean;
  error: string | null;
  parsing: boolean;
  parseError: string | null;
  timelineError: string | null;

  // UI state
  selectedChapterIndex: number | null;
  selectedSceneId: string | null;
  selectedShotId: string | null;
  selectedShotIds: string[];

  // Actions
  parseStory: (text: string, novelId: string, displayTitle?: string) => Promise<void>;
  loadGraph: (novelId: string) => Promise<void>;
  loadStoryboard: (novelId: string) => Promise<void>;
  updateShot: (novelId: string, shotId: string, patch: ShotUpdate) => Promise<ShotData>;
  selectChapter: (index: number | null) => void;
  selectScene: (id: string | null) => void;
  selectShot: (id: string | null) => void;
  toggleShotSelection: (id: string) => void;
  clearShotSelection: () => void;
  loadTimeline: (novelId: string, characterId?: string) => Promise<void>;
  invalidateRequests: () => void;
  clearAll: () => void;
}

let graphRequestSequence = 0;
let timelineRequestSequence = 0;
let parseRequestSequence = 0;
let activeParseProject = '';
let storyboardRequestSequence = 0;
let storyboardGeneration = 0;
const storyboardInflight = new Map<string, Promise<SceneData[]>>();

interface ShotUpdateJob {
  patch: ShotUpdate;
  generation: number;
  resolve: (shot: ShotData) => void;
  reject: (error: unknown) => void;
}

interface ShotUpdateQueue {
  running: boolean;
  jobs: ShotUpdateJob[];
}

const shotUpdateQueues = new Map<string, ShotUpdateQueue>();

function flattenShots(scenes: SceneData[]): ShotData[] {
  return scenes.flatMap((scene) => scene.shots ?? []);
}

export const useStoryStore = create<StoryState>((set) => ({
  graph: null,
  scenes: [],
  shots: [],
  storyboardNovelId: null,
  timeline: [],
  loading: false,
  error: null,
  parsing: false,
  parseError: null,
  timelineError: null,
  selectedChapterIndex: null,
  selectedSceneId: null,
  selectedShotId: null,
  selectedShotIds: [],

  parseStory: async (text, novelId) => {
    const requestToken = ++parseRequestSequence;
    activeParseProject = novelId;
    set({ parsing: true, parseError: null });
    try {
      const parsed = await api.parseStory({ text, novel_id: novelId });
      if (requestToken !== parseRequestSequence || activeParseProject !== novelId) return;
      const scenes = parsed.scene_data;
      const allShots: ShotData[] = [];
      for (const scene of scenes) {
        if (scene.shots) allShots.push(...scene.shots);
      }
      set({ scenes, shots: allShots, parsing: false, parseError: null });
    } catch (e: unknown) {
      if (requestToken !== parseRequestSequence || activeParseProject !== novelId) return;
      set({ parseError: userMessage(e), parsing: false });
    }
  },

  loadGraph: async (novelId) => {
    const requestToken = ++graphRequestSequence;
    set({ graph: null, loading: true, error: null });
    try {
      const graph = await api.getStoryGraph(novelId);
      if (requestToken !== graphRequestSequence) return;
      set({ graph, loading: false });
    } catch (e: unknown) {
      if (requestToken !== graphRequestSequence) return;
      set({
        graph: null,
        error: e instanceof ApiError && e.status === 404 ? null : userMessage(e),
        loading: false,
      });
    }
  },

  loadStoryboard: async (novelId) => {
    const current = useStoryStore.getState();
    if (current.storyboardNovelId === novelId && !current.loading) return;

    const requestToken = ++storyboardRequestSequence;
    const generation = storyboardGeneration;
    set({
      scenes: [],
      shots: [],
      storyboardNovelId: null,
      selectedSceneId: null,
      selectedShotId: null,
      selectedShotIds: [],
      loading: true,
      error: null,
    });

    let pending = storyboardInflight.get(novelId);
    if (!pending) {
      pending = api.getStoryboardScenes(novelId);
      storyboardInflight.set(novelId, pending);
      void pending.then(
        () => { if (storyboardInflight.get(novelId) === pending) storyboardInflight.delete(novelId); },
        () => { if (storyboardInflight.get(novelId) === pending) storyboardInflight.delete(novelId); },
      );
    }

    try {
      const scenes = await pending;
      if (requestToken !== storyboardRequestSequence || generation !== storyboardGeneration) return;
      const shots = flattenShots(scenes);
      const selectedShotId = useStoryStore.getState().selectedShotId;
      set({
        scenes,
        shots,
        storyboardNovelId: novelId,
        loading: false,
        error: null,
        selectedShotId: selectedShotId && shots.some((shot) => shot.id === selectedShotId)
          ? selectedShotId
          : null,
      });
    } catch (error) {
      if (requestToken !== storyboardRequestSequence || generation !== storyboardGeneration) return;
      if (error instanceof ApiError && error.status === 404) {
        set({ scenes: [], shots: [], storyboardNovelId: novelId, loading: false, error: null });
      } else {
        set({ loading: false, error: userMessage(error) });
      }
    }
  },

  updateShot: (novelId, shotId, patch) => new Promise<ShotData>((resolve, reject) => {
    const key = `${novelId}\u0000${shotId}`;
    let queue = shotUpdateQueues.get(key);
    if (!queue) {
      queue = { running: false, jobs: [] };
      shotUpdateQueues.set(key, queue);
    }
    const ownedQueue = queue;
    ownedQueue.jobs.push({ patch, generation: storyboardGeneration, resolve, reject });

    if (!ownedQueue.running) {
      ownedQueue.running = true;
      void (async () => {
        while (ownedQueue.jobs.length > 0) {
          const job = ownedQueue.jobs[0];
          try {
            const updated = await api.updateShot(novelId, shotId, job.patch);
            const current = useStoryStore.getState();
            if (job.generation === storyboardGeneration && current.storyboardNovelId === novelId) {
              const scenes = current.scenes.map((scene) => ({
                ...scene,
                shots: scene.shots.map((shot) => shot.id === shotId ? updated : shot),
              }));
              set({ scenes, shots: flattenShots(scenes), error: null });
            }
            job.resolve(updated);
          } catch (error) {
            const current = useStoryStore.getState();
            if (job.generation === storyboardGeneration && current.storyboardNovelId === novelId) {
              set({ error: userMessage(error) });
            }
            job.reject(error);
          } finally {
            ownedQueue.jobs.shift();
          }
        }
        ownedQueue.running = false;
        if (shotUpdateQueues.get(key) === ownedQueue) {
          shotUpdateQueues.delete(key);
        }
      })();
    }
  }),

  selectChapter: (index) => set({ selectedChapterIndex: index }),
  selectScene: (id) => set({ selectedSceneId: id }),
  selectShot: (id) => set({ selectedShotId: id }),
  toggleShotSelection: (id) => set((state) => ({
    selectedShotIds: state.selectedShotIds.includes(id)
      ? state.selectedShotIds.filter((candidate) => candidate !== id)
      : [...state.selectedShotIds, id],
  })),
  clearShotSelection: () => set({ selectedShotIds: [] }),

  loadTimeline: async (novelId, characterId) => {
    const requestToken = ++timelineRequestSequence;
    set({ timelineError: null });
    try {
      const timeline = characterId
        ? await api.getCharacterTimeline(novelId, characterId)
        : await api.getTimeline(novelId);
      if (requestToken !== timelineRequestSequence) return;
      set({ timeline, timelineError: null });
    } catch (error) {
      if (requestToken !== timelineRequestSequence) return;
      set({ timelineError: userMessage(error) });
    }
  },

  invalidateRequests: () => {
    graphRequestSequence += 1;
    timelineRequestSequence += 1;
    parseRequestSequence += 1;
    activeParseProject = '';
    storyboardRequestSequence += 1;
    storyboardGeneration += 1;
    set({ parsing: false });
  },

  clearAll: () => {
    graphRequestSequence += 1;
    timelineRequestSequence += 1;
    parseRequestSequence += 1;
    activeParseProject = '';
    storyboardRequestSequence += 1;
    storyboardGeneration += 1;
    set({
      graph: null,
      scenes: [],
      shots: [],
      storyboardNovelId: null,
      timeline: [],
      error: null,
      parsing: false,
      parseError: null,
      timelineError: null,
      selectedChapterIndex: null,
      selectedSceneId: null,
      selectedShotId: null,
      selectedShotIds: [],
    });
  },
}));
