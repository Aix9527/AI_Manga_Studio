/**
 * Story API Client — Phase 2 Story Graph Engine
 * 6 endpoints for story parsing, graph, timeline
 */

import { request } from '@/api/client';

const BASE = '/story';

export interface StoryNode {
  id: string;
  type: 'chapter' | 'scene' | 'shot';
  label: string;
  index: number;
  parent_id?: string;
  data: Record<string, unknown>;
}

export interface StoryEdge {
  source: string;
  target: string;
  edge_type: string;
}

export interface StoryGraph {
  id: string;
  novel_id: string;
  title: string;
  nodes: StoryNode[];
  edges: StoryEdge[];
}

export interface TimelineEvent {
  id: string;
  character_id: string;
  chapter_id: string;
  chapter_index: number;
  event_type: string;
  description: string;
  shot_id?: string;
}

export interface ParseRequest {
  text: string;
  novel_id?: string;
}

export interface ParseResponse {
  novel_id: string;
  title: string;
  chapters: number;
  scenes: number;
  shots: number;
  scene_data: SceneData[];
}

export interface SceneData {
  id: string;
  chapter_id: string;
  index: number;
  raw_text: string;
  description: string;
  location?: string;
  time_of_day?: string;
  mood?: string;
  shots: ShotData[];
}

export interface ShotData {
  id: string;
  scene_id: string;
  index: number;
  shot_type: string;
  camera_angle: string;
  camera_movement: string;
  description: string;
  action: string;
  dialogue: string;
  narration: string;
  emotion: string;
  character_ids: string[];
  duration: number;
  positive_prompt: string;
  negative_prompt: string;
  seed: number;
  image_model: string;
  video_model: string;
  thumbnail_url: string;
  production_status: string;
  quality_status: string;
  duration_hint?: string;
}

export type ShotUpdate = Partial<Pick<ShotData,
  | 'shot_type'
  | 'camera_angle'
  | 'camera_movement'
  | 'description'
  | 'action'
  | 'dialogue'
  | 'narration'
  | 'emotion'
  | 'character_ids'
  | 'duration'
  | 'positive_prompt'
  | 'negative_prompt'
  | 'seed'
  | 'image_model'
  | 'video_model'
  | 'thumbnail_url'
  | 'production_status'
  | 'quality_status'
>>;

function api<T>(url: string, options?: RequestInit): Promise<T> {
  return request<T>(`${BASE}${url}`, options);
}

interface RawParseResponse {
  novel_id?: string;
  title?: string;
  total_chapters?: number;
  total_scenes?: number;
  total_shots?: number;
  chapters?: unknown[];
  scenes?: RawSceneData[];
}

interface RawShotData extends Partial<ShotData> {
  id: string;
  scene_id: string;
  index: number;
}

interface RawSceneData extends Partial<Omit<SceneData, 'index' | 'shots'>> {
  number?: number;
  index?: number;
  shots?: RawShotData[];
}

interface RawTimelineEvent {
  id: string;
  character_id: string;
  chapter_number?: number;
  chapter_id?: string;
  chapter_index?: number;
  event_type: string;
  description: string;
  shot_id?: string;
}

function normalizeTimelineEvent(event: RawTimelineEvent): TimelineEvent {
  const chapterNumber = event.chapter_number ?? ((event.chapter_index ?? 0) + 1);
  return {
    id: event.id,
    character_id: event.character_id,
    chapter_id: event.chapter_id ?? String(chapterNumber),
    chapter_index: event.chapter_index ?? Math.max(chapterNumber - 1, 0),
    event_type: event.event_type,
    description: event.description,
    ...(event.shot_id ? { shot_id: event.shot_id } : {}),
  };
}

function normalizeShot(shot: RawShotData): ShotData {
  return {
    id: shot.id,
    scene_id: shot.scene_id,
    index: shot.index,
    shot_type: shot.shot_type ?? '',
    camera_angle: shot.camera_angle ?? '',
    camera_movement: shot.camera_movement ?? 'static',
    description: shot.description ?? '',
    action: shot.action ?? '',
    dialogue: shot.dialogue ?? '',
    narration: shot.narration ?? '',
    emotion: shot.emotion ?? '',
    character_ids: shot.character_ids ?? [],
    duration: shot.duration ?? 5,
    positive_prompt: shot.positive_prompt ?? '',
    negative_prompt: shot.negative_prompt ?? '',
    seed: shot.seed ?? 0,
    image_model: shot.image_model ?? '',
    video_model: shot.video_model ?? '',
    thumbnail_url: shot.thumbnail_url ?? '',
    production_status: shot.production_status ?? 'pending',
    quality_status: shot.quality_status ?? 'unreviewed',
    ...(shot.duration_hint ? { duration_hint: shot.duration_hint } : {}),
  };
}

