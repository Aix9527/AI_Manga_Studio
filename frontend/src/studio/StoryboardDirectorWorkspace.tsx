import React, { useEffect, useMemo, useState } from "react";
import { PlayCircleOutlined, ReloadOutlined, SafetyCertificateOutlined } from "@ant-design/icons";

import { userMessage } from "@/api/client";
import { workspaceApi } from "@/api/workspace";
import { useJobStore } from "@/state/jobStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { ProjectAsset } from "@/workbench/types";

interface ShotView {
  id: string;
  title: string;
  duration: number;
  asset?: ProjectAsset;
}

const CAMERA = ["推镜", "平移", "跟拍", "摇镜"] as const;

function mediaShot(asset: ProjectAsset, index: number): ShotView {
  return {
    id: asset.shot_id || `shot-${index + 1}`,
    title: asset.metadata?.title ? String(asset.metadata.title) : asset.shot_id || `镜头 ${String(index + 1).padStart(2, "0")}`,
    duration: Number(asset.metadata?.duration || 5),
    asset,
  };
}

const fallbackShots: ShotView[] = Array.from({ length: 8 }).map((_, index) => ({
  id: `shot-${index + 1}`,
  title: ["建立镜头", "环境推进", "异象出现", "主角凝视", "冲突升级", "反应镜头", "动作爆发", "悬念收束"][index],
  duration: [6, 5, 7, 8, 6, 7, 5, 6][index],
}));

