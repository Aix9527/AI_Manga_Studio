import React, { useCallback, useEffect, useState } from "react";

import { historyApi, type HistoryStats } from "@/api/history";
import { userMessage } from "@/api/client";
import { jobStoreActions } from "@/state/jobStore";
import { useWorkspaceStore } from "@/state/workspaceStore";

type ClearMode = "project" | "all";

interface ClearHistoryButtonProps {
  /** If true, shows a compact button. If false, shows a full panel. */
  compact?: boolean;
  /** Called after history is cleared successfully. */
  onCleared?: () => void;
}

const ClearHistoryButton: React.FC<ClearHistoryButtonProps> = ({
  compact = false,
  onCleared,
}) => {
  const [showConfirm, setShowConfirm] = useState(false);
  const [clearMode, setClearMode] = useState<ClearMode>("project");
  const [clearOutputs, setClearOutputs] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<HistoryStats | null>(null);

  const projectId = useWorkspaceStore((state) => state.projectId);

  // Load stats on mount and when result changes
  const loadStats = useCallback(async () => {
    try {
      const s = await historyApi.getStats();
      setStats(s);
    } catch {
      // Silent fail - stats are optional
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  const handleClear = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response =
        clearMode === "all"
          ? await historyApi.clearAll(clearOutputs)
          : await historyApi.clearProject(projectId || "default", clearOutputs);

      const sizeMB = (response.freed_bytes / 1024 / 1024).toFixed(1);
      setResult(
        `${response.message}。${response.freed_bytes > 0 ? `释放 ${sizeMB}MB 磁盘空间。` : ""}`,
      );

      // Refresh frontend state
      jobStoreActions().resetProjectJobs(projectId || "default");
      await useWorkspaceStore.getState().loadWorkspace(projectId || "default");

      // Reload stats
      await loadStats();

      // Notify parent
      onCleared?.();
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setLoading(false);
      setShowConfirm(false);
    }
  }, [clearMode, clearOutputs, projectId, loadStats, onCleared]);

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  };

  if (compact) {
    return (
      <>
        <button
          className="btn btn--danger btn--sm"
          onClick={() => {
            setClearMode("project");
            setShowConfirm(true);
          }}
          disabled={loading}
          title="清除当前项目的历史记录"
        >
          {loading ? "清除中..." : "清除历史"}
        </button>
        {showConfirm && (
          <ClearConfirmDialog
            mode={clearMode}
            setMode={setClearMode}
            clearOutputs={clearOutputs}
            setClearOutputs={setClearOutputs}
            onConfirm={handleClear}
            onCancel={() => setShowConfirm(false)}
            loading={loading}
            error={error}
            result={result}
          />
        )}
      </>
    );
  }

  return (
    <div className="clear-history-panel">
      <h3 className="clear-history-panel__title">历史记录管理</h3>

      {stats && (
        <div className="clear-history-panel__stats">
          <div className="stat-item">
            <span className="stat-item__label">任务记录</span>
            <span className="stat-item__value">{stats.total_jobs}</span>
          </div>
          <div className="stat-item">
            <span className="stat-item__label">产物文件</span>
            <span className="stat-item__value">{stats.total_artifacts}</span>
          </div>
          <div className="stat-item">
            <span className="stat-item__label">项目数量</span>
            <span className="stat-item__value">{stats.total_projects}</span>
          </div>
          <div className="stat-item">
            <span className="stat-item__label">磁盘占用</span>
            <span className="stat-item__value">{formatBytes(stats.storage_bytes)}</span>
          </div>
        </div>
      )}

      <div className="clear-history-panel__actions">
        <button
          className="btn btn--danger"
          onClick={() => {
            setClearMode("project");
            setShowConfirm(true);
          }}
          disabled={loading}
        >
          清除当前项目历史
        </button>
        <button
          className="btn btn--danger btn--outline"
          onClick={() => {
            setClearMode("all");
            setShowConfirm(true);
          }}
          disabled={loading}
        >
          清除全部历史
        </button>
      </div>

      {error && <p className="clear-history-panel__error" role="alert">{error}</p>}
      {result && <p className="clear-history-panel__success" role="status">{result}</p>}

      {showConfirm && (
        <ClearConfirmDialog
          mode={clearMode}
          setMode={setClearMode}
          clearOutputs={clearOutputs}
          setClearOutputs={setClearOutputs}
          onConfirm={handleClear}
          onCancel={() => setShowConfirm(false)}
          loading={loading}
          error={error}
          result={result}
        />
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Confirmation Dialog
// ---------------------------------------------------------------------------

interface ClearConfirmDialogProps {
  mode: ClearMode;
  setMode: (m: ClearMode) => void;
  clearOutputs: boolean;
  setClearOutputs: (v: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
  error: string | null;
  result: string | null;
}

const ClearConfirmDialog: React.FC<ClearConfirmDialogProps> = ({
  mode,
  setMode,
  clearOutputs,
  setClearOutputs,
  onConfirm,
  onCancel,
  loading,
  error,
  result,
}) => {
  return (
    <div className="clear-dialog__overlay" onClick={onCancel}>
      <div className="clear-dialog" onClick={(e) => e.stopPropagation()}>
        <h4 className="clear-dialog__title">
          {mode === "all" ? "确认清除全部历史" : "确认清除项目历史"}
        </h4>

        <p className="clear-dialog__warning">
          {mode === "all"
            ? "此操作将删除所有项目的任务记录、产物和输出文件，不可恢复。"
            : "此操作将删除当前项目的任务记录、产物和输出文件，不可恢复。"}
        </p>

        <div className="clear-dialog__mode">
          <label className="radio-label">
            <input
              type="radio"
              name="clear-mode"
              checked={mode === "project"}
              onChange={() => setMode("project")}
            />
            <span>仅当前项目</span>
          </label>
          <label className="radio-label">
            <input
              type="radio"
              name="clear-mode"
              checked={mode === "all"}
              onChange={() => setMode("all")}
            />
            <span>全部项目（完全重置）</span>
          </label>
        </div>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={clearOutputs}
            onChange={(e) => setClearOutputs(e.target.checked)}
          />
          <span>同时删除输出文件（图片、视频、音频）</span>
        </label>

        {error && <p className="clear-dialog__error" role="alert">{error}</p>}
        {result && <p className="clear-dialog__success" role="status">{result}</p>}

        <div className="clear-dialog__actions">
          <button
            className="btn btn--secondary"
            onClick={onCancel}
            disabled={loading}
          >
            取消
          </button>
          <button
            className="btn btn--danger"
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? "清除中..." : "确认清除"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ClearHistoryButton;
