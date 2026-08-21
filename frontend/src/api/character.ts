/**
 * Character API Client — Phase 1 Character Memory System
 * 14 endpoints for character CRUD, extraction, images, traits, relationships
 */

import { request } from '@/api/client';

const BASE = '/characters';

export interface CharacterData {
  id?: string;
  name: string;
  gender?: string;
  age?: number;
  species?: string;
  role?: string;
  novel_id?: string;
  appearance?: Record<string, unknown>;
  personality?: Record<string, unknown>;
  combat_style?: Record<string, unknown>;
}

export interface CharacterImage {
  id?: string;
  character_id: string;
  url: string;
  reference_embedding?: number[];
  is_reference?: boolean;
  created_at?: string;
  label?: string;
}

export interface CharacterTrait {
  id?: string;
  character_id: string;
  name: string;
  description: string;
}

export interface CharacterCostume {
  id?: string;
  character_id: string;
  name: string;
  description: string;
  season?: string;
  is_default?: boolean;
}

export interface Relationship {
  id?: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  description?: string;
  related_name?: string;
}

export interface ConsistencyResult {
  character_id: string;
  similarity: number;
  passed: boolean;
  threshold: number;
  message: string;
}

export interface ExtractRequest {
  text: string;
  novel_id?: string;
}

const encoded = (value: string) => encodeURIComponent(value);

function api<T>(url: string, options?: RequestInit): Promise<T> {
  return request<T>(`${BASE}${url}`, options);
}

type RawCharacter = Record<string, unknown> & { name: string };
type RawImage = Record<string, unknown>;
type RawRelationship = Record<string, unknown>;

function jsonRecord(value: unknown): Record<string, unknown> | undefined {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value !== 'string' || !value.trim()) return undefined;
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : undefined;
  } catch {
    return undefined;
  }
}

function normalizeCharacter(raw: RawCharacter): CharacterData {
  return {
    ...(raw as CharacterData),
    name: String(raw.name),
    appearance: jsonRecord(raw.appearance),
    personality: jsonRecord(raw.personality),
    combat_style: jsonRecord(raw.combat_style),
  };
}

const IMAGE_LABELS: Record<string, string> = {
  front_view: 'front',
  side_view: 'side',
  expression: 'expression',
  action: 'action',
};

const IMAGE_TYPES: Record<string, string> = {
  front: 'front_view',
  side: 'side_view',
  expression: 'expression',
  action: 'action',
};

function normalizeImage(raw: RawImage): CharacterImage {
  const imageId = typeof raw.id === 'string' ? raw.id : undefined;
  const filePath = String(raw.file_path ?? raw.url ?? '');
  const directlyUsable = /^(?:https?:|data:)/i.test(filePath);
  return {
    id: imageId,
    character_id: String(raw.character_id ?? ''),
    url: directlyUsable || !imageId
      ? filePath
      : `/api/characters/media/${encodeURIComponent(imageId)}`,
    label: IMAGE_LABELS[String(raw.image_type ?? '')] ?? String(raw.image_type ?? 'reference'),
    is_reference: Boolean(raw.is_primary ?? raw.is_reference),
    created_at: typeof raw.created_at === 'string' ? raw.created_at : undefined,
  };
}

function normalizeRelationship(raw: RawRelationship): Relationship {
  return {
    id: typeof raw.id === 'string' ? raw.id : undefined,
    source_id: String(raw.character_id ?? raw.source_id ?? ''),
    target_id: String(raw.related_id ?? raw.target_id ?? ''),
    relation_type: String(raw.relation_type ?? ''),
    description: typeof raw.description === 'string' ? raw.description : undefined,
    related_name: typeof raw.related_name === 'string' ? raw.related_name : undefined,
  };
}

// ── Character CRUD ──

export async function listCharacters(novelId?: string): Promise<CharacterData[]> {
  const params = novelId ? `?novel_id=${encodeURIComponent(novelId)}` : '';
  const raw = await api<RawCharacter[]>(`/${params}`);
  return raw.map(normalizeCharacter);
}