const StoryboardDirectorWorkspace: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const projectId = snapshot?.project_id || useWorkspaceStore.getState().projectId || "default";
  const { jobs, reviewJob, refreshJob } = useJobStore();
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [selectedId, setSelectedId] = useState<string>(fallbackShots[0].id);
  const [camera, setCamera] = useState<(typeof CAMERA)[number]>("推镜");
  const [prompt, setPrompt] = useState("电影感构图，角色保持一致，环境具有明确空间层次，镜头运动自然连贯。");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void workspaceApi.listAssets(projectId)
      .then((items) => alive && setAssets(items))
      .catch((error) => alive && setMessage(userMessage(error)));
    return () => { alive = false; };
  }, [projectId]);

  const shots = useMemo(() => {
    const media = assets.filter((asset) => asset.kind.includes("image") || asset.kind.includes("video") || asset.kind.includes("keyframe"));
    return media.length ? media.slice(0, 12).map(mediaShot) : fallbackShots;
  }, [assets]);
  const selected = shots.find((shot) => shot.id === selectedId) ?? shots[0];
  const selectedAsset = selected?.asset;
  const totalDuration = shots.reduce((sum, shot) => sum + shot.duration, 0);
  const selectedJob = selectedAsset?.job_id ? jobs.get(selectedAsset.job_id) : undefined;
  const selectedReviewStep = selectedAsset?.step_id
    ? selectedJob?.steps.find((step) => step.id === selectedAsset.step_id)
    : undefined;
  const canReviewSelected = Boolean(
    selectedAsset
    && selectedJob?.status === "waiting_review"
    && selectedReviewStep?.status === "waiting_review",
  );

  const continueToVideo = async () => {
    if (!selectedAsset || !canReviewSelected) {
      setMessage("当前镜头不是待审核关键帧，无法继续生成视频。");
      return;
    }
    try {
      await reviewJob(
        selectedAsset.job_id,
        "approve",
        `导演台批准 ${selectedAsset.shot_id || selected.title} 关键帧，继续后续视频生成`,
      );
      setMessage(`已批准${selected.title}，生产将继续到视频生成`);
    } catch (error) {
      setMessage(userMessage(error));
    }
  };

  const regenerate = async () => {
    if (!selectedAsset || !canReviewSelected) {
      setMessage(selectedAsset ? "当前镜头不是待审核版本，无法重拍。" : "当前是尚未生成的镜头草案；启动生成后会创建可重拍版本。");
      return;
    }
    try {
      await workspaceApi.regenerateAsset(projectId, selectedAsset.id);
      await refreshJob(selectedAsset.job_id);
      setMessage(`已为 ${selected.title} 创建重新生成任务`);
    } catch (error) {
      setMessage(userMessage(error));
    }
  };

  return (
    <div className="studio-workspace studio-three-pane">
      <aside className="studio-panel studio-left-pane">
        <div className="studio-panel__header"><div><strong>项目镜头树</strong><span>{shots.length} 镜头</span></div></div>
        <div className="inspector-section">
          <div className="story-list">
            <button type="button" className="is-active">场景 01 · 当前场景</button>
            {shots.map((shot, index) => (
              <button key={shot.id} type="button" className={selected?.id === shot.id ? "is-active" : ""} onClick={() => setSelectedId(shot.id)}>
                {String(index + 1).padStart(2, "0")} · {shot.title}
              </button>
            ))}
          </div>
        </div>
        <div className="inspector-section">
          <h3>版本历史</h3>
          <p className="subtle">{selectedAsset ? `当前 v${selectedAsset.version}` : "草案 v0"}</p>
          <p className="subtle">重拍不会覆盖旧版本，可随时回退。</p>
        </div>
      </aside>

      <section className="studio-center-pane">
        <header className="studio-workspace__header">
          <div>
            <h1>分镜导演台</h1>
            <p>场景 01 · {shots.length} 镜头 · 约 {totalDuration} 秒 · 本地导演控制</p>
          </div>
          <div className="asset-tabs">
            <button type="button" className="studio-secondary-button" disabled={!canReviewSelected} onClick={() => void regenerate()}><ReloadOutlined /> 重拍镜头</button>
            <button type="button" className="studio-primary-button" disabled={!canReviewSelected} onClick={() => void continueToVideo()}><PlayCircleOutlined /> 生成视频</button>
          </div>
        </header>

        <section className="director-preview">
          {selectedAsset?.media_url && selectedAsset.kind.includes("video") ? <video src={selectedAsset.media_url} controls preload="metadata" /> : null}
          {selectedAsset?.media_url && !selectedAsset.kind.includes("video") ? <img src={selectedAsset.media_url} alt={selected.title} /> : null}
          {!selectedAsset?.media_url ? <div className="studio-empty">{selected.title} · 等待关键帧 / 视频</div> : null}
          <span className="director-preview__overlay">当前镜头 · {selected.id}</span>
        </section>

        <section className="studio-panel">
          <div className="studio-panel__header"><div><strong>场景镜头</strong><span>点击镜头进入导演调参</span></div></div>
          <div className="inspector-section shot-rail">
            {shots.map((shot, index) => (
              <article key={shot.id} className={`shot-card${selected?.id === shot.id ? " is-active" : ""}`} onClick={() => setSelectedId(shot.id)}>
                <div className="shot-card__preview">
                  {shot.asset?.media_url && shot.asset.kind.includes("video") ? <video src={shot.asset.media_url} muted preload="metadata" /> : null}
                  {shot.asset?.media_url && !shot.asset.kind.includes("video") ? <img src={shot.asset.media_url} alt={shot.title} loading="lazy" /> : null}
                  {!shot.asset?.media_url ? <span>{String(index + 1).padStart(2, "0")}</span> : null}
                </div>
                <div className="shot-card__body"><strong>{shot.title}</strong><span>{shot.duration}s · {shot.asset?.quality_status || "待生成"}</span></div>
              </article>
            ))}
          </div>
        </section>

        <section className="mini-timeline">
          <div className="timeline-ruler"><span>00:00</span><span>00:10</span><span>00:20</span><span>00:30</span><span>00:40</span><span>00:50</span><span>01:00</span></div>
          <div className="timeline-track">
            {shots.map((shot, index) => <div key={shot.id} className={`timeline-block${shot.id === selected?.id ? " is-active" : ""}`}>{String(index + 1).padStart(2, "0")} · {shot.duration}s</div>)}
          </div>
        </section>
        {message ? <p className="studio-feedback" role="status">{message}</p> : null}
      </section>

      <aside className="studio-panel studio-right-pane">
        <div className="studio-panel__header"><div><strong>导演参数</strong><span>{selected.title}</span></div></div>
        <div className="inspector-section">
          <h3>角色与场景</h3>
          <div className="director-chip-row"><span className="director-chip is-active">主角</span><span className="director-chip">配角</span><span className="director-chip">环境角色</span></div>
          <div className="inspector-field"><label>场景</label><select defaultValue="当前场景"><option>当前场景</option></select></div>
          <div className="inspector-field"><label>道具</label><input defaultValue="核心道具 / 环境道具" /></div>
        </div>
        <div className="inspector-section">
          <h3>摄影机</h3>
          <div className="inspector-field"><label>构图</label><select defaultValue="三分构图"><option>三分构图</option><option>中心构图</option><option>对称构图</option></select></div>
          <div className="inspector-field"><label>景别</label><select defaultValue="中近景"><option>远景</option><option>全景</option><option>中景</option><option>中近景</option><option>特写</option></select></div>
          <div className="camera-buttons">{CAMERA.map((item) => <button key={item} type="button" className={camera === item ? "is-active" : ""} onClick={() => setCamera(item)}>{item}</button>)}</div>
          <div className="inspector-field"><label>运动强度</label><input type="range" min="0" max="100" defaultValue="65" /></div>
          <div className="inspector-field"><label>焦段</label><select defaultValue="35mm"><option>24mm</option><option>35mm</option><option>50mm</option><option>85mm</option></select></div>
          <div className="inspector-field"><label>光线</label><select defaultValue="电影逆光"><option>电影逆光</option><option>柔光</option><option>硬质侧光</option><option>环境自然光</option></select></div>
        </div>
        <div className="inspector-section">
          <h3>情绪</h3>
          <div className="director-chip-row"><span className="director-chip is-active">紧张</span><span className="director-chip">压迫</span><span className="director-chip">危机</span></div>
          <div className="inspector-field"><label>执行提示词</label><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} /></div>
        </div>
        <div className="inspector-section">
          <h3><SafetyCertificateOutlined /> QC 提示</h3>
          <div className="qc-grid">
            <div className="qc-item is-ok">角色一致性 ✓</div>
            <div className="qc-item is-ok">构图稳定性 ✓</div>
            <div className={selectedAsset?.quality_status === "failed" ? "qc-item is-warn" : "qc-item is-ok"}>画面质量 {selectedAsset?.quality_status || "待检测"}</div>
            <div className="qc-item is-ok">运动连贯性 ✓</div>
          </div>
        </div>
      </aside>
    </div>
  );
};

export default StoryboardDirectorWorkspace;
