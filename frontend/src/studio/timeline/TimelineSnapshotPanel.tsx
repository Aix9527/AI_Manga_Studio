import React, { useMemo, useState } from "react";

import type {
  TimelineDraft,
  TimelineExportResult,
  TimelineOutputProfile,
  TimelinePreflight,
  TimelineQcStatus,
  TimelineSnapshot,
} from "@/types/timeline";

interface TimelineSnapshotPanelProps {
  draft: TimelineDraft;
  preflight: TimelinePreflight | null;
  snapshots: TimelineSnapshot[];
  selectedSnapshotId: string | null;
  qcBySnapshot: Record<string, TimelineQcStatus>;
  exportBySnapshot?: Record<string, TimelineExportResult>;
  pendingSave: boolean;
  onSelectSnapshot: (snapshotId: string) => void;
  onFlush: () => Promise<void>;
  onCreateSnapshot: () => Promise<TimelineSnapshot | null>;
  onRunQc: (snapshotId: string) => Promise<void>;
  onExportSnapshot: (snapshotId: string, profile: TimelineOutputProfile) => Promise<unknown>;
}

const QC_LABEL: Record<string, string> = {
  not_run: "未运行",
  running: "检测中",
  passed: "通过",
  failed: "失败",
  stale: "源素材完整性已失效",
};

const TimelineSnapshotPanel: React.FC<TimelineSnapshotPanelProps> = ({
  draft,
  preflight,
  snapshots,
  selectedSnapshotId,
  qcBySnapshot,
  exportBySnapshot = {},
  pendingSave,
  onSelectSnapshot,
  onFlush,
  onCreateSnapshot,
  onRunQc,
  onExportSnapshot,
}) => {
  const [resolution, setResolution] = useState("1080x1920");
  const [fps, setFps] = useState("24");
  const [busy, setBusy] = useState<"snapshot" | "qc" | "export" | null>(null);
  const selected = useMemo(() => {
    const explicit = snapshots.find((item) => item.id === selectedSnapshotId);
    return explicit ?? (snapshots.length ? snapshots[snapshots.length - 1] : null);
  }, [snapshots, selectedSnapshotId]);
  const qc = selected ? qcBySnapshot[selected.id] : undefined;
  const qcStatus = qc?.effective_status ?? "not_run";
  const exportResult = selected ? exportBySnapshot[selected.id] : undefined;
  const [width, height] = resolution.split("x").map(Number);
  const profile: TimelineOutputProfile = { width, height, fps_num: Number(fps), fps_den: 1 };
  const canExport = Boolean(selected && qcStatus === "passed" && busy === null);

  const createSnapshot = async () => {
    setBusy("snapshot");
    try {
      await onFlush();
      await onCreateSnapshot();
    } finally {
      setBusy(null);
    }
  };

  const runQc = async () => {
    if (!selected) return;
    setBusy("qc");
    try {
      await onFlush();
      await onRunQc(selected.id);
    } finally {
      setBusy(null);
    }
  };

  const exportSnapshot = async () => {
    if (!selected || !canExport) return;
    setBusy("export");
    try {
      await onFlush();
      await onExportSnapshot(selected.id, profile);
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="studio-panel nle-snapshot-panel" data-testid="timeline-snapshot-panel">
      <div className="studio-panel__header">
        <div>
          <strong>版本 · Snapshot QC · 导出</strong>
          <span>Draft r{draft.revision}{pendingSave ? " · 有待保存操作" : " · 已同步"}</span>
        </div>
      </div>

      {preflight ? (
        <div className={`nle-preflight nle-preflight--${preflight.status}`}>
          结构预检：{preflight.status}{preflight.warnings.length ? ` · ${preflight.warnings.length} 条提示` : " · 无阻塞"}
        </div>
      ) : null}

      <button type="button" onClick={() => void createSnapshot()} disabled={busy !== null}>
        {busy === "snapshot" ? "正在创建…" : "创建版本"}
      </button>

      <div className="nle-snapshot-list">
        {snapshots.length === 0 ? <span>尚无 Snapshot</span> : snapshots.map((item) => {
          const status = qcBySnapshot[item.id]?.effective_status ?? "not_run";
          return (
            <button
              key={item.id}
              type="button"
              className={selected?.id === item.id ? "is-active" : ""}
              onClick={() => onSelectSnapshot(item.id)}
            >
              Snapshot #{item.snapshot_no} · QC {QC_LABEL[status] ?? status}
            </button>
          );
        })}
      </div>

      {selected ? (
        <div className="nle-snapshot-status">
          <strong>Snapshot #{selected.snapshot_no}</strong>
          <span>QC {QC_LABEL[qcStatus] ?? qcStatus}</span>
          {qcStatus === "stale" ? <p role="alert">源素材完整性已失效，请重新生成 Snapshot 或恢复原始素材后再次 QC。</p> : null}
          {qcStatus === "failed" ? <p role="alert">正式 QC 未通过，禁止导出当前 Snapshot。</p> : null}
          {exportResult?.job_id ? <small>导出 Job · {exportResult.job_id}</small> : null}
        </div>
      ) : null}

      <button type="button" onClick={() => void runQc()} disabled={!selected || busy !== null}>
        {busy === "qc" ? "QC 中…" : "运行正式 QC"}
      </button>

      <label>
        导出分辨率
        <select aria-label="导出分辨率" value={resolution} onChange={(event) => setResolution(event.target.value)}>
          <option value="1080x1920">1080x1920 · 9:16</option>
          <option value="1920x1080">1920x1080 · 16:9</option>
        </select>
      </label>
      <label>
        导出帧率
        <select aria-label="导出帧率" value={fps} onChange={(event) => setFps(event.target.value)}>
          <option value="24">24 fps</option>
          <option value="25">25 fps</option>
          <option value="30">30 fps</option>
        </select>
      </label>

      <button type="button" className="studio-primary-button" disabled={!canExport} onClick={() => void exportSnapshot()}>
        {busy === "export" ? "正在提交…" : "导出 Snapshot"}
      </button>
    </section>
  );
};

export default TimelineSnapshotPanel;
