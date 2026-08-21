/**
 * Production Studio v2.0（AI 影视生产控制台）。
 * GPT v2.0 布局方案：四层信息架构（总览 → 执行 → 资产 → 决策），全中文。
 */

import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert, Button, Card, Col, Drawer, Input, Progress, Row, Space, Statistic, Tag, Typography,
} from "antd";
import {
  ApartmentOutlined, BarChartOutlined, BulbOutlined, CrownOutlined, DashboardOutlined,
  ExperimentOutlined, RocketOutlined, SafetyCertificateOutlined, TeamOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

import {
  v1AdvanceProject, v1CeoDecide, v1Certify, v1CinemaScore, v1CreateProject,
  v1EvolutionDirect, v1Projects, v1SeasonPlan, v1ShotBible, v1Shots, v1StartProject, v1Workers,
} from "@/api/productionStudioV1";
import { teamFlow, teamStats } from "@/api/team";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;

// 状态机阶段（全中文）
const STAGES: Array<[string, string]> = [
  ["init", "初始化"], ["script_analysis", "剧本规划"], ["character_design", "角色设计"],
  ["world_building", "世界观"], ["storyboard", "分镜设计"], ["keyframe_generation", "关键帧"],
  ["video_generation", "视频生成"], ["quality_check", "质检"], ["editing", "剪辑"],
  ["audio", "配音"], ["final_export", "输出"],
];
const STAGE_INDEX: Record<string, number> = Object.fromEntries(STAGES.map((s, i) => [s[0], i]));

// AI 制作团队（全中文）
const AGENTS = [
  { key: "writer", label: "编剧", desc: "剧本与对白" },
  { key: "actor", label: "演员", desc: "角色情绪与表演" },
  { key: "camera", label: "摄影", desc: "镜头语言" },
  { key: "motion", label: "动作", desc: "动作与运镜" },
  { key: "art", label: "美术", desc: "画面与资产" },
  { key: "editor", label: "剪辑", desc: "成片剪辑" },
  { key: "sound", label: "声音", desc: "配音与音效" },
];

const PAGE_COLORS = {
  bg: "#0B1020",
  card: "#111827",
  border: "rgba(255,255,255,.08)",
  text1: "#F8FAFC",
  text2: "#CBD5E1",
  text3: "#64748B",
  green: "#22C55E",
  blue: "#3B82F6",
  purple: "#A855F7",
  red: "#EF4444",
  amber: "#F59E0B",
};

const ProductionStudioV1: React.FC = () => {
  const [searchParams] = useSearchParams();
  const episodeParam = searchParams.get("episode");

  const [projects, setProjects] = useState<Array<Record<string, unknown>>>([]);
  const [workers, setWorkers] = useState<Array<Record<string, unknown>>>([]);
  const [selected, setSelected] = useState<string>("");
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [name, setName] = useState("归墟觉醒");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drawer, setDrawer] = useState<Record<string, unknown> | null>(null);
  const [flow, setFlow] = useState<Record<string, unknown> | null>(null);
  const [teamStatsData, setTeamStatsData] = useState<Record<string, unknown> | null>(null);
  const [shotFilter, setShotFilter] = useState("all");
  const [shotPage, setShotPage] = useState(1);
  const [shots, setShots] = useState<Array<{ id: string; provider: string; thumb: string; duration_s: string }>>([]);

  // 演示面板数据
  const [shotBible, setShotBible] = useState<Record<string, unknown> | null>(null);
  const [season, setSeason] = useState<Record<string, unknown> | null>(null);
  const [cinema, setCinema] = useState<Record<string, unknown> | null>(null);
  const [evolution, setEvolution] = useState<Record<string, unknown> | null>(null);
  const [ceo, setCeo] = useState<Record<string, unknown> | null>(null);
  const [cert, setCert] = useState<Record<string, unknown> | null>(null);
  const [phaseE, setPhaseE] = useState<Record<string, unknown> | null>(null);

  const load = async () => {
    const [p, w] = await Promise.all([v1Projects(), v1Workers()]).catch((e: unknown) => {
      setError(userMessage(e));
      return [null, null];
    });
    setProjects((p?.projects ?? []) as unknown as Array<Record<string, unknown>>);
    setWorkers(w?.workers ?? []);
    const [f, s] = await Promise.all([teamFlow("guixu2"), teamStats()]).catch(() => [null, null]);
    setFlow(f as unknown as Record<string, unknown> | null);
    setTeamStatsData(s as unknown as Record<string, unknown> | null);
  };

  useEffect(() => {
    load();
    v1Shots().then((r) => setShots(r.shots)).catch(() => undefined);
    fetch("/api/production-pilot/phase-e").then((r) => r.json()).then((d) => setPhaseE(d)).catch(() => undefined);
    // SSE 实时推送（真实时）
    const es = new EventSource("/api/production/events");
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "production_status") setStatus(data.status);
      } catch { /* ignore */ }
    };
    const timer = setInterval(() => { load(); }, 15000);
    return () => { es.close(); clearInterval(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async (fn: () => Promise<unknown>, label: string) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(`${label}: ${userMessage(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const onCreate = () => run(async () => {
    const p = await v1CreateProject({ name, duration_seconds: 300 });
    await load();
    setSelected(p.id);
    setStatus(await v1StartProject(p.id));
  }, "创建项目");

  const onAdvance = () => selected && run(async () => {
    setStatus(await v1AdvanceProject(selected, { result: {} }));
  }, "推进");

  const onDemo = () => run(async () => {
    const [bible, sp, cs, evo, c, cf] = await Promise.all([
      v1ShotBible({ story: "陈夜进入地下城", characters: ["陈夜"], emotion: "好奇", mood: "史诗", action_type: "探索" }),
      v1SeasonPlan({ title: "归墟", content: "陈夜发现地下入口", characters: ["陈夜"], locations: ["地下城"], episodes: 2, shots_per_episode: 6 }),
      v1CinemaScore({ visual_quality: 92, character: 96, motion: 87, cinematic_language: 90, emotion: 85, continuity: 84 }),
      v1EvolutionDirect("hero_intro"),
      v1CeoDecide({ options: ["批量生产", "单集精修"] }),
      v1Certify({ style: "cinematic", episodes: 2, shots: 12 }),
    ]);
    setShotBible(bible);
    setSeason(sp);
    setCinema(cs);
    setEvolution(evo);
    setCeo(c);
    setCert(cf);
  }, "演示面板");

  const onSelect = (id: string) => {
    setSelected(id);
    v1AdvanceProject(id, { result: {} }).then((s) => setStatus(s)).catch(() => undefined);
  };

  const stateIdx = status ? STAGE_INDEX[(status.current as string) ?? ""] ?? 0 : 0;
  const byStatus = (teamStatsData?.by_status as Record<string, number>) ?? {};
  const assignments = (teamStatsData?.assignments as number) ?? 0;
  const doneCount = byStatus.done ?? 0;
  const activeCount = byStatus.in_progress ?? 0;
  const blockedCount = byStatus.blocked ?? 0;
  const totalShots = (season?.total_shots as number) ?? 100;
  const progressPct = assignments ? Math.round((doneCount / assignments) * 100) : ((status?.progress as number) ?? 0);

  const currentStageLabel = status ? STAGES[Math.max(0, stateIdx)]?.[1] ?? status.current as string : "未启动";

  return (
    <div className="page-container" style={{ background: PAGE_COLORS.bg, minHeight: "100vh", padding: 16, color: PAGE_COLORS.text1 }}>
      {/* 头部 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <Title level={3} style={{ marginBottom: 0, color: PAGE_COLORS.text1 }}>
            <CrownOutlined /> AI 影视生产控制台
          </Title>
          <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>Production Studio v2.0 · 总览 → 执行 → 资产 → 决策</Text>
        </div>
        <Space>
          <Tag style={{ background: PAGE_COLORS.card, color: PAGE_COLORS.green, borderColor: PAGE_COLORS.green }}>v2.0</Tag>
          <Tag style={{ background: PAGE_COLORS.card, color: PAGE_COLORS.blue, borderColor: PAGE_COLORS.blue }}>AI 影视工厂</Tag>
        </Space>
      </div>

            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 12, padding: "8px 12px", background: PAGE_COLORS.card, border: `1px solid ${PAGE_COLORS.border}`, borderRadius: 6 }}>
        {phaseE && (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 12, padding: "8px 12px", background: PAGE_COLORS.card, border: `1px solid ${PAGE_COLORS.border}`, borderRadius: 6 }}>
          <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>生产智能状态（候选，非自动切换）：</Text>
          <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>最佳导演 <Text style={{ color: PAGE_COLORS.text1 }}>{String(((phaseE.recommendation as Record<string, unknown>)?.best_director as string) ?? "—")}</Text></Text>
          <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>最佳提示词 <Text style={{ color: PAGE_COLORS.text1 }}>{String(((phaseE.recommendation as Record<string, unknown>)?.best_prompt as string) ?? "—")}（候选）</Text></Text>
          <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>最佳镜头DNA <Text style={{ color: PAGE_COLORS.text1 }}>{String(((phaseE.recommendation as Record<string, unknown>)?.recommended_shot_dna as string) ?? "—")}</Text></Text>
          <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>DT 单镜 <Text style={{ color: PAGE_COLORS.text1 }}>{(phaseE.E4_dt_calibration as Record<string, unknown>)?.mean_s as number ?? "—"}s</Text></Text>
          <Tag style={{ background: "#A855F722", color: PAGE_COLORS.purple, border: 0 }}>候选</Tag>
        </div>
      )}
<Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>等待我处理：</Text>
        <Tag style={{ cursor: "pointer", background: shotFilter === "review" ? "#A855F722" : "transparent", color: PAGE_COLORS.purple, border: `1px solid ${PAGE_COLORS.border}` }} onClick={() => { setShotFilter("all"); }}>待审批 {(byStatus.review ?? 0) + (byStatus.escalated ?? 0)}</Tag>
        <Tag style={{ cursor: "pointer", color: PAGE_COLORS.red, border: `1px solid ${PAGE_COLORS.border}` }} onClick={() => { setShotFilter("failed"); setShotPage(1); }}>阻塞 {byStatus.blocked ?? 0}</Tag>
        <Tag style={{ cursor: "pointer", color: PAGE_COLORS.red, border: `1px solid ${PAGE_COLORS.border}` }} onClick={() => { setShotFilter("failed"); setShotPage(1); }}>失败镜头 {byStatus.failed ?? 0}</Tag>
        <Tag style={{ cursor: "pointer", color: PAGE_COLORS.amber, border: `1px solid ${PAGE_COLORS.border}` }} onClick={() => { setShotFilter("rework"); setShotPage(1); }}>返工 {byStatus.rework ?? 0}</Tag>
      </div>

{episodeParam && (
        <Alert style={{ marginBottom: 12 }} type="info" showIcon
               message={`已从工作流定位到 ${episodeParam}`}
               description="该集生产状态可在此查看；点击下方镜头或工作流继续流转。" />
      )}

      {/* ① 生产总览（第一优先） */}
      <Card size="small" title={<span style={{ color: PAGE_COLORS.text1, fontSize: 13 }}><DashboardOutlined /> 生产总览</span>}
            style={{ marginBottom: 12, background: PAGE_COLORS.card, borderColor: PAGE_COLORS.border }}>
        <Row gutter={[16, 16]}>
          <Col span={12} md={6}>
            <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>当前项目</span>}
                       value={selected ? projects.find((p) => p.id === selected)?.name as string ?? "已选择" : "未选择"}
                       valueStyle={{ color: PAGE_COLORS.text1, fontSize: 18 }} />
          </Col>
          <Col span={12} md={6}>
            <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>生产阶段</span>}
                       value={currentStageLabel}
                       valueStyle={{ color: PAGE_COLORS.blue, fontSize: 18 }} />
          </Col>
          <Col span={12} md={6}>
            <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>完成进度</span>}
                       value={progressPct}
                       suffix="%" valueStyle={{ color: PAGE_COLORS.green, fontSize: 18 }} />
          </Col>
          <Col span={12} md={6}>
            <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>健康状态</span>}
                       value={blockedCount > 0 ? "有阻塞" : "良好"}
                       valueStyle={{ color: blockedCount > 0 ? PAGE_COLORS.red : PAGE_COLORS.green, fontSize: 18 }} />
          </Col>
        </Row>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 12 }}>
          <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>GPU 节点：<Text style={{ color: PAGE_COLORS.blue }}>{workers.length}</Text></Text>
          <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>已完成任务：<Text style={{ color: PAGE_COLORS.green }}>{doneCount}</Text></Text>
          <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>待审批：<Text style={{ color: PAGE_COLORS.purple }}>{blockedCount}</Text></Text>
          <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>风险：<Text style={{ color: blockedCount > 0 ? PAGE_COLORS.red : PAGE_COLORS.green }}>{blockedCount > 0 ? "需关注" : "低"}</Text></Text>
        </div>
      </Card>

      {/* ② 项目总控（执行层第一） */}
      <Card size="small" title={<span style={{ color: PAGE_COLORS.text1, fontSize: 13 }}><RocketOutlined /> 项目总控</span>}
            style={{ marginBottom: 12, background: PAGE_COLORS.card, borderColor: PAGE_COLORS.border }}>
        <Space wrap style={{ marginBottom: 8 }}>
          <Input value={name} onChange={(e) => setName(e.target.value)}
                 style={{ width: 180, background: PAGE_COLORS.bg, borderColor: PAGE_COLORS.border, color: PAGE_COLORS.text1 }} />
          <Button type="primary" loading={busy} onClick={onCreate}>创建并启动</Button>
          <Button loading={busy} disabled={!selected} onClick={onAdvance}>推进阶段</Button>
          <Button loading={busy} onClick={onDemo}>演示面板</Button>
        </Space>
        <Space wrap>
          <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>项目：</Text>
          {projects.map((p) => (
            <Tag key={String(p.id)} color={selected === String(p.id) ? "blue" : "default"} style={{ cursor: "pointer" }}
                 onClick={() => onSelect(String(p.id))}>{p.name as string} · {p.state as string} · {p.progress as number}%</Tag>
          ))}
        </Space>
        {status && (
          <div style={{ marginTop: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: PAGE_COLORS.text3, marginBottom: 4 }}>
              <span>生产阶段：{currentStageLabel}</span>
              <span>{status.progress as number}% · 完成 {(status.completed as number) ?? 0} · 失败 {(status.failed as number) ?? 0}</span>
            </div>
            <Progress percent={status.progress as number} strokeColor={PAGE_COLORS.blue} trailColor="#1E293B" size={{ height: 8 }} />
            <Space wrap style={{ marginTop: 6 }}>
              {STAGES.map(([key, label], i) => (
                <Tag key={key} style={{
                  background: i < stateIdx ? "#22C55E22" : i === stateIdx ? "#3B82F633" : PAGE_COLORS.card,
                  color: i < stateIdx ? PAGE_COLORS.green : i === stateIdx ? PAGE_COLORS.blue : PAGE_COLORS.text3,
                  border: i <= stateIdx ? `1px solid ${i === stateIdx ? PAGE_COLORS.blue : PAGE_COLORS.green}` : `1px solid ${PAGE_COLORS.border}`,
                }}>{label}</Tag>
              ))}
            </Space>
          </div>
        )}
      </Card>

      {/* ③ 集数进度（执行层第二） */}
      <Card size="small" title={<span style={{ color: PAGE_COLORS.text1, fontSize: 13 }}><ApartmentOutlined /> 集数进度</span>}
            style={{ marginBottom: 12, background: PAGE_COLORS.card, borderColor: PAGE_COLORS.border }}>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ minWidth: 220 }}>
            <div style={{ color: PAGE_COLORS.text3, fontSize: 12, marginBottom: 4 }}>《归墟第二部》 第一季 · 共 {totalShots} 镜</div>
            <Progress percent={progressPct} strokeColor={PAGE_COLORS.green} trailColor="#1E293B" size={{ height: 10 }} />
          </div>
          <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>集数</span>} value={100} valueStyle={{ color: PAGE_COLORS.text1 }} />
          <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>已完成</span>} value={doneCount} valueStyle={{ color: PAGE_COLORS.green }} />
          <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>进行中</span>} value={activeCount} valueStyle={{ color: PAGE_COLORS.blue }} />
          <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>阻塞</span>} value={blockedCount} valueStyle={{ color: PAGE_COLORS.red }} />
          <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>待审批</span>} value={(byStatus.review ?? 0) + (byStatus.escalated ?? 0)} valueStyle={{ color: PAGE_COLORS.purple }} />
          <Statistic title={<span style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>返工</span>} value={byStatus.rework ?? 0} valueStyle={{ color: PAGE_COLORS.amber }} />
          <Space wrap style={{ marginLeft: "auto" }}>
            <a href="#/workflow" style={{ color: PAGE_COLORS.blue, fontSize: 12 }}>工作流 →</a>
            <a href="#/digital-twin" style={{ color: PAGE_COLORS.blue, fontSize: 12 }}>数字孪生 →</a>
            <a href="#/command-center" style={{ color: PAGE_COLORS.blue, fontSize: 12 }}>指挥中心 →</a>
            <a href="#/knowledge-graph" style={{ color: PAGE_COLORS.blue, fontSize: 12 }}>知识图谱 →</a>
          </Space>
        </div>
        <div style={{ marginTop: 8 }}>
          <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>最近集：</Text>
          {(flow?.episodes as Array<Record<string, unknown>>)?.slice(0, 6).map((ep: Record<string, unknown>) => (
            <Tag key={ep.episode_id as string} style={{ cursor: "pointer", background: PAGE_COLORS.card, color: PAGE_COLORS.text1, border: 0 }}
                 onClick={() => { window.location.hash = "#/workflow"; }}>
              {ep.episode_id as string} · 完成 {ep.stages ? Object.values(ep.stages as Record<string, unknown>).filter((s) => (s as Record<string, unknown>).status === "done").length : 0}/9
            </Tag>
          ))}
        </div>
      </Card>

      {/* ④ AI 制作团队（执行层第三） */}
      <Card size="small" title={<span style={{ color: PAGE_COLORS.text1, fontSize: 13 }}><TeamOutlined /> AI 制作团队</span>}
            style={{ marginBottom: 12, background: PAGE_COLORS.card, borderColor: PAGE_COLORS.border }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
          {AGENTS.map((a, i) => {
            const running = i === stateIdx % AGENTS.length;
            const done = i < stateIdx % AGENTS.length || (status && (status.completed as number) > i);
            const stateText = done ? "已完成" : running ? "运行中" : "等待中";
            const stateColor = done ? PAGE_COLORS.green : running ? PAGE_COLORS.blue : PAGE_COLORS.amber;
            return (
              <div key={a.key} style={{ background: PAGE_COLORS.bg, border: `1px solid ${running ? PAGE_COLORS.blue : PAGE_COLORS.border}`, borderRadius: 6, padding: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <Text style={{ color: PAGE_COLORS.text1, fontSize: 12 }}>{a.label}</Text>
                  <Tag color={done ? "green" : running ? "blue" : "warning"} style={{ margin: 0, fontSize: 10 }}>{stateText}</Tag>
                </div>
                <div style={{ fontSize: 10, color: PAGE_COLORS.text3, marginTop: 4 }}>
                  {a.desc} · {running ? `当前阶段：${currentStageLabel}` : done ? "输出：已交付" : "等待依赖"}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* ⑤ 镜头墙（资产层） */}
      <Card size="small" title={<span style={{ color: PAGE_COLORS.text1, fontSize: 13 }}><BarChartOutlined /> 镜头墙</span>}
            style={{ marginBottom: 12, background: PAGE_COLORS.card, borderColor: PAGE_COLORS.border }}
            extra={
              <Space>
                {["all", "failed", "rework", "best"].map((f) => (
                  <Tag key={f} style={{ cursor: "pointer", background: shotFilter === f ? "#3B82F633" : PAGE_COLORS.card, color: shotFilter === f ? PAGE_COLORS.blue : PAGE_COLORS.text3, border: shotFilter === f ? `1px solid ${PAGE_COLORS.blue}` : `1px solid ${PAGE_COLORS.border}` }}
                       onClick={() => { setShotFilter(f); setShotPage(1); }}>{f === "all" ? "全部" : f === "failed" ? "失败" : f === "rework" ? "返工" : "最佳"}</Tag>
                ))}
              </Space>
            }>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 8 }}>
          {(() => {
            let list = shots.filter((s) => shotFilter === "all" || (shotFilter === "best" && s.provider === "MiniMaxH3"));
            const pageSize = 12;
            const start = (shotPage - 1) * pageSize;
            return list.slice(start, start + pageSize).map((s) => (
            <div key={s.id} style={{ background: PAGE_COLORS.bg, border: `1px solid ${PAGE_COLORS.border}`, borderRadius: 6, padding: 8, cursor: "pointer" }}
                 title={s.id} onClick={() => {
                   const ep = s.id.match(/^(EP\d{3})/)?.[1];
                   if (ep) { window.location.hash = `#/workflow?episode=${ep}`; }
                   else { setDrawer({ shot: s.id, provider: s.provider, duration: s.duration_s, note: "真实产物在 outputs/（Wan2.2 / MiniMaxH3）" }); }
                 }}>
              {s.thumb ? (
                <img src={s.thumb} alt={s.id} style={{ width: "100%", height: 50, objectFit: "cover", borderRadius: 4 }} />
              ) : (
                <div style={{ height: 50, background: "linear-gradient(135deg,#1E293B,#0F172A)", borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", color: "#475569", fontSize: 20 }}>🎬</div>
              )}
              <div style={{ fontSize: 11, color: PAGE_COLORS.text1, marginTop: 4 }}>{s.id}</div>
              <div style={{ fontSize: 10, color: PAGE_COLORS.text3 }}>{s.provider} · {s.duration_s}</div>
            </div>
          ));
        })()}
          <div style={{ gridColumn: "1 / -1", textAlign: "center" }}>
            {shotPage > 1 && <Tag style={{ cursor: "pointer", background: PAGE_COLORS.card, color: PAGE_COLORS.text3, border: 0 }} onClick={() => setShotPage(shotPage - 1)}>← 上一页</Tag>}
            <Tag style={{ background: PAGE_COLORS.card, color: PAGE_COLORS.text3, border: 0 }}>第 {shotPage} 页</Tag>
            {shots.length > shotPage * 12 && <Tag style={{ cursor: "pointer", background: PAGE_COLORS.card, color: PAGE_COLORS.text3, border: 0 }} onClick={() => setShotPage(shotPage + 1)}>下一页 →</Tag>}
          </div>
        </div>
      </Card>

      {/* ⑥ 制作质量 + ⑦ 导演经验（资产层） */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={12}>
          <Card size="small" title={<span style={{ color: PAGE_COLORS.text1, fontSize: 13 }}><SafetyCertificateOutlined /> 制作质量</span>}
                style={{ background: PAGE_COLORS.card, borderColor: PAGE_COLORS.border, height: "100%" }}>
            {cinema && (
              <div style={{ marginBottom: 8 }}>
                <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>制作评分：</Text>
                <Tag color="gold">{String(cinema.score)}</Tag>
                <Tag color="blue">{String(cinema.level)}</Tag>
                <Tag color="green">{String(cinema.recommendation)}</Tag>
              </div>
            )}
            {cert && (
              <div style={{ marginBottom: 8 }}>
                <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>认证等级：</Text>
                <Tag color={String(cert.certificate) === "S" ? "gold" : "blue"}>{String(cert.certificate)} 级</Tag>
                <Tag>{(cert.level as string)}</Tag>
                <Text style={{ color: PAGE_COLORS.text1, fontSize: 12 }}> 评分 {String(cert.score)}</Text>
              </div>
            )}
            <div style={{ marginTop: 8 }}>
              <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>五维质量：</Text>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 4, fontSize: 12 }}>
                <span style={{ color: PAGE_COLORS.text2 }}>综合 <Text style={{ color: PAGE_COLORS.text1 }}>{String((cinema?.detail as Record<string, { value: number }>)?.visual_quality?.value ?? 0)}</Text></span>
                <span style={{ color: PAGE_COLORS.text2 }}>角色一致性 <Text style={{ color: PAGE_COLORS.text1 }}>{String((cinema?.detail as Record<string, { value: number }>)?.character?.value ?? 0)}</Text></span>
                <span style={{ color: PAGE_COLORS.text2 }}>画面质量 <Text style={{ color: PAGE_COLORS.text1 }}>{String((cinema?.detail as Record<string, { value: number }>)?.visual_quality?.value ?? 0)}</Text></span>
                <span style={{ color: PAGE_COLORS.text2 }}>动作稳定 <Text style={{ color: PAGE_COLORS.text1 }}>{String((cinema?.detail as Record<string, { value: number }>)?.motion?.value ?? 0)}</Text></span>
                <span style={{ color: PAGE_COLORS.text2 }}>时间一致性 <Text style={{ color: PAGE_COLORS.text1 }}>{String((cinema?.detail as Record<string, { value: number }>)?.continuity?.value ?? 0)}</Text></span>
              </div>
            </div>
            <div style={{ marginTop: 8 }}>
              <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>季镜头数：</Text>
              <Tag>{(season?.total_shots as number) ?? 0} 镜</Tag>
              <Tag>已完成 {doneCount}</Tag>
            </div>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title={<span style={{ color: PAGE_COLORS.text1, fontSize: 13 }}><ExperimentOutlined /> 导演经验</span>}
                style={{ background: PAGE_COLORS.card, borderColor: PAGE_COLORS.border, height: "100%" }}>
            {evolution && (
              <div>
                <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>最佳方案（英雄登场）：</Text>
                <Tag>评分 {String(evolution.best_score)}</Tag>
                <div style={{ marginTop: 4 }}>
                  <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>推荐：{(evolution.solution as Record<string, unknown>)?.camera as string ?? "待定"}</Text>
                </div>
              </div>
            )}
            {!evolution && <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>点击「演示面板」加载导演经验数据</Text>}
          </Card>
        </Col>
      </Row>

      {/* ⑧ AI 制片建议（决策层） */}
      <Card size="small" title={<span style={{ color: PAGE_COLORS.text1, fontSize: 13 }}><BulbOutlined /> AI 制片建议</span>}
            style={{ marginBottom: 12, background: PAGE_COLORS.card, borderColor: PAGE_COLORS.border }}>
        <Row gutter={[12, 12]}>
          <Col span={12} md={8}>
            <div style={{ background: PAGE_COLORS.bg, border: `1px solid ${PAGE_COLORS.border}`, borderRadius: 6, padding: 10, height: "100%" }}>
              <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>今日建议</Text>
              <div style={{ fontSize: 12, color: PAGE_COLORS.text1, marginTop: 6, lineHeight: 1.8 }}>
                <div>① 生产进度 {progressPct}%，可继续排产</div>
                <div>② 待审批 {byStatus.waiting ?? 0} 项，建议处理</div>
                <div>③ 阻塞 {blockedCount} 项，需人工介入</div>
              </div>
            </div>
          </Col>
          <Col span={12} md={8}>
            <div style={{ background: PAGE_COLORS.bg, border: `1px solid ${PAGE_COLORS.border}`, borderRadius: 6, padding: 10, height: "100%" }}>
              <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>CEO 决策</Text>
              {ceo ? (
                <div style={{ fontSize: 12, color: PAGE_COLORS.text1, marginTop: 6 }}>
                  <div>项目：{(ceo.project as Record<string, unknown>)?.name as string ?? ""}</div>
                  <div>规划：{(ceo.project as Record<string, unknown>)?.episodes as number ?? 0} 集</div>
                </div>
              ) : (
                <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>点击「演示面板」加载</Text>
              )}
            </div>
          </Col>
          <Col span={24} md={8}>
            <div style={{ background: PAGE_COLORS.bg, border: `1px solid ${PAGE_COLORS.border}`, borderRadius: 6, padding: 10, height: "100%" }}>
              <Text style={{ color: PAGE_COLORS.text2, fontSize: 12 }}>基础设施</Text>
              <div style={{ marginTop: 6 }}>
                <Text style={{ color: PAGE_COLORS.text3, fontSize: 12 }}>GPU 节点：</Text>
                {workers.map((w) => (
                  <Tag key={w.id as string} color="green">{w.id as string} · {(w.models as string[])?.join("/")}</Tag>
                ))}
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: PAGE_COLORS.text3 }}>
                Phase 1-9 生产能力：制片大脑 · 影视团队 · 一致性 · 进化 · 平台 · 基础设施 ✅
              </div>
            </div>
          </Col>
        </Row>
      </Card>

      <Drawer open={!!drawer} onClose={() => setDrawer(null)} width={420}
              title="镜头圣经 2.0（影视团队协作）"
              styles={{ body: { background: PAGE_COLORS.bg, color: PAGE_COLORS.text1 }, header: { background: PAGE_COLORS.bg, color: PAGE_COLORS.text1 } }}>
        {drawer && <pre style={{ color: PAGE_COLORS.text1, fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(drawer, null, 2)}</pre>}
      </Drawer>

      {error ? <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} /> : null}
    </div>
  );
};

export default ProductionStudioV1;