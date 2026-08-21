/**
 * Character Store (Zustand)
 * Manages character list, selection, extraction state
 */

import { create } from 'zustand';
import { ApiError, userMessage } from '@/api/client';
import type { CharacterData, ExtractRequest, Relationship } from '../api/character';
import * as api from '../api/character';

interface CharacterState {
  // Data
  characters: CharacterData[];
  selectedId: string | null;
  relationships: Record<string, Relationship[]>;

  // Status
  loading: boolean;
  extracting: boolean;
  error: string | null;
  relationshipError: string | null;

  // Actions
  loadCharacters: (novelId?: string) => Promise<void>;
  selectCharacter: (id: string | null) => void;
  extractFromText: (req: ExtractRequest) => Promise<void>;
  createCharacter: (data: CharacterData) => Promise<CharacterData>;
  deleteCharacter: (id: string) => Promise<void>;
  loadRelationships: (characterId: string) => Promise<void>;
  invalidateRequests: () => void;
  clearAll: () => void;
}

let characterRequestSequence = 0;
let relationshipRequestSequence = 0;

export const useCharacterStore = create<CharacterState>((set, get) => ({
  characters: [],
  selectedId: null,
  relationships: {},
  loading: false,
  extracting: false,
  error: null,
  relationshipError: null,

  loadCharacters: async (novelId) => {
    const requestToken = ++characterRequestSequence;
    set({ characters: [], selectedId: null, loading: true, error: null });
    try {
      const characters = await api.listCharacters(novelId);
      if (requestToken !== characterRequestSequence) return;
      set({ characters, loading: false });
    } catch (e: unknown) {
      if (requestToken !== characterRequestSequence) return;
      set({
        characters: [],
        error: e instanceof ApiError && e.status === 404 ? null : userMessage(e),
        loading: false,
      });
    }
  },

  selectCharacter: (id) => set({ selectedId: id }),

  extractFromText: async (req) => {
    set({ extracting: true, error: null });
    try {
      const chars = await api.extractCharacters(req);
      set((s) => ({
        characters: [...s.characters, ...chars],
        extracting: false,
      }));
    } catch (e: unknown) {
      set({ error: userMessage(e), extracting: false });
    }
  },

  createCharacter: async (data) => {
    const character = await api.createCharacter(data);
    set((s) => ({ characters: [...s.characters, character] }));
    return character;
  },

  deleteCharacter: async (id) => {
    await api.deleteCharacter(id);
    set((s) => ({
      characters: s.characters.filter((c) => c.id !== id),
      selectedId: s.selectedId === id ? null : s.selectedId,
    }));
  },

  loadRelationships: async (characterId) => {
    const requestToken = ++relationshipRequestSequence;
    set({ relationships: {}, relationshipError: null });
    try {
      const rels = await api.listRelationships(characterId);
      if (requestToken !== relationshipRequestSequence) return;
      set((s) => ({
        relationships: { ...s.relationships, [characterId]: rels },
      }));
    } catch (error) {
      if (requestToken !== relationshipRequestSequence) return;
      set({ relationshipError: userMessage(error) });
    }
  },

  invalidateRequests: () => {
    characterRequestSequence += 1;
    relationshipRequestSequence += 1;
  },

  clearAll: () =>
    set({
      characters: [],
      selectedId: null,
      relationships: {},
      error: null,
      relationshipError: null,
    }),
}));

/* Selector helpers */
export function selectedCharacterSelector(state: CharacterState) {
  return state.characters.find((c) => c.id === state.selectedId) ?? null;
}
