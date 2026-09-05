import React from "react";

import type { TimelineClip, TimelineDraft, TimelineOperation } from "@/types/timeline";

interface TimelineInspectorProps {
  draft: TimelineDraft;
  selectedClip: TimelineClip | null;
  onCriticalOperation: (operation: TimelineOperation) => void | Promise<unknown>;
}

const TimelineInspector: React.FC<TimelineInspectorProps> = ({ draft, selectedClip, onCriticalOperation }) => {
  if (!selectedClip) {
    return <div className="nle-inspector-empty">选择片段查看剪辑信息</div>;
  }

  return (
    <div className="nle-inspector" data-testid="timeline-clip-inspector">
      <div><span>片段</span><strong>{selectedClip.shot_id || selectedClip.id}</strong></div>
      <div><span>Artifact</span><strong>#{selectedClip.artifact_id ?? "-"} · v{selectedClip.artifact_version ?? "-"}</strong></div>
      <div><span>时间</span><strong>{selectedClip.timeline_start_tick} → {selectedClip.timeline_start_tick + selectedClip.duration_tick}</strong></div>
      <div><span>源范围</span><strong>{selectedClip.source_in_tick} → {selectedClip.source_out_tick}</strong></div>
      <div><span>链接</span><strong>{selectedClip.link_group_id ? "已链接" : "未链接"}</strong></div>
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
