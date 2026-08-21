import React, { useMemo, useState } from "react";
import {
  AudioOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";

import { api } from "@/api/jobs";
import { userMessage } from "@/api/client";
import { useCharacterStore } from "@/state/characterStore";
import { jobStoreActions, useJobStore } from "@/state/jobStore";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { StageKey } from "@/workbench/types";
import LocalStatusStrip from "@/studio/components/LocalStatusStrip";
import PipelineStep from "@/studio/components/PipelineStep";
import TaskQueuePanel from "@/studio/components/TaskQueuePanel";

const STAGE_GROUPS: Array<{ title: string; description: string; keys: StageKey[]; icon: React.ReactNode }> = [
  { title: "导入小说/剧本", description: "TXT / Markdown / Fountain，本地读取与解析", keys: ["import"], icon: <FileTextOutlined /> },
  { title: "AI 拆解角色与场景", description: "故事结构、角色设定与资产提取", keys: ["story", "character"], icon: <TeamOutlined /> },
  { title: "批量分镜", description: "镜头拆分、景别与镜头语言建议", keys: ["storyboard"], icon: <VideoCameraOutlined /> },
  { title: "关键帧 / 视频生成", description: "FLUX 关键帧 + Wan / H3 视频生成", keys: ["keyframe", "video"], icon: <PlayCircleOutlined /> },
  { title: "配音与字幕", description: "CosyVoice / TTS、字幕与音频轨道", keys: ["audio"], icon: <AudioOutlined /> },
  { title: "质检与导出", description: "合成、QC 门禁、版本化成片导出", keys: ["compose", "export"], icon: <SafetyCertificateOutlined /> },
];

function stageStatus(snapshot: ReturnType<typeof useWorkspaceStore.getState>["snapshot"], keys: StageKey[]) {
  if (!snapshot) return { status: "waiting" as const, progress: 0 };
  const stages = keys.map((key) => snapshot.stages.find((stage) => stage.stage_key === key)).filter(Boolean);
  if (stages.length && stages.every((stage) => stage?.status === "completed")) return { status: "completed" as const, progress: 1 };
  const running = stages.find((stage) => stage?.status === "running" || stage?.status === "queued" || stage?.progress);
  if (running) return { status: "running" as const, progress: running.progress || 0 };
  return { status: "waiting" as const, progress: 0 };
}

const ProjectCockpit: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const workspaceProjectId = useWorkspaceStore((state) => state.projectId);
  const jobStore = useJobStore();
  const parseStory = useStoryStore((state) => state.parseStory);
  const [file, setFile] = useState<File | null>(null);
  const [uploadedPath, setUploadedPath] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [healthText, setHealthText] = useState<string>("");
  const projectId = snapshot?.project_id || workspaceProjectId || "default";

  const recentArtifacts = useMemo(() => jobStore.recentIds
    .map((id) => jobStore.jobs.get(id))
    .filter(Boolean)
    .flatMap((job) => job?.artifacts ?? [])
    .filter((artifact) => Boolean(artifact.media_url))
    .slice(0, 9), [jobStore.jobs, jobStore.recentIds]);

  const prepareInput = async (): Promise<string | null> => {
    if (uploadedPath) return uploadedPath;
    if (!file) {
      setMessage("请选择小说或剧本文件");
      return null;
    }
    const text = await file.text();
    const uploaded = await api.uploadInput(file, projectId);
    await parseStory(text, projectId);
    const storyError = useStoryStore.getState().parseError;
    if (storyError) throw new Error(storyError);
    await useCharacterStore.getState().extractFromText({ text, novel_id: projectId });
    const characterError = useCharacterStore.getState().error;
    if (characterError) throw new Error(characterError);
    setUploadedPath(uploaded.path);
    return uploaded.path;
  };

  const startOneClick = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const inputPath = await prepareInput();
      if (!inputPath) return;
      const job = await jobStoreActions().createJob({
        project_id: projectId,
        input_path: inputPath,
        mode: "automatic",
        shot_duration: 5,
        width: 1080,
        height: 1920,
        fps: 24,
        options: { style: "anime", local_first: true },
      });
      jobStoreActions().subscribeSSE(job.id);
      setMessage(`一键生产已启动 · 任务 ${job.id.slice(0, 8)}`);
    } catch (error) {
      setMessage(userMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const runHealth = async () => {
    try {
      const result = await api.health();
      setHealthText(`服务正常 · ${result.version}`);
    } catch (error) {
      setHealthText(userMessage(error));
    }
  };

  return (
    <div className="studio-workspace project-cockpit">
      <section className="studio-project-rail">
        <div className="project-cover"><span>归</span></div>
        <h2>{snapshot?.title || "当前项目"}</h2>
        <p>{snapshot?.source_path || "本地项目库"}</p>
        <div className="project-tree-static">
          <strong>第 1 集</strong>
          <span>场景 01 · 建立镜头</span>
          <span className="is-selected">镜头 02 · 主角登场</span>
          <span>场景 02 · 冲突升级</span>
          <span>场景 03 · 高潮与悬念</span>
        </div>
        <div className="project-rail__footer">本地项目 · 自动保存</div>
      </section>

      <section className="cockpit-center">
        <header className="studio-workspace__header">
          <div>
            <h1>一站式 · 一键成片</h1>
            <p>本地优先 / 一站式 / 可观察 / 可回退</p>
          </div>
          <button type="button" className="studio-secondary-button" onClick={() => void runHealth()}>运行环境预检</button>
        </header>

        <div className="pipeline-grid">
          {STAGE_GROUPS.map((group, index) => {
            const state = stageStatus(snapshot, group.keys);
            return <PipelineStep key={group.title} index={index + 1} {...group} {...state} />;
          })}
        </div>

        <div className="one-click-zone">
          <label className="file-drop-control">
            <input type="file" accept=".txt,.md,.xml,.fountain" onChange={(event) => { setFile(event.target.files?.[0] || null); setUploadedPath(null); }} />
            <span>{file ? file.name : "选择小说 / 剧本文件"}</span>
          </label>
          <button type="button" className="studio-primary-button one-click-button" disabled={busy} onClick={() => void startOneClick()}>
            <PlayCircleOutlined /> {busy ? "正在启动本地生产…" : "开始一键生成"}
          </button>
          {message ? <p className="studio-feedback" role="status">{message}</p> : null}
        </div>

        <LocalStatusStrip snapshot={snapshot} healthText={healthText} />

        <section className="studio-panel media-rail-panel">
          <div className="studio-panel__header"><div><strong>时间线预览</strong><span>最近生成镜头与产物</span></div></div>
          <div className="media-rail">
            {recentArtifacts.length ? recentArtifacts.map((artifact, index) => (
              <article key={`${artifact.path}-${index}`} className="media-card">
                {artifact.kind === "image" ? <img src={artifact.media_url} alt={artifact.shot_id || "镜头"} /> : <video src={artifact.media_url} muted preload="metadata" />}
                <span>{artifact.shot_id || artifact.stage_key || `镜头 ${index + 1}`}</span>
              </article>
            )) : Array.from({ length: 8 }).map((_, index) => (
              <article key={index} className="media-card media-card--empty"><span>{String(index + 1).padStart(2, "0")} · 待生成</span></article>
            ))}
          </div>
        </section>
      </section>

      <TaskQueuePanel />
    </div>
  );
};

export default ProjectCockpit;
