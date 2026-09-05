import React from "react";

import type { TimelineClip, TimelineTrack as TimelineTrackModel } from "@/types/timeline";

interface TimelineTrackProps {
  track: TimelineTrackModel;
  pixelsPerSecond: number;
  timebaseHz: number;
  selectedClipId?: string | null;
  draggingClipId?: string | null;
  onSelectClip: (clip: TimelineClip) => void;
  onClipPointerDown: (clip: TimelineClip) => void;
  onClipPointerMove: (clip: TimelineClip) => void;
  onClipPointerUp: (clip: TimelineClip) => void;
  onTrimPointerUp: (clip: TimelineClip, edge: "left" | "right") => void;
}

const TimelineTrack: React.FC<TimelineTrackProps> = ({
  track,
  pixelsPerSecond,
  timebaseHz,
  selectedClipId,
  draggingClipId,
  onSelectClip,
  onClipPointerDown,
  onClipPointerMove,
  onClipPointerUp,
  onTrimPointerUp,
}) => {
  return (
    <div
      className={`nle-track nle-track--${track.track_type}${track.locked ? " is-locked" : ""}`}
      data-testid={`timeline-track-${track.role}`}
    >
      <div className="nle-track__label">
        <strong>{track.name}</strong>
        <span>{track.role}</span>
      </div>
      <div className="nle-track__content">
        {track.clips.map((clip) => {
          const left = (clip.timeline_start_tick / timebaseHz) * pixelsPerSecond;
          const width = Math.max(42, (clip.duration_tick / timebaseHz) * pixelsPerSecond);
          const selected = selectedClipId === clip.id;
          const dragging = draggingClipId === clip.id;
          return (
            <button
              key={clip.id}
              type="button"
              data-testid={`timeline-clip-${clip.id}`}
              className={`nle-clip${selected ? " is-selected" : ""}${dragging ? " is-dragging" : ""}${clip.link_group_id ? " is-linked" : ""}`}
              style={{ left, width }}
              disabled={track.locked || clip.locked}
              onClick={() => onSelectClip(clip)}
              onPointerDown={() => onClipPointerDown(clip)}
              onPointerMove={() => onClipPointerMove(clip)}
              onPointerUp={() => onClipPointerUp(clip)}
            >
              <span className="nle-clip__title">{clip.shot_id || clip.scene_id || clip.id}</span>
              <small>v{clip.artifact_version ?? 1}{clip.link_group_id ? " · 🔗" : ""}</small>
              {selected && !track.locked && !clip.locked ? (
                <>
                  <i
                    className="nle-trim-handle nle-trim-handle--left"
                    aria-label="左裁切"
                    onPointerUp={(event) => {
                      event.stopPropagation();
                      onTrimPointerUp(clip, "left");
                    }}
                  />
                  <i
                    className="nle-trim-handle nle-trim-handle--right"
                    aria-label="右裁切"
                    onPointerUp={(event) => {
                      event.stopPropagation();
                      onTrimPointerUp(clip, "right");
                    }}
                  />
                </>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default TimelineTrack;
