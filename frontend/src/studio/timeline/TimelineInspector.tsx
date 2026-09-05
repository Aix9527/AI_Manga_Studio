import React, { useEffect, useMemo, useState } from "react";

import type { TimelineClip, TimelineDraft, TimelineOperation } from "@/types/timeline";

interface ArtifactUpgrade {
  artifact_id: number;
  version: number;
}

interface TimelineInspectorProps {
  draft: TimelineDraft;
  selectedClip: TimelineClip | null;
  artifactUpgrade?: ArtifactUpgrade | null;
  onCriticalOperation: (operation: TimelineOperation) => void | Promise<unknown>;
}

type TransitionSelection = "cut" | "crossfade" | "fade_to_black" | "fade_from_black";

const TimelineInspector: React.FC<TimelineInspectorProps> = ({ draft, selectedClip, artifactUpgrade, onCriticalOperation }) => {
  const [keepOld, setKeepOld] = useState(false);
  const [transitionType, setTransitionType] = useState<TransitionSelection>("cut");
  const [transitionMs, setTransitionMs] = useState("400");
  const [subtitleText, setSubtitleText] = useState("");

  const mainTrack = useMemo(
    () => draft.tracks.find((track) => track.role === "video.main") ?? null,
    [draft.tracks],
  );
  const orderedMainClips = useMemo(
    () => [...(mainTrack?.clips ?? [])].sort((a, b) => a.timeline_start_tick - b.timeline_start_tick || a.id.localeCompare(b.id)),
    [mainTrack],
  );
  const nextClip = useMemo(() => {
    if (!selectedClip) return null;
    const index = orderedMainClips.findIndex((clip) => clip.id === selectedClip.id);
    return index >= 0 && index + 1 < orderedMainClips.length ? orderedMainClips[index + 1] : null;
  }, [orderedMainClips, selectedClip]);
  const existingTransition = useMemo(() => {
    if (!selectedClip || !nextClip) return null;
    return draft.transitions.find(
      (transition) => transition.from_clip_id === selectedClip.id && transition.to_clip_id === nextClip.id,
    ) ?? null;
  }, [draft.transitions, nextClip, selectedClip]);
  const subtitleTrack = useMemo(
    () => draft.tracks.find((track) => track.role === "subtitle.primary" || track.track_type === "subtitle") ?? null,
    [draft.tracks],
  );
  const selectedCue = useMemo(() => {
    if (!selectedClip) return null;
    return draft.subtitle_cues.find((cue) => (
      cue.clip_id === selectedClip.id
      || (selectedClip.link_group_id && cue.link_group_id === selectedClip.link_group_id)
    )) ?? null;
  }, [draft.subtitle_cues, selectedClip]);

  useEffect(() => {
    setKeepOld(false);
    if (existingTransition) {
      const type = existingTransition.transition_type as TransitionSelection;
      setTransitionType(type === "crossfade" || type === "fade_to_black" || type === "fade_from_black" ? type : "cut");
      setTransitionMs(String(Math.max(1, Math.round(existingTransition.duration_tick / draft.timebase_hz * 1000))));
    } else {
      setTransitionType("cut");
      setTransitionMs("400");
    }
    setSubtitleText(selectedCue?.text ?? "");
  }, [draft.timebase_hz, existingTransition, selectedClip?.id, selectedCue?.id, selectedCue?.text]);

  if (!selectedClip) {
    return <div className="nle-inspector-empty">选择片段查看剪辑信息</div>;
  }

  const matchingClipIds = draft.tracks
    .flatMap((track) => track.clips)
    .filter((clip) => clip.shot_id === selectedClip.shot_id && clip.artifact_version === selectedClip.artifact_version)
    .map((clip) => clip.id);

  const applyTransition = async () => {
    if (!nextClip) return;
    if (transitionType === "cut") {
      if (existingTransition) {
        await onCriticalOperation({ type: "REMOVE_TRANSITION", transition_id: existingTransition.id });
      }
      return;
    }
    const durationMs = Number(transitionMs);
    if (!Number.isFinite(durationMs) || durationMs <= 0) return;
    const durationTick = Math.max(1, Math.round(durationMs / 1000 * draft.timebase_hz));
    if (existingTransition) {
      if (existingTransition.transition_type === transitionType) {
        await onCriticalOperation({
          type: "UPDATE_TRANSITION",
          transition_id: existingTransition.id,
          duration_tick: durationTick,
        });
        return;
      }
      await onCriticalOperation({ type: "REMOVE_TRANSITION", transition_id: existingTransition.id });
    }
    await onCriticalOperation({
      type: "ADD_TRANSITION",
      from_clip_id: selectedClip.id,
      to_clip_id: nextClip.id,
      transition_type: transitionType,
      duration_tick: durationTick,
    });
  };

  const saveSubtitle = async () => {
    const text = subtitleText.trim();
    if (!text) return;
    if (selectedCue) {
      await onCriticalOperation({ type: "UPDATE_SUBTITLE", cue_id: selectedCue.id, text });
      return;
    }
    if (!subtitleTrack) return;
    await onCriticalOperation({
      type: "ADD_SUBTITLE",
      track_id: subtitleTrack.id,
      start_tick: selectedClip.timeline_start_tick,
      end_tick: selectedClip.timeline_start_tick + selectedClip.duration_tick,
      text,
      clip_id: selectedClip.id,
      link_group_id: selectedClip.link_group_id,
    });
  };

  return (
    <div className="nle-inspector" data-testid="timeline-clip-inspector">
      <div><span>片段</span><strong>{selectedClip.shot_id || selectedClip.id}</strong></div>
      <div><span>Artifact</span><strong>#{selectedClip.artifact_id ?? "-"} · v{selectedClip.artifact_version ?? "-"}</strong></div>
      <div><span>时间</span><strong>{selectedClip.timeline_start_tick} → {selectedClip.timeline_start_tick + selectedClip.duration_tick}</strong></div>
      <div><span>源范围</span><strong>{selectedClip.source_in_tick} → {selectedClip.source_out_tick}</strong></div>
      <div><span>链接</span><strong>{selectedClip.link_group_id ? "已链接" : "未链接"}</strong></div>

      {nextClip && mainTrack?.id === selectedClip.track_id ? (
        <section className="nle-inspector-section nle-transition-editor">
          <strong>镜头转场</strong>
          <label>
            镜头转场
            <select
              aria-label="镜头转场"
              value={transitionType}
              onChange={(event) => setTransitionType(event.target.value as TransitionSelection)}
            >
              <option value="cut">Cut / 无转场</option>
              <option value="crossfade">Crossfade</option>
              <option value="fade_to_black">Fade to black</option>
              <option value="fade_from_black">Fade from black</option>
            </select>
          </label>
          <label>
            转场时长毫秒
            <input
              aria-label="转场时长毫秒"
              type="number"
              min={1}
              step={10}
              value={transitionMs}
              disabled={transitionType === "cut"}
              onChange={(event) => setTransitionMs(event.target.value)}
            />
          </label>
          <button type="button" onClick={() => void applyTransition()}>应用转场</button>
          <small>只有显式 Transition 才允许 V1 受控重叠；源素材手柄不足时由后端拒绝。</small>
        </section>
      ) : null}

      {subtitleTrack ? (
        <section className="nle-inspector-section nle-subtitle-editor">
          <strong>字幕</strong>
          <label>
            字幕文本
            <textarea
              aria-label="字幕文本"
              value={subtitleText}
              onChange={(event) => setSubtitleText(event.target.value)}
              placeholder="输入当前镜头字幕"
            />
          </label>
          <div className="nle-inspector__actions">
            <button type="button" disabled={!subtitleText.trim()} onClick={() => void saveSubtitle()}>保存字幕</button>
            {selectedCue ? (
              <button type="button" onClick={() => void onCriticalOperation({ type: "REMOVE_SUBTITLE", cue_id: selectedCue.id })}>删除字幕</button>
            ) : null}
          </div>
          <small>{selectedCue ? `${selectedCue.start_tick} → ${selectedCue.end_tick}` : "默认绑定当前 Clip 的时间范围与 Link Group"}</small>
        </section>
      ) : null}

      {artifactUpgrade ? (
        <div className={`nle-upgrade${keepOld ? " is-kept" : ""}`}>
          <strong>v{selectedClip.artifact_version ?? "-"} → v{artifactUpgrade.version} 可用</strong>
          <div className="nle-inspector__actions">
            <button type="button" onClick={() => setKeepOld(true)}>保留旧版</button>
            <button
              type="button"
              onClick={() => void onCriticalOperation({
                type: "REPLACE_ARTIFACT_VERSION",
                clip_ids: [selectedClip.id],
                artifact_id: artifactUpgrade.artifact_id,
              })}
            >替换当前</button>
            <button
              type="button"
              onClick={() => void onCriticalOperation({
                type: "REPLACE_ARTIFACT_VERSION",
                clip_ids: matchingClipIds.length ? matchingClipIds : [selectedClip.id],
                artifact_id: artifactUpgrade.artifact_id,
              })}
            >替换全部</button>
          </div>
        </div>
      ) : null}
      <div className="nle-inspector__actions">
        {selectedClip.link_group_id ? (
          <button type="button" onClick={() => void onCriticalOperation({ type: "UNLINK_CLIPS", clip_ids: [selectedClip.id] })}>解除链接</button>
        ) : null}
        <button type="button" onClick={() => void onCriticalOperation({ type: "REMOVE_CLIP", clip_id: selectedClip.id, mode: "ripple" })}>波纹删除</button>
      </div>
      <small>Draft r{draft.revision}</small>
    </div>
  );
};

export default TimelineInspector;
