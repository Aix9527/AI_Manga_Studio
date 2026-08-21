/**
 * Production Intelligence Center (Phase 13.5-B, GPT spec).
 *
 * B1 事件化仓库 → B2 分析引擎（成本/周期/导演/Prompt ROI）→ B3 智能中心
 * （Overview / Episode ROI / Risk Radar / 优化候选）→ B4 人工审批候选回流。
 * 分析不是决策者：候选必须人工审批，绝不自动修改生产资产。
 */

import React, { useEffect, useState } from "react";

import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  message,
  Progress,
  Row,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import {
  DashboardOutlined,
  FundOutlined,
  RadarChartOutlined,
  RocketOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

import {
  applyAnalyticsCandidate,
  costIntelligence,
  cycleIntelligence,
  directorIntelligence,
  episodeRoi,
  listAnalyticsCandidates,
  overview,
  productionIntelligenceStats,
  promptRoi,
  proposeAnalyticsCandidates,
  reviewAnalyticsCandidate,
  riskRadar,
  type AnalyticsCandidate,
  type CostIntelligence,
  type CycleIntelligence,
  type DirectorRow,
  type EpisodeROI,
  type Overview,
  type PromptROIRow,
  type ProductionIntelligenceStats,
  type RiskItem,
} from "@/api/productionIntelligence";

const { Title, Text, Paragraph } = Typography;

const RISK_LABELS: Record<string, string> = {
  qc_failure_rate: "QC 失败率",
  cost_overrun: "成本超支",
  long_lead_time: "Lead Time 过长",
  high_revision: "高修订率",
};

const ProductionIntelligence: React.FC = () => {
  const [stats, setStats] = useState<ProductionIntelligenceStats | null>(null);
  const [overviewData, setOverviewData] = useState<Overview | null>(null);
  const [cost, setCost] = useState<CostIntelligence | null>(null);
  const [cycle, setCycle] = useState<CycleIntelligence | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeROI[]>([]);
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [directors, setDirectors] = useState<DirectorRow[]>([]);
  const [prompts, setPrompts] = useState<PromptROIRow[]>([]);
  const [candidates, setCandidates] = useState<AnalyticsCandidate[]>([]);
  const [busy, setBusy] = useState(false);

  const loadAll = () => {
    productionIntelligenceStats().then(setStats).catch((e: Error) => message.error(e.message));
    overview().then(setOverviewData).catch((e: Error) => message.error(e.message));
    costIntelligence().then(setCost).catch((e: Error) => message.error(e.message));
    cycleIntelligence().then(setCycle).catch((e: Error) => message.error(e.message));
    episodeRoi().then((r) => setEpisodes(r.episodes)).catch((e: Error) => message.error(e.message));
    riskRadar().then((r) => setRisks(r.risks)).catch((e: Error) => message.error(e.message));
    directorIntelligence().then((r) => setDirectors(r.directors)).catch((e: Error) => message.error(e.message));
    promptRoi().then((r) => setPrompts(r.prompts)).catch((e: Error) => message.error(e.message));
    listAnalyticsCandidates().then((r) => setCandidates(r.candidates)).catch((e: Error) => message.error(e.message));
  };

  useEffect(() => {
    loadAll();
  }, []);

  const onPropose = async () => {
    setBusy(true);
    try {
      const result = await proposeAnalyticsCandidates();
      message.success(`已生成 ${result.candidates.length} 个优化候选`);
      await loadAll();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onReview = async (candidate: AnalyticsCandidate, decision: "approved" | "rejected") => {
    try {
      await reviewAnalyticsCandidate(candidate.id, decision, "human");
      message.success(decision === "approved" ? "候选已批准" : "候选已驳回");
      await loadAll();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const onApply = async (candidate: AnalyticsCandidate) => {
    try {
      await applyAnalyticsCandidate(candidate.id);
      message.success("已应用（生成审计记录，生产资产未被自动修改）");
      await loadAll();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const episodeColumns = [
    { title: "集", dataIndex: "episode_id" },
    { title: "完播", dataIndex: "retention", render: (v: number) => `${(v * 100).toFixed(0)}%` },
    { title: "钩子", dataIndex: "hook_score", render: (v: number) => v.toFixed(2) },
    { title: "质量", dataIndex: "avg_qc", render: (v: number) => v.toFixed(3) },
    { title: "失败率", dataIndex: "failure_rate", render: (v: number) => `${(v * 100).toFixed(0)}%` },
    { title: "成本", dataIndex: "cost_actual" },
    { title: "ROI", dataIndex: "roi", render: (v: number) => v.toFixed(4) },
    { title: "Lead Time", dataIndex: "lead_time_s", render: (v: number) => `${v}s` },
  ];

  const riskColumns = [
    { title: "风险", dataIndex: "risk_type", render: (v: string) => RISK_LABELS[v] ?? v },
    { title: "目标", dataIndex: "target_id" },
    { title: "数值", dataIndex: "value", render: (v: number) => v.toFixed(3) },
    {
      title: "严重度",
      dataIndex: "severity",
      render: (v: number) => (
        <Progress percent={Math.round(v * 100)} size="small" status={v > 0.6 ? "exception" : v > 0.3 ? "active" : "normal"} />
      ),
    },
    { title: "说明", dataIndex: "message" },
  ];

  const directorColumns = [
    { title: "导演", dataIndex: "director" },
    { title: "镜头数", dataIndex: "shots" },
    { title: "成功率", dataIndex: "success_rate", render: (v: number) => `${(v * 100).toFixed(0)}%` },
    { title: "平均质量", dataIndex: "avg_quality", render: (v: number) => v.toFixed(3) },
    { title: "平均修订", dataIndex: "avg_revision", render: (v: number) => v.toFixed(2) },
    { title: "总成本", dataIndex: "total_cost" },
  ];

  const promptColumns = [
    { title: "Prompt 版本", dataIndex: "prompt_version" },
    { title: "使用次数", dataIndex: "usage" },
    { title: "成功率", dataIndex: "success_rate", render: (v: number) => `${(v * 100).toFixed(0)}%` },
    { title: "平均质量", dataIndex: "avg_quality", render: (v: number) => v.toFixed(3) },
    { title: "修订率", dataIndex: "revision_rate", render: (v: number) => v.toFixed(2) },
  ];

  const candidateColumns = [
    { title: "ID", dataIndex: "id", width: 150 },
    { title: "目标", dataIndex: "target_type", width: 110, render: (v: string, r: AnalyticsCandidate) => `${v}: ${r.target_id}` },
    { title: "原因", dataIndex: "reason" },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => {
        const color = value === "applied" ? "gold" : value === "approved" ? "green" : value === "rejected" ? "red" : value === "proposed" ? "orange" : "default";
        return <Tag color={color}>{value}</Tag>;
      },
    },
    {
      title: "操作",
      key: "actions",
      width: 210,
      render: (_: unknown, record: AnalyticsCandidate) => (
        <Space wrap>
          {record.status === "proposed" && (
            <>
              <Button size="small" type="primary" onClick={() => onReview(record, "approved")}>批准</Button>
              <Button size="small" onClick={() => onReview(record, "rejected")}>驳回</Button>
            </>
          )}
          {record.status === "approved" && (
            <Button size="small" type="primary" onClick={() => onApply(record)}>应用</Button>
          )}
        </Space>
      ),
    },
  ];

  const cyclePercent = (cycle?.lead_time_s ?? 0) > 0 ? 100 : 0;

  return (
    <div className="page-container">
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <DashboardOutlined /> Production Intelligence <Text type="secondary">生产智能中心</Text>
        </Title>
        <Paragraph type="secondary">
          事件仓库 → 分析引擎 → 智能中心 → 人工审批候选回流（auto_learning=false / auto_apply=false）
        </Paragraph>
      </div>

      {stats && (
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          <Col span={4}><Card size="small"><Statistic title="事件数" value={stats.warehouse.events} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="镜头指标" value={stats.warehouse.shot_metrics} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="集指标" value={stats.warehouse.episode_metrics} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="审计覆盖率" value={`${(stats.warehouse.audit_coverage * 100).toFixed(0)}%`} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="优化候选" value={stats.candidates.candidates} /></Card></Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="治理门禁" value={stats.governance.human_approval ? "开启" : "关闭"} />
              <Text type="secondary">auto_learning=false / auto_apply=false</Text>
            </Card>
          </Col>
        </Row>
      )}
      {overviewData && (
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          <Col span={4}><Card size="small"><Statistic title="集数" value={overviewData.episodes} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="镜头数" value={overviewData.shots} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="成功率" value={overviewData.success_rate} precision={2} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="平均质量" value={overviewData.avg_quality} precision={3} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="总成本" value={overviewData.total_cost} precision={2} /></Card></Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="成本解释率" value={overviewData.cost.explanation_rate} precision={3} suffix="/ 1.0" />
              <Text type="secondary">门禁 ≥ 0.90</Text>
            </Card>
          </Col>
        </Row>
      )}

      <Tabs defaultActiveKey="overview" items={[
        {
          key: "overview",
          label: <span><DashboardOutlined /> 总览</span>,
          children: (
            <Row gutter={[12, 12]}>
              <Col span={12}>
                <Card size="small" title="成本智能 Cost Intelligence">
                  {cost && (
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label="计划成本">{cost.planned}</Descriptions.Item>
                      <Descriptions.Item label="实际成本">{cost.actual}</Descriptions.Item>
                      <Descriptions.Item label="偏差">{(cost.variance >= 0 ? "+" : "") + cost.variance}</Descriptions.Item>
                      <Descriptions.Item label="拆因">
                        {cost.factors.length > 0
                          ? cost.factors.map((f) => <Tag key={f.factor} color="orange">{f.factor}: {f.cost}</Tag>)
                          : "无显著偏差因素"}
                      </Descriptions.Item>
                      <Descriptions.Item label="解释率">
                        <Progress percent={Math.round(cost.explanation_rate * 100)} size="small"
                                  status={cost.explanation_rate >= 0.9 ? "success" : "exception"} />
                      </Descriptions.Item>
                    </Descriptions>
                  )}
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small" title="周期智能 Cycle Intelligence（Lead Time 拆解）">
                  {cycle && (
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label="总 Lead Time">{cycle.lead_time_s}s</Descriptions.Item>
                      <Descriptions.Item label="等待 waiting">
                        {cycle.segments.waiting}s（{(cycle.ratios.waiting * 100).toFixed(0)}%）
                      </Descriptions.Item>
                      <Descriptions.Item label="生成 generation">
                        {cycle.segments.generation}s（{(cycle.ratios.generation * 100).toFixed(0)}%）
                      </Descriptions.Item>
                      <Descriptions.Item label="质检 review">
                        {cycle.segments.review}s（{(cycle.ratios.review * 100).toFixed(0)}%）
                      </Descriptions.Item>
                      <Descriptions.Item label="审批 approval">
                        {cycle.segments.approval}s（{(cycle.ratios.approval * 100).toFixed(0)}%）
                      </Descriptions.Item>
                    </Descriptions>
                  )}
                </Card>
              </Col>
            </Row>
          ),
        },
        {
          key: "episodes",
          label: <span><FundOutlined /> 集 ROI</span>,
          children: (
            <Card size="small">
              <Table rowKey="episode_id" size="small" columns={episodeColumns} dataSource={episodes} pagination={false} />
            </Card>
          ),
        },
        {
          key: "risks",
          label: <span><RadarChartOutlined /> 风险雷达</span>,
          children: (
            <Card size="small">
              <Table rowKey={(row: RiskItem) => `${row.risk_type}-${row.target_id}`} size="small" columns={riskColumns} dataSource={risks} pagination={false} />
            </Card>
          ),
        },
        {
          key: "directors",
          label: <span><ThunderboltOutlined /> 导演智能</span>,
          children: (
            <Card size="small">
              <Table rowKey="director" size="small" columns={directorColumns} dataSource={directors} pagination={false} />
            </Card>
          ),
        },
        {
          key: "prompts",
          label: <span><FundOutlined /> Prompt ROI</span>,
          children: (
            <Card size="small">
              <Table rowKey="prompt_version" size="small" columns={promptColumns} dataSource={prompts} pagination={false} />
            </Card>
          ),
        },
        {
          key: "candidates",
          label: <span><RocketOutlined /> 优化候选</span>,
          children: (
            <Card size="small">
              <Alert
                style={{ marginBottom: 12 }}
                type="info"
                showIcon
                message="人工审批门（Analytics 不是决策者）"
                description="分析引擎只生成证据与候选；必须人工批准后才能应用，应用仅生成审计记录，绝不自动修改生产资产。"
              />
              <Space style={{ marginBottom: 12 }}>
                <Button type="primary" loading={busy} onClick={onPropose}>从分析生成候选</Button>
              </Space>
              <Table rowKey="id" size="small" columns={candidateColumns} dataSource={candidates} pagination={{ pageSize: 8 }} />
            </Card>
          ),
        },
      ]} />
    </div>
  );
};

export default ProductionIntelligence;