import React, { useEffect, useRef, useState } from "react";

import { ApiError, userMessage } from "@/api/client";
import * as pipelineApi from "@/api/pipeline";
import type { ShotData, ShotUpdate } from "@/api/story";
import { useStoryStore } from "@/state/storyStore";

const SHOT_TYPE_OPTIONS = [
  ["wide", "远景"], ["medium", "中景"], ["close-up", "特写"],
  ["extreme-close-up", "大特写"], ["long", "全景"], ["panorama", "横移全景"],
] as const;
const CAMERA_ANGLE_OPTIONS = [
  ["eye-level", "平视"], ["low-angle", "低机位"], ["high-angle", "高机位"],
  ["dutch", "倾斜机位"], ["birds-eye", "俯瞰"], ["worms-eye", "仰视"],
] as const;
const CAMERA_MOVEMENT_OPTIONS = [
  ["static", "固定"], ["pan-left", "左摇"], ["pan-right", "右摇"],
  ["tilt-up", "上摇"], ["tilt-down", "下摇"], ["dolly-in", "推进"],
  ["dolly-out", "拉远"], ["tracking", "跟拍"], ["handheld", "手持"],
] as const;

type Draft = Required<Pick<ShotUpdate,
  | "shot_type" | "camera_angle" | "camera_movement" | "description" | "action"
  | "dialogue" | "narration" | "emotion" | "character_ids" | "duration"
  | "positive_prompt" | "negative_prompt" | "seed" | "image_model" | "video_model"
>>;

function toDraft(shot: ShotData): Draft {
  return {
    shot_type: shot.shot_type,
    camera_angle: shot.camera_angle,
    camera_movement: shot.camera_movement,
    description: shot.description,
    action: shot.action,
    dialogue: shot.dialogue,
    narration: shot.narration,
    emotion: shot.emotion,
    character_ids: shot.character_ids,
    duration: shot.duration,
    positive_prompt: shot.positive_prompt,
    negative_prompt: shot.negative_prompt,
    seed: shot.seed,
    image_model: shot.image_model,
    video_model: shot.video_model,
  };
}

function localized(error: unknown, fallback: string): string {
  return error instanceof ApiError || error instanceof TypeError ? userMessage(error) : fallback;
}

