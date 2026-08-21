/**
 * Agent API Client — Phase 3 Director Agent System
 */

import { request } from '@/api/client';

const BASE = '/agents';

export interface ShotBrief {
  shot_id: string;
  panel_layout: string;
  decisions: Decision[];
  approved: boolean;
  feedback?: string;
  shot: {
    id: string;
    scene_id: string;
    index: number;
    shot_type: string;
    camera_angle: string;
    description: string;
    action: string;
    dialogue: string;
    emotion: string;
    character_ids: string[];
  };
}

export interface Decision {
  type: string;
  value: string;
  reason: string;
}

export interface DirectorPlanRequest {
  shots: Array<{
    id: string;
    scene_id: string;
    index: number;
    shot_type: string;
    camera_angle: string;
    description: string;
    action?: string;
    dialogue?: string;
    emotion?: string;
    character_ids: string[];
  }>;
}

export interface WriterEnhanceRequest {
  id: string;
  description: string;
}

export interface WriterEnhanceResponse {
  id: string;
  enhanced_description: string;
  notes: string[];
  dialogue_polish?: string;
}

export interface CharacterContext {
  character_id: string;
  shot_id: string;
  emotion: string;
  appearance_summary: string;
  costume_suggestion: string;
  expression_guide: string;
  has_reference_image: boolean;
}

export interface CriticReview {
  shot_id: string;
  approved: boolean;
  score: number;
  rules_passed: string[];
  rules_failed: Array<{ rule: string; reason: string }>;
  suggestions: string[];
}

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  return request<T>(`${BASE}${url}`, options);
}

// ── Director ──

export function planSequence(req: DirectorPlanRequest): Promise<ShotBrief[]> {
  return api<ShotBrief[]>('/director/plan', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export function planSingleShot(shot: DirectorPlanRequest['shots'][0]): Promise<ShotBrief> {
  return api<ShotBrief>('/director/plan/shot', {
    method: 'POST',
    body: JSON.stringify(shot),
  });
}

// ── Writer ──

export function enhanceScene(req: WriterEnhanceRequest): Promise<WriterEnhanceResponse> {
  return api<WriterEnhanceResponse>('/writer/enhance', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ── Character Agent ──

export function getCharacterContext(
  characterId: string,
  shotId: string,
  emotion?: string
): Promise<CharacterContext> {
  const params = emotion ? `?emotion=${encodeURIComponent(emotion)}` : '';
  return api<CharacterContext>(`/character/${encodeURIComponent(characterId)}/context/${encodeURIComponent(shotId)}${params}`);
}

// ── Critic ──

export function reviewShot(shotBrief: ShotBrief): Promise<CriticReview> {
  return api<CriticReview>('/critic/review', {
    method: 'POST',
    body: JSON.stringify(shotBrief),
  });
}

export function reviewSequence(shotBriefs: ShotBrief[]): Promise<CriticReview[]> {
  return api<CriticReview[]>('/critic/review/sequence', {
    method: 'POST',
    body: JSON.stringify({ shots: shotBriefs }),
  });
}