export async function getCharacter(id: string): Promise<CharacterData> {
  const raw = await api<RawCharacter | { character: RawCharacter }>(`/${encoded(id)}`);
  const character = 'character' in raw && raw.character && typeof raw.character === 'object'
    ? raw.character as RawCharacter
    : raw as RawCharacter;
  return normalizeCharacter(character);
}

export async function createCharacter(data: CharacterData): Promise<CharacterData> {
  const raw = await api<RawCharacter>('/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return normalizeCharacter(raw);
}

export function deleteCharacter(id: string): Promise<void> {
  return api<void>(`/${encoded(id)}`, { method: 'DELETE' });
}

export async function searchCharacters(query: string): Promise<CharacterData[]> {
  const raw = await api<RawCharacter[]>(`/search?q=${encodeURIComponent(query)}`);
  return raw.map(normalizeCharacter);
}

// ── Extraction ──

export async function extractCharacters(req: ExtractRequest): Promise<CharacterData[]> {
  const raw = await api<{ characters: RawCharacter[] }>('/extract', {
    method: 'POST',
    body: JSON.stringify(req),
  });
  return raw.characters.map(normalizeCharacter);
}

// ── Images ──

export async function listCharacterImages(characterId: string): Promise<CharacterImage[]> {
  const raw = await api<RawImage[]>(`/${encoded(characterId)}/images`);
  return raw.map(normalizeImage);
}

export async function addCharacterImage(characterId: string, image: Omit<CharacterImage, 'id'>): Promise<CharacterImage> {
  const params = new URLSearchParams({
    character_id: characterId,
    image_path: image.url,
    image_type: IMAGE_TYPES[image.label ?? ''] ?? image.label ?? 'reference',
    is_primary: String(Boolean(image.is_reference)),
  });
  const raw = await api<RawImage>(`/images?${params}`, {
    method: 'POST',
  });
  return normalizeImage(raw);
}

// ── Traits ──

export function listCharacterTraits(characterId: string): Promise<CharacterTrait[]> {
  return api<CharacterTrait[]>(`/${encoded(characterId)}/traits`);
}

export function addCharacterTrait(characterId: string, trait: Omit<CharacterTrait, 'id'>): Promise<CharacterTrait> {
  return api<CharacterTrait>('/traits', {
    method: 'POST',
    body: JSON.stringify({
      character_id: characterId,
      trait_type: 'other',
      name: trait.name,
      value: trait.description,
    }),
  });
}

// ── Costumes ──

export function listCharacterCostumes(characterId: string): Promise<CharacterCostume[]> {
  return api<CharacterCostume[]>(`/${encoded(characterId)}/costumes`);
}

// ── Relationships ──

export async function listRelationships(characterId: string): Promise<Relationship[]> {
  const raw = await api<RawRelationship[]>(`/${encoded(characterId)}/relationships`);
  return raw.map(normalizeRelationship);
}

export async function addRelationship(characterId: string, rel: Omit<Relationship, 'id'>): Promise<Relationship> {
  const raw = await api<RawRelationship>('/relationships', {
    method: 'POST',
    body: JSON.stringify({
      character_id: characterId,
      related_id: rel.target_id,
      relation_type: rel.relation_type,
      description: rel.description ?? '',
    }),
  });
  return normalizeRelationship(raw);
}

export function getRelationshipGraph(characterId: string, depth?: number): Promise<Record<string, unknown>> {
  const params = depth ? `?depth=${depth}` : '';
  return api(`/${encoded(characterId)}/graph${params}`);
}

// ── Consistency ──

export async function checkCharacterConsistency(characterId: string, imageUrl: string): Promise<ConsistencyResult> {
  const params = new URLSearchParams({ image_path: imageUrl });
  const raw = await api<{
    character_id?: string;
    consistent: boolean;
    score: number;
    threshold: number;
    reason?: string;
  }>(`/${encoded(characterId)}/consistency?${params}`, {
    method: 'GET',
  });
  return {
    character_id: raw.character_id ?? characterId,
    similarity: raw.score,
    passed: raw.consistent,
    threshold: raw.threshold,
    message: '',
  };
}

// ── Profile Export ──

export function exportCharacterProfile(characterId: string): Promise<Record<string, unknown>> {
  return api(`/${encoded(characterId)}`);
}
