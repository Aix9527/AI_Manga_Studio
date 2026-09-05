import React, { useState } from "react";

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

const TimelineInspector: React.FC<TimelineInspectorProps> = ({ draft, selectedClip, artifactUpgrade, onCriticalOperation }) => {
  const [keepOld, setKeepOld] = useState(false);
  if (!selectedClip) {
    return <div className="nle-inspector-empty">选择片段查看剪辑信息</div>;
  }

  const matchingClipIds = draft.tracks
    .flatMap((track) => track.clips)
    .filter((clip) => clip.shot_id === selectedClip.shot_id && clip.artifact_version === selectedClip.artifact_version)
    .map((clip) => clip.id);

  return (
    <div className="nle-inspector" data-testid="timeline-clip-inspector">
      <div><span>片段</span><strong>{selectedClip.shot_id || selectedClip.id}</strong></div>
      <div><span>Artifact</span><strong>#{selectedClip.artifact_id ?? "-"} · v{selectedClip.artifact_version ?? "-"}</strong></div>
      <div><span>时间</span><strong>{selectedClip.timeline_start_tick} → {selectedClip.timeline_start_tick + selectedClip.duration_tick}</strong></div>
      <div><span>源范围</span><strong>{selectedClip.source_in_tick} → {selectedClip.source_out_tick}</strong></div>
      <div><span>链接</span><strong>{selectedClip.link_group_id ? "已链接" : "未链接"}</strong></div>
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
