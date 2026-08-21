import React from "react";

import type { ShotData } from "@/api/story";
import { shotNumber } from "@/components/workbench/ShotGrid";

function seconds(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
}

interface ShotTimelineProps {
  shots: ShotData[];
  selectedShotId: string | null;
  onSelectShot: (shotId: string) => void;
}

const ShotTimeline: React.FC<ShotTimelineProps> = ({ shots, selectedShotId, onSelectShot }) => {
  const total = shots.reduce((sum, shot) => sum + Math.max(shot.duration, 0), 0);
  let elapsed = 0;

  return (
    <section className="director-timeline-panel" aria-labelledby="director-timeline-heading">
      <div className="director-section-heading">
        <h2 id="director-timeline-heading">全片时间线</h2>
        {shots.length > 0 ? <p>总时长 {seconds(total)} 秒</p> : null}
      </div>
      {shots.length === 0 || total <= 0 ? (
        <p className="director-empty-inline">暂无可用时间线</p>
      ) : (
        <ol className="director-timeline" aria-label="全片时间线">
          {shots.map((shot) => {
            const start = elapsed;
            elapsed += Math.max(shot.duration, 0);
            const ratio = (Math.max(shot.duration, 0) / total) * 100;
            const number = shotNumber(shot.index);
            return (
              <li key={shot.id}>
                <button
                  type="button"
                  aria-label={`定位镜头 ${number}`}
                  aria-pressed={selectedShotId === shot.id}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={ratio}
                  style={{ width: `${ratio}%` }}
                  onClick={() => onSelectShot(shot.id)}
                >
                  <strong>{number}</strong>
                  <span>{seconds(start)}–{seconds(elapsed)} 秒</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
};

export default ShotTimeline;
