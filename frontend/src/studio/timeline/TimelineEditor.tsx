import React, { useMemo, useState } from "react";

import TimelineInspector from "@/studio/timeline/TimelineInspector";
import TimelineTrack from "@/studio/timeline/TimelineTrack";
import type { TimelineClip, TimelineDraft, TimelineOperation } from "@/types/timeline";

interface ArtifactUpgrade {
  artifact_id: number;
  version: number;
}

interface TimelineEditorProps {
  draft: TimelineDraft;
  playheadTick: number;
  selectedClipId?: string | null;
  artifactUpgrades?: Record<string, ArtifactUpgrade>;
  onPlayheadChange: (tick: number) => void;
  onScheduleOperation: (operation: TimelineOperation) => void;
  onCriticalOperation: (operation: TimelineOperation) => void | Promise<unknown>;
  onSelectClip: (clip: TimelineClip) => void;
}

const PIXELS_PER_SECOND = 90;

function frameTick(draft: TimelineDraft): number {
  return Math.max(1, Math.round((draft.timebase_hz * draft.fps_den) / draft.fps_num));
}

const TimelineEditor: React.FC<TimelineEditorProps> = ({
  draft,
  playheadTick,
  selectedClipId: controlledSelectedClipId,
  artifactUpgrades = {},
  onPlayheadChange,
  onScheduleOperation,
  onCriticalOperation,
  onSelectClip,
}) => {
  const [internalSelectedClipId, setInternalSelectedClipId] = useState<string | null>(null);
  const [draggingClipId, setDraggingClipId] = useState<string | null>(null);
  const selectedClipId = controlledSelectedClipId ?? internalSelectedClipId;

  const allClips = useMemo(() => draft.tracks.flatMap((track) => track.clips), [draft.tracks]);
  const selectedClip = allClips.find((clip) => clip.id === selectedClipId) ?? null;
  const durationTick = useMemo(() => Math.max(
    draft.timebase_hz,
    ...allClips.map((clip) => clip.timeline_start_tick + clip.duration_tick),
    ...draft.subtitle_cues.map((cue) => cue.end_tick),
  ), [allClips, draft.subtitle_cues, draft.timebase_hz]);
  const timelineWidth = Math.max(720, (durationTick / draft.timebase_hz) * PIXELS_PER_SECOND + 120);

  const selectClip = (clip: TimelineClip) => {
    setInternalSelectedClipId(clip.id);
    onSelectClip(clip);
  };

  const handlePointerUp = (target: TimelineClip) => {
    if (!draggingClipId) return;
    const source = allClips.find((clip) => clip.id === draggingClipId);
    if (source && source.id !== target.id) {
      onScheduleOperation({
        type: "MOVE_CLIP",
        clip_id: source.id,
        insert_before_clip_id: target.id,
      });
    }
    setDraggingClipId(null);
  };

  const handleTrim = (clip: TimelineClip, edge: "left" | "right") => {
    const step = frameTick(draft);
    if (edge === "left") {
      const next = Math.min(clip.source_out_tick - step, clip.source_in_tick + step);
      if (next > clip.source_in_tick) {
        onScheduleOperation({ type: "TRIM_CLIP", clip_id: clip.id, edge, target_source_tick: next });
      }
      return;
    }
    const next = Math.max(clip.source_in_tick + step, clip.source_out_tick - step);
    if (next < clip.source_out_tick) {
      onScheduleOperation({ type: "TRIM_CLIP", clip_id: clip.id, edge, target_source_tick: next });
    }
  };

  const seconds = Math.ceil(durationTick / draft.timebase_hz);
  const rulerMarks = Array.from({ length: Math.max(2, Math.ceil(seconds / 5) + 1) }, (_, index) => index * 5);

  return (
    <div className="nle-editor" data-testid="timeline-editor">
      <div className="nle-toolbar">
        <button
          type="button"
          disabled={!selectedClip || playheadTick <= selectedClip.timeline_start_tick || playheadTick >= selectedClip.timeline_start_tick + selectedClip.duration_tick}
          onClick={() => selectedClip && void onCriticalOperation({ type: "SPLIT_CLIP", clip_id: selectedClip.id, timeline_tick: playheadTick })}
        >分割</button>
        <button
          type="button"
          disabled={!selectedClip}
          onClick={() => selectedClip && void onCriticalOperation({ type: "REMOVE_CLIP", clip_id: selectedClip.id, mode: "ripple" })}
        >波纹删除</button>
        <span>Draft r{draft.revision}</span>
        <span>{draft.fps_num}/{draft.fps_den} fps</span>
      </div>

      <div className="nle-scroll">
        <div className="nle-canvas" style={{ width: timelineWidth }}>
          <div
            className="nle-ruler"
            onClick={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              const x = Math.max(0, event.clientX - rect.left);
              onPlayheadChange(Math.round((x / PIXELS_PER_SECOND) * draft.timebase_hz));
            }}
          >
            {rulerMarks.map((second) => (
              <span key={second} style={{ left: second * PIXELS_PER_SECOND }}>{second}s</span>
            ))}
          </div>
          <div
            className="nle-playhead"
            style={{ left: (playheadTick / draft.timebase_hz) * PIXELS_PER_SECOND + 112 }}
            aria-hidden="true"
          />
          {draft.tracks
            .filter((track) => !track.hidden)
            .sort((a, b) => a.sort_index - b.sort_index)
            .map((track) => (
              <TimelineTrack
                key={track.id}
                timelineId={draft.timeline_id}
                track={track}
                pixelsPerSecond={PIXELS_PER_SECOND}
                timebaseHz={draft.timebase_hz}
                selectedClipId={selectedClipId}
                draggingClipId={draggingClipId}
                onSelectClip={selectClip}
                onClipPointerDown={(clip) => {
                  selectClip(clip);
                  if (track.role === "video.main" && !track.locked && !clip.locked) {
                    setDraggingClipId(clip.id);
                  }
                }}
                onClipPointerMove={() => undefined}
                onClipPointerUp={handlePointerUp}
                onTrimPointerUp={handleTrim}
              />
            ))}
        </div>
      </div>

      <TimelineInspector
        draft={draft}
        selectedClip={selectedClip}
        artifactUpgrade={selectedClip ? artifactUpgrades[selectedClip.id] : null}
        onCriticalOperation={onCriticalOperation}
      />
    </div>
  );
};

export default TimelineEditor;
