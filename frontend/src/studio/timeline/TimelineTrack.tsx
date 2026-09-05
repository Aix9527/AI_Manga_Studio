import React, { useEffect, useState } from "react";

import { timelineApi } from "@/api/timeline";
import type { TimelineClip, TimelineTrack as TimelineTrackModel, WaveformEnvelope } from "@/types/timeline";

interface TimelineTrackProps {
  timelineId?: string;
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

interface WaveformState {
  envelope?: WaveformEnvelope;
  error?: string;
}

const TimelineTrack: React.FC<TimelineTrackProps> = ({
  timelineId = "",
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
  const [waveforms, setWaveforms] = useState<Record<string, WaveformState>>({});

  useEffect(() => {
    if (!timelineId || track.track_type !== "audio" || track.hidden) return;
    let alive = true;
    for (const clip of track.clips) {
      if (clip.artifact_id == null || waveforms[clip.id]) continue;
      void timelineApi.getWaveform(timelineId, clip.artifact_id, 128)
        .then((envelope) => {
          if (!alive) return;
          setWaveforms((current) => ({ ...current, [clip.id]: { envelope } }));
        })
        .catch(() => {
          if (!alive) return;
          setWaveforms((current) => ({ ...current, [clip.id]: { error: "波形提取失败，不影响剪辑" } }));
        });
    }
    return () => { alive = false; };
  }, [timelineId, track.track_type, track.hidden, track.clips, waveforms]);

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
          const waveform = waveforms[clip.id];
          const points = waveform?.envelope?.peaks ?? [];
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
              {points.length ? (
                <svg className="nle-waveform" viewBox={`0 0 ${points.length} 2`} preserveAspectRatio="none" aria-hidden="true">
                  <polyline
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="0.08"
                    points={points.map((peak, index) => `${index},${1 - Math.max(-1, Math.min(1, peak))}`).join(" ")}
                  />
                </svg>
              ) : null}
              {waveform?.error ? <span className="nle-waveform-warning" title={waveform.error}>波形不可用</span> : null}
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