function normalizeScenes(scenes: RawSceneData[] | undefined): SceneData[] {
  return (scenes ?? []).map((scene, position) => ({
    id: scene.id ?? `scene-${position + 1}`,
    chapter_id: scene.chapter_id ?? '',
    index: scene.index ?? Math.max((scene.number ?? position + 1) - 1, 0),
    raw_text: scene.raw_text ?? '',
    description: scene.description ?? scene.raw_text ?? '',
    ...(scene.location ? { location: scene.location } : {}),
    ...(scene.time_of_day ? { time_of_day: scene.time_of_day } : {}),
    ...(scene.mood ? { mood: scene.mood } : {}),
    shots: (scene.shots ?? []).map(normalizeShot),
  }));
}

// ── Parse ──

export async function parseStory(req: ParseRequest): Promise<ParseResponse> {
  const raw = await api<RawParseResponse>('/parse', {
    method: 'POST',
    body: JSON.stringify({ text: req.text, novel_id: req.novel_id ?? '' }),
  });
  return {
    novel_id: raw.novel_id ?? req.novel_id ?? '',
    title: raw.title ?? '',
    chapters: raw.total_chapters ?? raw.chapters?.length ?? 0,
    scenes: raw.total_scenes ?? 0,
    shots: raw.total_shots ?? 0,
    scene_data: normalizeScenes(raw.scenes),
  };
}

export async function parseScenes(text: string, novelId?: string): Promise<SceneData[]> {
  const raw = await api<{ scene_count: number; scenes: RawSceneData[] }>('/parse/scenes', {
    method: 'POST',
    body: JSON.stringify({ text, novel_id: novelId ?? '' }),
  });
  return normalizeScenes(raw.scenes);
}

// ── Graph ──

export function getStoryGraph(novelId: string): Promise<StoryGraph> {
  return api<StoryGraph>(`/graph/${encodeURIComponent(novelId)}`);
}

export function getSequentialShots(novelId: string, chapterIndex?: number): Promise<ShotData[]> {
  const params = chapterIndex !== undefined ? `?chapter=${chapterIndex}` : '';
  return api<ShotData[]>(`/graph/${encodeURIComponent(novelId)}/shots${params}`);
}

export async function getStoryboardScenes(novelId: string): Promise<SceneData[]> {
  const scenes = await api<RawSceneData[]>(`/graph/${encodeURIComponent(novelId)}/scenes`);
  return normalizeScenes(scenes);
}

export async function updateShot(
  novelId: string,
  shotId: string,
  patch: ShotUpdate,
): Promise<ShotData> {
  const shot = await api<RawShotData>(
    `/${encodeURIComponent(novelId)}/shots/${encodeURIComponent(shotId)}`,
    { method: 'PATCH', body: JSON.stringify(patch) },
  );
  return normalizeShot(shot);
}

// ── Timeline ──

export async function getTimeline(novelId: string): Promise<TimelineEvent[]> {
  const raw = await api<{ events?: RawTimelineEvent[] }>(`/timeline/${encodeURIComponent(novelId)}`);
  return (raw.events ?? []).map(normalizeTimelineEvent);
}

export async function getCharacterTimeline(novelId: string, characterId: string): Promise<TimelineEvent[]> {
  const raw = await api<{ events?: RawTimelineEvent[] }>(
    `/timeline/${encodeURIComponent(novelId)}/character/${encodeURIComponent(characterId)}`
  );
  return (raw.events ?? []).map(normalizeTimelineEvent);
}

export interface TimelineEventInput {
  novel_id: string;
  chapter_number: number;
  character_id: string;
  event_type: string;
  description: string;
  relative_time?: string;
}

export async function addTimelineEvent(event: TimelineEventInput): Promise<TimelineEvent> {
  const raw = await api<RawTimelineEvent>('/timeline/event', {
    method: 'POST',
    body: JSON.stringify(event),
  });
  return normalizeTimelineEvent(raw);
}
