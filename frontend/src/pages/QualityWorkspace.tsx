import React, { useEffect, useRef, useState } from "react";

import { userMessage } from "@/api/client";
import { normalizeQualityReport } from "@/api/vision";
import { workspaceApi } from "@/api/workspace";
import VisionScoreCard from "@/components/VisionScoreCard";
import { useJobStore } from "@/state/jobStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { ProjectAsset } from "@/workbench/types";

function shotTitle(shotId: string): string {
  const match = shotId.match(/(\d+)$/);
  return match ? `镜头 ${match[1].padStart(2, "0")}` : `镜头 ${shotId || "未标注"}`;
}

function AssetPreview({ asset }: { asset: ProjectAsset }) {
  const label = `${shotTitle(asset.shot_id)} 版本 ${asset.version} 预览`;
  if (asset.kind === "video") return <video src={asset.media_url} controls preload="metadata" aria-label={label} />;
  if (asset.kind === "image") return <img src={asset.media_url} alt={label} />;
  return <p className="workspace-muted">该素材类型不支持画面预览</p>;
}

export const QualityWorkspace: React.FC = () => {
  const projectId = useWorkspaceStore((state) => state.snapshot?.project_id ?? state.projectId);
  const {
    jobs,
    loadingProjectId,
    loadError: jobLoadError,
    refreshJob,
    retryProjectJobs,
  } = useJobStore();
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [regeneratingId, setRegeneratingId] = useState<number | null>(null);
  const requestSequence = useRef(0);
  const regenerationGeneration = useRef(0);

  useEffect(() => () => {
    regenerationGeneration.current += 1;
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return undefined;
    const token = ++requestSequence.current;
    setLoading(true);
    setError(null);
    void workspaceApi.listAssets(projectId, {}).then((result) => {
      if (token === requestSequence.current) setAssets(result);
    }).catch((reason: unknown) => {
      if (token === requestSequence.current) {
        setAssets([]);
        setError(userMessage(reason));
      }
    }).finally(() => {
      if (token === requestSequence.current) setLoading(false);
    });
    return () => { requestSequence.current += 1; };
  }, [projectId, reloadToken]);

  const regenerate = async (asset: ProjectAsset) => {
    const generation = ++regenerationGeneration.current;
    const targetProjectId = projectId;
    setRegeneratingId(asset.id);
    setError(null);
    try {
      const updated = await workspaceApi.regenerateAsset(targetProjectId, asset.id);
      if (generation !== regenerationGeneration.current) return;
      await refreshJob(updated.id);
      if (generation !== regenerationGeneration.current) return;
      setReloadToken((value) => value + 1);
    } catch (reason) {
      if (generation === regenerationGeneration.current) setError(userMessage(reason));
    } finally {
      if (generation === regenerationGeneration.current) setRegeneratingId(null);
    }
  };

  return (
    <section className="workspace-page quality-workspace" aria-labelledby="quality-workspace-title">
      <header className="workspace-page__header"><div><p className="workspace-eyebrow">具体素材版本的质检记录</p><h1 id="quality-workspace-title">视觉质检</h1></div></header>
      {loading ? <p className="workspace-feedback" role="status">正在加载质检结果</p> : null}
      {error ? <p className="workspace-error" role="alert">{error}</p> : null}
      {jobLoadError ? (
        <div className="workspace-error" role="alert">
          <p>任务状态加载失败，请重新加载任务</p>
          <button type="button" onClick={() => void retryProjectJobs().catch(() => undefined)}>重新加载任务</button>
        </div>
      ) : null}
      {!loading && !error && assets.length === 0 ? <p className="workspace-muted">当前项目暂无可质检素材版本</p> : null}
      <div className="quality-list">
        {assets.map((asset) => {
          const report = normalizeQualityReport(asset.quality_report);
          const job = jobs.get(asset.job_id);
          const firstReviewStep = job?.steps.find((step) => step.status === "waiting_review");
          const taskStateLoading = loadingProjectId === projectId;
          const canRegenerate = asset.active
            && !taskStateLoading
            && !jobLoadError
            && job?.status === "waiting_review"
            && firstReviewStep?.id === asset.step_id;
          const disabledReason = canRegenerate
            ? undefined
            : taskStateLoading
              ? "正在加载任务状态"
              : jobLoadError
                ? "任务状态加载失败，请重新加载任务"
                : "该版本当前不处于待审核状态";
          return (
            <VisionScoreCard
              key={asset.id}
              assetId={asset.id}
              version={asset.version}
              shotId={asset.shot_id}
              title={`${shotTitle(asset.shot_id)} · 版本 ${asset.version}`}
              overallScore={report.overallScore}
              scores={report.dimensions}
              passed={report.passed}
              issues={report.issues}
              suggestions={report.suggestions}
              qualityAttempt={asset.quality_attempt}
              hasReport={report.hasReport}
              preview={<AssetPreview asset={asset} />}
              disabled={!canRegenerate}
              disabledReason={disabledReason}
              isRegenerating={regeneratingId === asset.id}
              onRegenerate={() => void regenerate(asset)}
            />
          );
        })}
      </div>
    </section>
  );
};

export default QualityWorkspace;
