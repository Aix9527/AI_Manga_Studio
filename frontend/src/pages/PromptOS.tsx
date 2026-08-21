/**
 * Prompt OS (Phase 13.6, GPT spec).
 *
 * Prompt 操作系统：十引擎注册表 / Prompt DNA 知识库（含 ContinuityDNA 与
 * NegativeDNA）/ 八层 ShotDesign / Prompt Compiler 试算台 / Evolution 分数榜。
 * 所有进化候选必须人工审批（auto_learning=false / auto_apply=false）。
 */

import React, { useEffect, useMemo, useState } from "react";

import {
  Alert,
  Badge,
  message,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  List,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import {
  ApartmentOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  RocketOutlined,
} from "@ant-design/icons";

import {
  addDna,
  applyCandidate,
  compileSequence,
  compileShot,
  deriveShotDesignVersion,
  evolutionLeaderboard,
  listDna,
  listEngines,
  listEvolutionRecords,
  listShotDesigns,
  promptOsStats,
  proposeCandidates,
  recordMetric,
  reviewCandidate,
  runEngine,
  setShotDesignStatus,
  type DNARecord,
  type EngineRecord,
  type EvolutionRecord,
  type LeaderboardRow,
  type PromptOSStats,
  type ShotDesignRecord,
} from "@/api/promptOs";


const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const DNA_KIND_OPTIONS = [
  { value: "character", label: "角色 Character" },
  { value: "camera", label: "摄影 Camera" },
  { value: "lens", label: "焦段 Lens" },
  { value: "scene", label: "场景 Scene" },
  { value: "weather", label: "天气 Weather" },
  { value: "motion", label: "动作 Motion" },
  { value: "lighting", label: "灯光 Lighting" },
  { value: "composition", label: "构图 Composition" },
  { value: "style", label: "风格 Style" },
  { value: "continuity", label: "连续性 Continuity" },
  { value: "negative", label: "负面 Negative" },
];

const LAYER_LABELS: Record<string, string> = {
  story: "剧情",
  director_intent: "导演意图",
  photography: "摄影",
  composition: "构图",
  action: "动作",
  camera_movement: "运镜",
  lighting: "灯光",
  style: "风格",
};

function renderLayerValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

const PromptOS: React.FC = () => {
  const [stats, setStats] = useState<PromptOSStats | null>(null);
  const [engines, setEngines] = useState<EngineRecord[]>([]);
  const [dnaKind, setDnaKind] = useState<string>("character");
  const [dna, setDna] = useState<DNARecord[]>([]);
  const [shots, setShots] = useState<ShotDesignRecord[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [records, setRecords] = useState<EvolutionRecord[]>([]);
  const [compileResult, setCompileResult] = useState<ShotDesignRecord | null>(null);
  const [sequenceResult, setSequenceResult] = useState<ShotDesignRecord[]>([]);
  const [busy, setBusy] = useState(false);

  const [compileForm] = Form.useForm();
  const [sequenceForm] = Form.useForm();
  const [metricForm] = Form.useForm();

  const loadStats = () => promptOsStats().then(setStats).catch((e: Error) => message.error(e.message));
  const loadEngines = () => listEngines().then((r) => setEngines(r.engines)).catch((e: Error) => message.error(e.message));
  const loadDna = (kind: string) => listDna(kind).then((r) => setDna(r.entries)).catch((e: Error) => message.error(e.message));
  const loadShots = () => listShotDesigns().then((r) => setShots(r.shots)).catch((e: Error) => message.error(e.message));
  const loadLeaderboard = () => evolutionLeaderboard().then((r) => setLeaderboard(r.leaderboard)).catch((e: Error) => message.error(e.message));
  const loadRecords = () => listEvolutionRecords().then((r) => setRecords(r.records)).catch((e: Error) => message.error(e.message));

  useEffect(() => {
    loadStats();
    loadEngines();
    loadDna(dnaKind);
    loadShots();
    loadLeaderboard();
    loadRecords();
  }, []);

  useEffect(() => {
    loadDna(dnaKind);
  }, [dnaKind]);

  const onCompile = async () => {
    const values = await compileForm.validateFields();
    setBusy(true);
    try {
      const result = await compileShot(values);
      setCompileResult(result);
      message.success(`已生成 ShotDesign ${result.id}（${result.version}）`);
      await loadShots();
      await loadStats();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onCompileSequence = async () => {
    const values = await sequenceForm.validateFields();
    const lines = (values.lines ?? "").split("\n").map((line: string) => line.trim()).filter(Boolean);
    if (lines.length < 2) {
      message.error("连续镜头至少输入两行剧情");
      return;
    }
    setBusy(true);
    try {
      const result = await compileSequence(lines);
      setSequenceResult(result.shots);
      message.success(`已生成 ${result.shots.length} 个连续镜头（转场已自动衔接）`);
      await loadShots();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onRecordMetric = async () => {
    const values = await metricForm.validateFields();
    setBusy(true);
    try {
      await recordMetric(values);
      message.success("指标已记录");
      metricForm.resetFields();
      await loadLeaderboard();
      await loadStats();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onProposeCandidates = async () => {
    setBusy(true);
    try {
      const result = await proposeCandidates();
      message.success(`生成 ${result.candidates.length} 个进化候选`);
      await loadRecords();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onReview = async (record: EvolutionRecord, decision: "approved" | "rejected") => {
    try {
      await reviewCandidate(record.id, decision, "human");
      message.success(decision === "approved" ? "候选已批准，可应用生成新版本" : "候选已驳回");
      await loadRecords();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const onApply = async (record: EvolutionRecord) => {
    try {
      await applyCandidate(record.id);
      message.success("已生成新版本（原版本未改动）");
      await loadRecords();
      await loadShots();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const onSetStatus = async (shot: ShotDesignRecord, status: string) => {
    try {
      await setShotDesignStatus(shot.id, status, "human");
      message.success(`ShotDesign ${shot.id} 状态 → ${status}`);
      await loadShots();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const onDerive = async (shot: ShotDesignRecord) => {
    try {
      const next = await deriveShotDesignVersion(shot.id, {}, "从人工审批派生");
      message.success(`已派生新版本 ${next.version}`);
      await loadShots();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const engineColumns = [
    { title: "引擎", dataIndex: "key", width: 140 },
    { title: "名称", dataIndex: "name" },
    { title: "职责", dataIndex: "description" },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => (value === "active" ? <Tag color="green">active</Tag> : <Tag color="red">disabled</Tag>),
    },
    { title: "版本", dataIndex: "version", width: 80 },
  ];

  const dnaColumns = [
    { title: "ID", dataIndex: "id", width: 160 },
    { title: "名称", dataIndex: "name", width: 140 },
    { title: "描述 / 值", dataIndex: "description", render: (_: unknown, row: DNARecord) => renderLayerValue(row.values) },
    {
      title: "标签",
      dataIndex: "tags",
      width: 220,
      render: (tags: string[]) => tags.map((tag) => <Tag key={tag}>{tag}</Tag>),
    },
    {
      title: "用量",
      dataIndex: "usage_count",
      width: 90,
    },
  ];

  const shotColumns = [
    { title: "ID", dataIndex: "id", width: 150 },
    { title: "版本", dataIndex: "version", width: 70 },
    { title: "剧情", dataIndex: ["layers", "story"] },
    { title: "镜头", dataIndex: ["layers", "photography"], render: (v: unknown) => renderLayerValue(v) },
    { title: "时长", dataIndex: "duration_seconds", width: 80 },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => {
        const color = value === "locked" ? "gold" : value === "approved" ? "green" : "blue";
        return <Tag color={color}>{value}</Tag>;
      },
    },
    {
      title: "操作",
      key: "actions",
      width: 260,
      render: (_: unknown, shot: ShotDesignRecord) => (
        <Space wrap>
          {shot.status === "draft" && (
            <Button size="small" onClick={() => onSetStatus(shot, "approved")}>批准</Button>
          )}
          {shot.status === "approved" && (
            <Button size="small" onClick={() => onSetStatus(shot, "locked")}>锁定</Button>
          )}
          {shot.status === "locked" && (
            <Button size="small" onClick={() => onDerive(shot)}>派生新版本</Button>
          )}
        </Space>
      ),
    },
  ];

  const boardColumns = [
    { title: "镜头", dataIndex: "shot_design_id" },
    { title: "样本", dataIndex: "samples", width: 80 },
    { title: "Prompt Score", dataIndex: "score", width: 120, render: (v: number) => v.toFixed(3) },
    { title: "完播率", dataIndex: "completion", width: 90, render: (v: number) => `${(v * 100).toFixed(1)}%` },
    { title: "点赞率", dataIndex: "like", width: 90, render: (v: number) => `${(v * 100).toFixed(1)}%` },
    { title: "评论率", dataIndex: "comment", width: 90, render: (v: number) => `${(v * 100).toFixed(1)}%` },
    { title: "收藏率", dataIndex: "favorite", width: 90, render: (v: number) => `${(v * 100).toFixed(1)}%` },
    { title: "播放", dataIndex: "views", width: 100 },
  ];

  const recordColumns = [
    { title: "ID", dataIndex: "id", width: 150 },
    { title: "镜头", dataIndex: "shot_design_id", width: 170 },
    { title: "Score", dataIndex: "score", width: 90, render: (v: number) => v.toFixed(3) },
    { title: "样本", dataIndex: "samples", width: 70 },
    { title: "建议", dataIndex: "suggested_layers", render: (v: Record<string, string>) => Object.entries(v).map(([k, val]) => <Tag key={k}>{k}: {val}</Tag>) },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => {
        const color = value === "applied" ? "gold" : value === "approved" ? "green" : value === "rejected" ? "red" : value === "candidate" ? "orange" : "default";
        return <Tag color={color}>{value}</Tag>;
      },
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_: unknown, record: EvolutionRecord) => (
        <Space wrap>
          {record.status === "candidate" && (
            <>
              <Button size="small" type="primary" onClick={() => onReview(record, "approved")}>批准</Button>
              <Button size="small" onClick={() => onReview(record, "rejected")}>驳回</Button>
            </>
          )}
          {record.status === "approved" && (
            <Button size="small" type="primary" onClick={() => onApply(record)}>应用新版本</Button>
          )}
        </Space>
      ),
    },
  ];

  const continuityEntries = dna.filter((entry) => entry.kind === "continuity");
  const negativeEntries = dna.filter((entry) => entry.kind === "negative");

  return (
    <div className="page-container">
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <ApartmentOutlined /> Prompt OS <Text type="secondary">提示词操作系统</Text>
        </Title>
        <Paragraph type="secondary">
          电影 Prompt 语言 · 八层 ShotDesign · Prompt DNA · Compiler · Evolution（人工审批制）
        </Paragraph>
      </div>

      {stats && (
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          <Col span={4}><Card size="small"><Statistic title="引擎" value={stats.engines} suffix={`/ ${stats.engines_active} 活跃`} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="DNA 条目" value={stats.dna.entries} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="ShotDesign" value={stats.shot_designs} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="进化指标" value={stats.evolution.metrics} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="进化记录" value={stats.evolution.records} /></Card></Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="冻结约束" value={stats.evolution.auto_learning ? "ON" : "OFF"} prefix={<Badge status={stats.evolution.auto_learning ? "error" : "success"} />} />
              <Text type="secondary">auto_learning / auto_apply = false</Text>
            </Card>
          </Col>
        </Row>
      )}

      <Tabs defaultActiveKey="engines" items={[
        {
          key: "engines",
          label: <span><RocketOutlined /> 十引擎</span>,
          children: (
            <Card size="small">
              <Table rowKey="key" size="small" columns={engineColumns} dataSource={engines} pagination={false} />
            </Card>
          ),
        },
        {
          key: "dna",
          label: <span><ExperimentOutlined /> Prompt DNA 知识库</span>,
          children: (
            <Card size="small">
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space wrap>
                  <Select value={dnaKind} onChange={setDnaKind} style={{ width: 220 }} options={DNA_KIND_OPTIONS} />
                  <Button
                    onClick={() => {
                      void addDna({
                        kind: dnaKind,
                        name: "示例条目",
                        values: { detail: "待完善" },
                        tags: ["示例"],
                      }).then(() => {
                        message.success("DNA 条目已添加");
                        return loadDna(dnaKind);
                      });
                    }}
                  >
                    添加示例条目
                  </Button>
                </Space>
                {dnaKind === "continuity" && continuityEntries.length > 0 && (
                  <Alert type="info" showIcon message="ContinuityDNA（GPT 修改建议 3）" description="跨镜人物/空间/道具状态继承规则，用于连续镜头一致性约束。" />
                )}
                {dnaKind === "negative" && negativeEntries.length > 0 && (
                  <Alert type="warning" showIcon message="NegativeDNA（GPT 修改建议 4）" description="失败模式词库：面部/形体/物理/画质/一致性失败词，编译时自动注入负面词。" />
                )}
                <Table rowKey="id" size="small" columns={dnaColumns} dataSource={dna} pagination={{ pageSize: 10 }} />
              </Space>
            </Card>
          ),
        },
        {
          key: "compiler",
          label: <span><FileSearchOutlined /> Compiler 试算台</span>,
          children: (
            <Row gutter={[12, 12]}>
              <Col span={12}>
                <Card size="small" title="一句剧情 → 八层 ShotDesign">
                  <Form form={compileForm} layout="vertical" initialValues={{ logline: "少年进入地下遗迹", duration_seconds: 10, lens: "24mm" }}>
                    <Form.Item name="logline" label="剧情（一句话）" rules={[{ required: true, message: "请输入剧情" }]}>
                      <TextArea rows={2} placeholder="例如：少年进入地下遗迹" />
                    </Form.Item>
                    <Form.Item name="duration_seconds" label="时长（秒，建议 ≥10）">
                      <Input type="number" />
                    </Form.Item>
                    <Form.Item name="lens" label="焦段">
                      <Select options={["24mm", "35mm", "50mm", "85mm", "135mm"].map((v) => ({ value: v, label: v }))} allowClear />
                    </Form.Item>
                    <Form.Item name="style" label="风格">
                      <Select
                        allowClear
                        options={[
                          { value: "east_wuxia", label: "东方武侠（水墨写意）" },
                          { value: "neon_cyber", label: "高对比霓虹赛博" },
                          { value: "epic_wide", label: "广角史诗" },
                          { value: "ink_fantasy", label: "水墨东方幻想" },
                          { value: "anime", label: "日系动画" },
                        ]}
                      />
                    </Form.Item>
                    <Button type="primary" loading={busy} onClick={onCompile}>编译 ShotDesign</Button>
                  </Form>
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small" title="编译结果">
                  {compileResult ? (
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label="ID / 版本">{compileResult.id} · {compileResult.version}</Descriptions.Item>
                      <Descriptions.Item label="状态"><Tag color={compileResult.status === "draft" ? "blue" : "green"}>{compileResult.status}</Tag></Descriptions.Item>
                      <Descriptions.Item label="时长">{compileResult.duration_seconds}s</Descriptions.Item>
                      <Descriptions.Item label="转场衔接">in: {compileResult.transition_in || "—"} / out: {compileResult.transition_out}</Descriptions.Item>
                      <Descriptions.Item label="负面词">{(compileResult.negative_words ?? []).slice(0, 6).join("、")}</Descriptions.Item>
                      {Object.entries(compileResult.layers ?? {}).map(([key, value]) => (
                        <Descriptions.Item key={key} label={LAYER_LABELS[key] ?? key}>
                          <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{renderLayerValue(value)}</pre>
                        </Descriptions.Item>
                      ))}
                      <Descriptions.Item label="continuity_contract">
                        <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{renderLayerValue(compileResult.continuity_contract)}</pre>
                      </Descriptions.Item>
                    </Descriptions>
                  ) : (
                    <Text type="secondary">输入剧情后点击"编译 ShotDesign"查看八层输出。</Text>
                  )}
                </Card>
              </Col>
            </Row>
          ),
        },
        {
          key: "sequence",
          label: <span><FileSearchOutlined /> 连续镜头</span>,
          children: (
            <Card size="small" title="多镜头连续编译（转场自动衔接 + continuity 继承）">
              <Form form={sequenceForm} layout="vertical" initialValues={{ lines: "少年进入地下遗迹\n少年回眸望向黑暗" }}>
                <Form.Item name="lines" label="每行一个镜头剧情">
                  <TextArea rows={4} placeholder={"少年进入地下遗迹\n少年回眸望向黑暗"} />
                </Form.Item>
                <Button type="primary" loading={busy} onClick={onCompileSequence}>编译连续镜头</Button>
              </Form>
              {sequenceResult.length > 0 && (
                <List
                  style={{ marginTop: 16 }}
                  dataSource={sequenceResult}
                  renderItem={(shot, index) => (
                    <List.Item>
                      <Space direction="vertical" style={{ width: "100%" }}>
                        <Text strong>镜头 {index + 1} · {shot.id}（{shot.version}）</Text>
                        <Text>in: {shot.transition_in || "—"} → out: {shot.transition_out}</Text>
                        <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{renderLayerValue(shot.layers)}</pre>
                      </Space>
                    </List.Item>
                  )}
                />
              )}
            </Card>
          ),
        },
        {
          key: "shots",
          label: <span><ApartmentOutlined /> ShotDesign 版本</span>,
          children: (
            <Card size="small">
              <Table rowKey="id" size="small" columns={shotColumns} dataSource={shots} pagination={{ pageSize: 8 }} />
            </Card>
          ),
        },
        {
          key: "evolution",
          label: <span><RocketOutlined /> Evolution</span>,
          children: (
            <Row gutter={[12, 12]}>
              <Col span={12}>
                <Card size="small" title="记录平台指标">
                  <Form form={metricForm} layout="vertical" initialValues={{ completion_rate: 0.6, like_rate: 0.2, comment_rate: 0.1, favorite_rate: 0.15, views: 5000 }}>
                    <Form.Item name="shot_design_id" label="镜头 ID" rules={[{ required: true, message: "请输入镜头 ID" }]}>
                      <Input placeholder="先编译一个 ShotDesign 拿到 ID" />
                    </Form.Item>
                    <Form.Item name="completion_rate" label="完播率 (0-1)"><Input type="number" step="0.05" /></Form.Item>
                    <Form.Item name="like_rate" label="点赞率 (0-1)"><Input type="number" step="0.05" /></Form.Item>
                    <Form.Item name="comment_rate" label="评论率 (0-1)"><Input type="number" step="0.05" /></Form.Item>
                    <Form.Item name="favorite_rate" label="收藏率 (0-1)"><Input type="number" step="0.05" /></Form.Item>
                    <Form.Item name="views" label="播放量"><Input type="number" /></Form.Item>
                    <Space>
                      <Button type="primary" loading={busy} onClick={onRecordMetric}>记录指标</Button>
                      <Button loading={busy} onClick={onProposeCandidates}>生成进化候选</Button>
                    </Space>
                  </Form>
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small" title="Prompt Score 榜（完播/点赞/评论/收藏加权）">
                  <Table rowKey="shot_design_id" size="small" columns={boardColumns} dataSource={leaderboard} pagination={false} />
                </Card>
              </Col>
              <Col span={24}>
                <Card size="small" title="进化候选与审批">
                  <Alert
                    style={{ marginBottom: 12 }}
                    type="info"
                    showIcon
                    message="人工审批门（auto_learning=false / auto_apply=false）"
                    description="候选必须人工批准后才能应用；应用只生成新版本，绝不修改已锁定版本。"
                  />
                  <Table rowKey="id" size="small" columns={recordColumns} dataSource={records} pagination={{ pageSize: 8 }} />
                </Card>
              </Col>
            </Row>
          ),
        },
      ]} />
    </div>
  );
};

export default PromptOS;