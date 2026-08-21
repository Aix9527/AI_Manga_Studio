/**
 * SOP Center（GPT 15.3-G：独立 SOP 页面）。
 *
 * 漫剧生产 SOP：剧本 → 角色/场景资产 → 分镜设计 → AI 视频生成 →
 * 剪辑包装 → 审核发布。每环节映射到系统模块与当前状态。
 */

import React, { useEffect, useState } from "react";
import { Alert, Card, Col, Progress, Row, Space, Statistic, Tag, Typography } from "antd";
import { ApartmentOutlined, BookOutlined, CameraOutlined, CheckCircleOutlined, ClusterOutlined, EditOutlined, ExperimentOutlined, VideoCameraOutlined } from "@ant-design/icons";

import { teamStats, type TeamStats } from "@/api/team";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;

const SOP_STAGES = [
  {
    key: "script", label: "剧本创作", icon: <BookOutlined />, desc: "主线/节奏/版权：开头3秒抓眼球，10秒立角色，结尾5秒反转",
    systems: ["Story Intelligence", "Episode Planner", "Writer"], module: "Story / Writer",
  },
  {
    key: "assets", label: "角色与场景资产", icon: <ClusterOutlined />, desc: "统一美术风格 + 标准化命名（林野*17岁 / 学校教室*夜晚）",
    systems: ["Character Studio v2", "World Builder", "Shot DNA Studio"], module: "Asset Studio",
  },
  {
    key: "storyboard", label: "分镜设计", icon: <CameraOutlined />, desc: "逐镜头拆解：景别/运镜/角度/光线/台词/动作；每集约18镜头",
    systems: ["Storyboard Director", "ShotDesign Compiler", "Director Council"], module: "Director OS",
  },
  {
    key: "generation", label: "AI 视频生成", icon: <VideoCameraOutlined />, desc: "资产+分镜输入模型；首尾帧固定角色；MiniMaxH3 15s 3×5s 镜头链",
    systems: ["Team Collaboration", "MiniMaxH3 Provider", "Worker Runtime"], module: "Production Pipeline",
  },
  {
    key: "editing", label: "剪辑与包装", icon: <EditOutlined />, desc: "按分镜顺序合成/调节奏；字幕/转场；调色统一",
    systems: ["Editor", "FFmpeg Composer", "Subtitles"], module: "Editor / Composer",
  },
  {
    key: "review", label: "审核与发布", icon: <CheckCircleOutlined />, desc: "内容合规 + 画面质量；人工审批门；多平台分发",
    systems: ["Quality Gate", "Identity Gate", "Command Center", "Human Approval"], module: "Governance",
  },
];

const SOPCenter: React.FC = () => {
  const [stats, setStats] = useState<TeamStats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    teamStats().then(setStats).catch((e: Error) => setError(userMessage(e)));
  }, []);

  const done = stats?.by_status?.done ?? 0;
  const total = stats?.assignments ?? 0;

  return (
    <div className="page-container" style={{ background: "#0B1020", minHeight: "100vh", padding: 16, color: "#E2E8F0" }}>
      <div className="page-header" style={{ marginBottom: 12 }}>
        <Title level={3} style={{ marginBottom: 0, color: "#E2E8F0" }}>
          <ApartmentOutlined /> SOP Center <Text style={{ color: "#94A3B8" }}>漫剧生产 SOP</Text>
        </Title>
        <Text style={{ color: "#64748B", fontSize: 12 }}>
          剧本 × 视觉 × 节奏 × 技术 四位一体：剧本 → 资产 → 分镜 → 生成 → 剪辑 → 发布
        </Text>
      </div>

      {stats && (
        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col span={6}><Card size="small" style={{ background: "#0F172A", borderColor: "#1E293B" }}><Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>生产任务</span>} value={total} valueStyle={{ color: "#E2E8F0" }} /></Card></Col>
          <Col span={6}><Card size="small" style={{ background: "#0F172A", borderColor: "#1E293B" }}><Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>已完成</span>} value={done} valueStyle={{ color: "#22C55E" }} /></Card></Col>
          <Col span={6}><Card size="small" style={{ background: "#0F172A", borderColor: "#1E293B" }}><Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>完成率</span>} value={total ? Math.round(done / total * 100) : 0} suffix="%" valueStyle={{ color: "#3B82F6" }} /></Card></Col>
          <Col span={6}><Card size="small" style={{ background: "#0F172A", borderColor: "#1E293B" }}><Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>审计</span>} value={`${(stats.audit_coverage * 100).toFixed(0)}%`} valueStyle={{ color: "#22C55E" }} /></Card></Col>
        </Row>
      )}

      <Row gutter={[12, 12]}>
        {SOP_STAGES.map((stage, i) => (
          <Col span={8} key={stage.key} style={{ marginBottom: 12 }}>
            <Card size="small" style={{ background: "#0F172A", borderColor: "#1E293B", height: "100%" }}
                  title={<span style={{ color: "#E2E8F0", fontSize: 13 }}>{i + 1}. {stage.icon} {stage.label}</span>}>
              <div style={{ color: "#94A3B8", fontSize: 12, marginBottom: 8 }}>{stage.desc}</div>
              <div style={{ fontSize: 11, color: "#64748B", marginBottom: 4 }}>
                <Text style={{ color: "#64748B" }}>系统：</Text>
                {stage.systems.map((s) => <Tag key={s} style={{ background: "#1E293B", color: "#94A3B8", border: 0, marginBottom: 2 }}>{s}</Tag>)}
              </div>
              <div style={{ fontSize: 11, color: "#3B82F6" }}>模块：{stage.module}</div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card size="small" style={{ background: "#0F172A", borderColor: "#1E293B" }}>
        <Text style={{ color: "#94A3B8", fontSize: 12 }}>
          关键建议：先小样再量产（1-2 集测试流程与质量）；重视审美与项目管理；成本控制（选择性价比模型）。
        </Text>
      </Card>

      {error ? <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} /> : null}
    </div>
  );
};

export default SOPCenter;
