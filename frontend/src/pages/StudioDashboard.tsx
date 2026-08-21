import React, { useCallback, useEffect, useState } from "react";

import {
  chainPlan,
  chainStatus,
  directorPlan,
  identityVerify,
  type ChainStatus,
  type DirectorPlanResponse,
  type ShotDirective,
} from "@/api/studio";
import { getPipelineStats, type PipelineStats } from "@/api/pipeline";

const MODE_LABELS: Record<string, string> = {
  keyframe: "关键帧起镜",
  last_frame: "末帧续接",
  reset: "换场重置",
};

const SAMPLE_SHOTS = JSON.stringify(
  [
    { id: "gx_001", location: "实验室", time_of_day: "night", image_path: "outputs/images/gx_001/frame.png", prompt_tail: "苏晚站在实验室", motion_level: "low" },
    { id: "gx_002", location: "实验室", time_of_day: "night", image_path: "outputs/images/gx_002/frame.png", prompt_tail: "警报响起", motion_level: "medium" },
    { id: "gx_003", location: "蜀地夜行公路", time_of_day: "night", image_path: "outputs/images/gx_003/frame.png", prompt_tail: "雨夜公路", motion_level: "high" },
  ],
  null,
  2
);

const StudioDashboard: React.FC = () => {
  const [stats, setStats] = useState<PipelineStats | null>(null);

  // Director Studio
  const [planText, setPlanText] = useState("");
  const [planning, setPlanning] = useState(false);
  const [plan, setPlan] = useState<DirectorPlanResponse | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);

  // Chain runtime
  const [projectId, setProjectId] = useState("归墟觉醒·天倾");
  const [shotsJson, setShotsJson] = useState(SAMPLE_SHOTS);
  const [chainLoading, setChainLoading] = useState(false);
  const [chainPlanResult, setChainPlanResult] = useState<{ links: Array<{ shot_id: string; mode: string; note: string }>; report: { by_mode: Record<string, number> } } | null>(null);
  const [chainStatusResult, setChainStatusResult] = useState<ChainStatus | null>(null);

  // Identity gate
  const [videoPath, setVideoPath] = useState("");
  const [refsJson, setRefsJson] = useState('{"suwan": [0.9, 0.1, 0.2]}');
  const [identityLoading, setIdentityLoading] = useState(false);
  const [identityResult, setIdentityResult] = useState<{ overall_verdict: string; per_character: Record<string, { frames_present: number; frames_checked: number; presence_ratio: number }> } | null>(null);

  useEffect(() => {
    getPipelineStats().then(setStats).catch(() => undefined);
  }, []);

  const runDirectorPlan = useCallback(async () => {
    setPlanning(true);
    setPlanError(null);
    try {
      const result = await directorPlan({ text: planText, novel_id: projectId, title: "导演计划" });
      setPlan(result);
    } catch (e) {
      setPlanError((e as Error).message);
    } finally {
      setPlanning(false);
    }
  }, [planText, projectId]);

  const runChainPlan = useCallback(async () => {
    setChainLoading(true);
    try {
      const shots = JSON.parse(shotsJson);
      const result = await chainPlan({ project_id: projectId, shots });
      setChainPlanResult(result);
      const status = await chainStatus(projectId);
      setChainStatusResult(status);
    } catch (e) {
      setChainPlanResult(null);
      setChainStatusResult(null);
      setPlanError((e as Error).message);
    } finally {
      setChainLoading(false);
    }
  }, [projectId, shotsJson]);

  const runIdentityVerify = useCallback(async () => {
    setIdentityLoading(true);
    try {
      const refs = JSON.parse(refsJson);
      const result = await identityVerify({ video_path: videoPath, character_references: refs });
      setIdentityResult(result);
    } catch (e) {
      setIdentityResult(null);
      setPlanError((e as Error).message);
    } finally {
      setIdentityLoading(false);
    }
  }, [videoPath, refsJson]);

  return (
    <div className="studio-dashboard" aria-label="导演工作台">
      <h2 className="studio-dashboard__title">Studio 导演工作台</h2>
      <p className="studio-dashboard__subtitle">
        Phase 10 合并能力：Director v2 分镜指令 · Chain Runtime 长视频续接 · Identity Gate 角色校验
      </p>

      <div className="studio-dashboard__grid">
        <section className="studio-card" aria-label="管线状态">
          <h3>管线模块</h3>
          {stats ? (
            <>
              <p>版本 v{stats.version}</p>
              <ul>
                {Object.entries(stats.phases)
                  .filter(([, on]) => on)
                  .map(([key]) => (
                    <li key={key}>{key}</li>
                  ))}
              </ul>
            </>
          ) : (
            <p>加载中…</p>
          )}
        </section>

        <section className="studio-card" aria-label="导演指令">
          <h3>Director v2 分镜指令</h3>
          <textarea
            aria-label="小说片段"
            value={planText}
            onChange={(e) => setPlanText(e.target.value)}
            placeholder="粘贴小说片段，生成分镜指令 JSON…"
            rows={4}
          />
          <button type="button" onClick={runDirectorPlan} disabled={planning || !planText.trim()}>
            {planning ? "生成中…" : "生成导演指令"}
          </button>
          {plan && (
            <div className="studio-card__result">
              <p>
                {plan.shots_total} 镜 / {plan.scenes} 场 / {plan.chapters} 章
              </p>
              <ul>
                {plan.directives.map((d: ShotDirective) => (
                  <li key={d.shot_id}>
                    {d.directive_id || d.shot_id} — {d.shot_intent} · {d.camera.angle}/{d.camera.distance} · 光源 {d.lighting.style ?? "natural"}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="studio-card" aria-label="长视频链">
          <h3>Chain Runtime（长视频续接）</h3>
          <label>
            项目 ID
            <input aria-label="项目 ID" value={projectId} onChange={(e) => setProjectId(e.target.value)} />
          </label>
          <textarea
            aria-label="镜头清单 JSON"
            value={shotsJson}
            onChange={(e) => setShotsJson(e.target.value)}
            rows={6}
          />
          <button type="button" onClick={runChainPlan} disabled={chainLoading}>
            {chainLoading ? "规划中…" : "规划镜头链 + 读取检查点"}
          </button>
          {chainPlanResult && (
            <div className="studio-card__result">
              <p>共 {chainPlanResult.links.length} 镜</p>
              <ul>
                {chainPlanResult.links.map((link) => (
                  <li key={link.shot_id}>
                    {link.shot_id} — {MODE_LABELS[link.mode] ?? link.mode}（{link.note}）
                  </li>
                ))}
              </ul>
              {chainStatusResult && (
                <p>
                  检查点：完成 {chainStatusResult.completed.length} / 进行中 {chainStatusResult.current || "—"} / 失败 {chainStatusResult.failed.length}
                </p>
              )}
            </div>
          )}
        </section>

        <section className="studio-card" aria-label="角色校验">
          <h3>Identity Gate（生成后角色校验）</h3>
          <input
            aria-label="视频路径"
            placeholder="outputs/videos/gx_002.mp4"
            value={videoPath}
            onChange={(e) => setVideoPath(e.target.value)}
          />
          <textarea
            aria-label="角色参考向量 JSON"
            value={refsJson}
            onChange={(e) => setRefsJson(e.target.value)}
            rows={3}
          />
          <button type="button" onClick={runIdentityVerify} disabled={identityLoading || !videoPath}>
            {identityLoading ? "校验中…" : "校验视频角色"}
          </button>
          {identityResult && (
            <div className="studio-card__result">
              <p>总体判定：{identityResult.overall_verdict === "pass" ? "通过 ✅" : "失败 ❌"}</p>
              <ul>
                {Object.entries(identityResult.per_character).map(([cid, v]) => (
                  <li key={cid}>
                    {cid} — 出现 {v.frames_present}/{v.frames_checked} 帧（{Math.round(v.presence_ratio * 100)}%）
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      {planError && <p className="studio-dashboard__error">{planError}</p>}
    </div>
  );
};

export default StudioDashboard;