const ShotInspector: React.FC = () => {
  const selectedShotId = useStoryStore((state) => state.selectedShotId);
  const novelId = useStoryStore((state) => state.storyboardNovelId);
  const shot = useStoryStore((state) => state.shots.find((candidate) => candidate.id === selectedShotId));
  const updateShot = useStoryStore((state) => state.updateShot);
  const [draft, setDraft] = useState<Draft | null>(shot ? toDraft(shot) : null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selectionVersion = useRef(0);
  const revision = useRef(0);

  useEffect(() => {
    selectionVersion.current += 1;
    revision.current = 0;
    setDraft(shot ? toDraft(shot) : null);
    setDirty(false);
    setSaving(false);
    setCompiling(false);
    setFeedback(null);
    setError(null);
  }, [shot?.id]);

  if (!shot || !draft || !novelId) {
    return <div className="shot-inspector__empty">选择镜头后可编辑制作参数。</div>;
  }

  const change = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    revision.current += 1;
    setDraft((current) => current ? { ...current, [key]: value } : current);
    setDirty(true);
    setFeedback(null);
    setError(null);
  };

  const save = async () => {
    const activeSelection = selectionVersion.current;
    const activeRevision = revision.current;
    const activeShotId = shot.id;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateShot(novelId, activeShotId, draft);
      if (
        activeSelection !== selectionVersion.current ||
        activeRevision !== revision.current ||
        useStoryStore.getState().selectedShotId !== activeShotId
      ) return;
      setDraft(toDraft(updated));
      setDirty(false);
      setFeedback("已保存");
    } catch (saveError) {
      if (activeSelection !== selectionVersion.current) return;
      setError(localized(saveError, "保存镜头设置失败，请重试"));
    } finally {
      if (activeSelection === selectionVersion.current) setSaving(false);
    }
  };

  const compile = async () => {
    const activeSelection = selectionVersion.current;
    const activeShotId = shot.id;
    setCompiling(true);
    setError(null);
    try {
      const compiled = await pipelineApi.compileSingleShot({
        id: shot.id,
        scene_id: shot.scene_id,
        index: shot.index,
        ...draft,
      });
      if (
        activeSelection !== selectionVersion.current ||
        useStoryStore.getState().selectedShotId !== activeShotId
      ) return;
      const parameters = compiled.parameters ?? {};
      revision.current += 1;
      setDraft((current) => current ? {
        ...current,
        positive_prompt: compiled.positive_prompt,
        negative_prompt: compiled.negative_prompt,
        ...(typeof parameters.seed === "number" ? { seed: parameters.seed } : {}),
        ...(typeof parameters.image_model === "string" ? { image_model: parameters.image_model } : {}),
        ...(typeof parameters.video_model === "string" ? { video_model: parameters.video_model } : {}),
      } : current);
      setDirty(true);
      setFeedback("提示词已编译，尚未保存");
    } catch (compileError) {
      if (activeSelection !== selectionVersion.current) return;
      setError(localized(compileError, "编译提示词失败，请重试"));
    } finally {
      if (activeSelection === selectionVersion.current) setCompiling(false);
    }
  };

  return (
    <form className="shot-inspector" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <div className="shot-inspector__grid">
        <label>景别<select value={draft.shot_type} onChange={(event) => change("shot_type", event.target.value)}>{SHOT_TYPE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>机位<select value={draft.camera_angle} onChange={(event) => change("camera_angle", event.target.value)}>{CAMERA_ANGLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>镜头运动<select value={draft.camera_movement} onChange={(event) => change("camera_movement", event.target.value)}>{CAMERA_MOVEMENT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>时长<input type="number" min="1" max="30" step="0.1" value={draft.duration} onChange={(event) => change("duration", Number(event.target.value))} /></label>
        <label>情绪<input value={draft.emotion} onChange={(event) => change("emotion", event.target.value)} /></label>
        <label>随机种子<input type="number" min="0" max="4294967295" value={draft.seed} onChange={(event) => change("seed", Number(event.target.value))} /></label>
      </div>
      <label>镜头描述<textarea value={draft.description} onChange={(event) => change("description", event.target.value)} /></label>
      <label>动作<textarea value={draft.action} onChange={(event) => change("action", event.target.value)} /></label>
      <label>台词<textarea value={draft.dialogue} onChange={(event) => change("dialogue", event.target.value)} /></label>
      <label>旁白<textarea value={draft.narration} onChange={(event) => change("narration", event.target.value)} /></label>
      <label>正向提示词<textarea value={draft.positive_prompt} onChange={(event) => change("positive_prompt", event.target.value)} /></label>
      <label>负向提示词<textarea value={draft.negative_prompt} onChange={(event) => change("negative_prompt", event.target.value)} /></label>
      <label>图像模型<input value={draft.image_model} onChange={(event) => change("image_model", event.target.value)} /></label>
      <label>视频模型<input value={draft.video_model} onChange={(event) => change("video_model", event.target.value)} /></label>
      {dirty || feedback ? <p role="status">{dirty ? "有未保存修改" : feedback}</p> : null}
      {error ? <p className="shot-inspector__error" role="alert">{error}</p> : null}
      <div className="shot-inspector__actions">
        <button type="submit" disabled={!dirty || saving}>{saving ? "保存中…" : "保存镜头设置"}</button>
        <button type="button" disabled={compiling} onClick={() => void compile()}>{compiling ? "编译中…" : "编译提示词"}</button>
      </div>
    </form>
  );
};

export default ShotInspector;
