/**
 * Industrial Asset Studio (Phase 13.3, GPT spec).
 *
 * Modules: Character Studio v2 (Bible 三视图/表情/动作/版本) / World Builder
 * (World & Scene Bible) / Shot DNA Studio (Top-K 检索) + Episode Production
 * Readiness Gate.
 */

import React, { useEffect, useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Progress,
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
  ClusterOutlined,
  DatabaseOutlined,
  GoldOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";

import {
  addBibleAction,
  addBibleExpression,
  addBibleVersion,
  addBibleView,
  addShotDna,
  createBible,
  createScene,
  createWorld,
  environmentSummary,
  listBibles,
  listScenes,
  listShotDna,
  listWorlds,
  projectReadiness,
  retrieveShotDna,
  shotDnaStats,
  type CharacterBible,
  type ReadinessReport,
  type RetrievalResult,
  type SceneBible,
  type ShotDNA,
  type WorldBible,
  productionReadinessMatrix,
  type ReadinessMatrix,
} from "@/api/industrial";
import {
  applyCandidate,
  autoProposeCandidates,
  feedbackStats,
  listFeedbackCandidates,
  listFeedbackEvents,
  recordFeedbackEvent,
  reviewCandidate,
  type FeedbackCandidate,
  type FeedbackEvent,
  type FeedbackStats as FeedbackStatsType,
} from "@/api/feedback";

const { Title, Text } = Typography;

const EXPRESSION_KEYS = ["neutral", "angry", "sad", "fear", "smile", "surprise"];
const ACTION_KEYS = ["walk", "run", "fight", "sit", "interact", "emotional"];
const VIEW_KEYS = ["front", "side", "back"];
const CATEGORY_KEYS = ["action", "dialogue", "emotion", "reveal", "climax", "transition"];

const INDUSTRIAL_LABELS: Record<string, string> = {
  neutral: "平静", angry: "愤怒", sad: "悲伤", fear: "恐惧", smile: "开心", surprise: "震惊",
  walk: "行走", run: "奔跑", fight: "战斗", sit: "坐姿", interact: "互动", emotional: "情绪化",
  front: "正面", side: "侧面", back: "背面",
  action: "动作", dialogue: "对话", emotion: "情绪", reveal: "揭示", climax: "高潮", transition: "转场",
};

const IndustrialStudio: React.FC = () => {
  const [projectId, setProjectId] = useState("default");
  const [readiness, setReadiness] = useState<ReadinessReport | null>(null);
  const [bibles, setBibles] = useState<CharacterBible[]>([]);
  const [worlds, setWorlds] = useState<WorldBible[]>([]);
  const [scenes, setScenes] = useState<SceneBible[]>([]);
  const [envEntries, setEnvEntries] = useState<number>(0);
  const [dna, setDna] = useState<ShotDNA[]>([]);
  const [dnaStats, setDnaStats] = useState<{ total: number; by_category: Record<string, number>; avg_success_rate: number; total_usage: number } | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalResult | null>(null);
  const [matrix, setMatrix] = useState<ReadinessMatrix | null>(null);
  const [fbStats, setFbStats] = useState<FeedbackStatsType | null>(null);
  const [fbEvents, setFbEvents] = useState<FeedbackEvent[]>([]);
  const [fbCandidates, setFbCandidates] = useState<FeedbackCandidate[]>([]);

  const load = async () => {
    const [r, b, w, s, e, d, ds, m, fs, fe, fc] = await Promise.all([
      projectReadiness(projectId),
      listBibles(),
      listWorlds(),
      listScenes(),
      environmentSummary(projectId),
      listShotDna(),
      shotDnaStats(),
      productionReadinessMatrix(projectId),
      feedbackStats(),
      listFeedbackEvents(),
      listFeedbackCandidates(),
    ]).catch(() => Array(11).fill(null));
    setReadiness(r);
    setBibles(b?.bibles ?? []);
    setWorlds(w?.worlds ?? []);
    setScenes(s?.scenes ?? []);
    setEnvEntries(e?.entries ?? 0);
    setDna(d?.items ?? []);
    setDnaStats(ds ?? null);
    setMatrix(m ?? null);
    setFbStats(fs ?? null);
    setFbEvents(fe?.events ?? []);
    setFbCandidates(fc?.candidates ?? []);
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const completeCount = bibles.filter((b) => b.completeness.ratio >= 0.9).length;

  return (
    <div style={{ padding: 16 }}>
      <Title level={4} style={{ marginTop: 0 }}>
        <ApartmentOutlined /> Industrial Asset Studio
        <Text type="secondary" style={{ fontSize: 13, marginLeft: 12 }}>
          Phase 13：角色资产 / 世界观 / 镜头库 / 生产就绪门禁
        </Text>
      </Title>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="项目 ID" value={projectId} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="生产就绪"
              value={readiness ? (readiness.ready ? "READY" : "BLOCKED") : "-"}
              valueStyle={{ color: readiness?.ready ? "#3f8600" : "#cf1322" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="角色 Bible 完整度" value={`${completeCount}/${bibles.length}`} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="Shot DNA" value={dnaStats?.total ?? 0} suffix="条" />
          </Card>
        </Col>
      </Row>

      {readiness && !readiness.ready && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="Episode 无法进入 ASSET_READY：资产未达标"
          description={
            <Space size={8}>
              {readiness.missing.map((name) => (
                <Tag key={name} color="red">{name}</Tag>
              ))}
            </Space>
          }
        />
      )}

      {matrix && (
        <Card
          size="small"
          title="Production Readiness Matrix（13.4-B）"
          style={{ marginBottom: 12 }}
          extra={<Tag color={matrix.status === "READY" ? "green" : matrix.status === "WARNING" ? "orange" : "red"}>{matrix.status}</Tag>}
        >
          <Table
            rowKey="name"
            size="small"
            pagination={false}
            dataSource={Object.entries(matrix.gates).map(([name, gate]) => ({ name, ...gate }))}
            columns={[
              { title: "门禁", dataIndex: "name", key: "name" },
              {
                title: "状态", dataIndex: "status", key: "status",
                render: (status: string) => (
                  <Tag color={status === "READY" ? "green" : status === "WARNING" ? "orange" : "red"}>{status}</Tag>
                ),
              },
              { title: "检查项", dataIndex: "checks", key: "checks" },
              { title: "缺失", dataIndex: "missing", key: "missing", render: (missing: string[]) => missing.join("，") || "-" },
              { title: "证据", dataIndex: "evidence", key: "evidence", render: (evidence: string[]) => evidence.join("，") || "-" },
              { title: "建议动作", dataIndex: "recommended_actions", key: "actions", render: (actions: string[]) => actions.join("；") || "-" },
            ]}
          />
        </Card>
      )}

      <Tabs
        items={[
          {
            key: "character",
            label: <Badge count={bibles.length} size="small"><span>Character Studio v2</span></Badge>,
            children: (
              <CharacterStudioPanel
                bibles={bibles}
                onChanged={load}
              />
            ),
          },
          {
            key: "world",
            label: <Badge count={worlds.length} size="small"><span>World Builder</span></Badge>,
            children: (
              <WorldBuilderPanel
                projectId={projectId}
                worlds={worlds}
                scenes={scenes}
                envEntries={envEntries}
                onChanged={load}
              />
            ),
          },
          {
            key: "shotdna",
            label: <Badge count={dnaStats?.total ?? 0} size="small"><span>Shot DNA Studio</span></Badge>,
            children: (
              <ShotDNAPanel
                dna={dna}
                stats={dnaStats}
                retrieval={retrieval}
                onRetrieved={setRetrieval}
                onChanged={load}
              />
            ),
          },
          {
            key: "feedback",
            label: <Badge count={fbStats?.candidates ?? 0} size="small"><span>反馈回流 Feedback</span></Badge>,
            children: (
              <FeedbackPanel
                stats={fbStats}
                events={fbEvents}
                candidates={fbCandidates}
                onChanged={load}
              />
            ),
          },
        ]}
      />
    </div>
  );
};

// ---------------------------------------------------------------- Character
interface CharacterStudioProps {
  bibles: CharacterBible[];
  onChanged: () => Promise<void>;
}

const CharacterStudioPanel: React.FC<CharacterStudioProps> = ({ bibles, onChanged }) => {
  const [createForm] = Form.useForm();
  const [assetForm] = Form.useForm();
  const [selected, setSelected] = useState<string | null>(null);

  const bible = bibles.find((b) => b.character_id === selected) ?? null;

  const columns = [
    { title: "角色", dataIndex: ["identity", "name"], key: "name" },
    { title: "ID", dataIndex: "character_id", key: "id" },
    {
      title: "三视图",
      key: "views",
      render: (_: unknown, row: CharacterBible) => (
        <Space size={4}>
          {Object.values(row.views).map((v) => (
            <Tag key={v.key} color="blue">{INDUSTRIAL_LABELS[v.key] ?? v.key}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "表情库",
      key: "expr",
      render: (_: unknown, row: CharacterBible) => (
        <Space size={4}>
          {Object.keys(row.expressions).map((k) => (
            <Tag key={k}>{INDUSTRIAL_LABELS[k] ?? k}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "动作库",
      key: "actions",
      render: (_: unknown, row: CharacterBible) => (
        <Space size={4}>
          {Object.keys(row.actions).map((k) => (
            <Tag key={k} color="purple">{INDUSTRIAL_LABELS[k] ?? k}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "版本",
      key: "versions",
      render: (_: unknown, row: CharacterBible) => (
        <Space size={4}>
          {Object.values(row.versions).map((v) => (
            <Tag key={v.id} color={v.approved ? "green" : "default"}>
              {v.id}{v.locked ? " 🔒" : ""}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "完整度",
      key: "ratio",
      render: (_: unknown, row: CharacterBible) => (
        <Progress percent={Math.round(row.completeness.ratio * 100)} size="small" />
      ),
    },
  ];

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Card size="small" title="创建 Character Bible">
        <Space align="start" size={8}>
          <Form form={createForm} layout="inline" onFinish={async (v) => {
            await createBible(v);
            createForm.resetFields();
            await onChanged();
          }}>
            <Form.Item name="character_id" rules={[{ required: true, message: "角色ID必填" }]}>
              <Input placeholder="角色 ID，如 CH001" style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="name"><Input placeholder="姓名，如 陈夜" style={{ width: 140 }} /></Form.Item>
            <Form.Item name="gender"><Select placeholder="性别" style={{ width: 90 }} options={[{ value: "male", label: "男" }, { value: "female", label: "女" }]} /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit">创建</Button></Form.Item>
          </Form>
        </Space>
      </Card>

      <Card size="small" title="角色资产列表">
        <Table<CharacterBible>
          rowKey={(row) => row.character_id}
          columns={columns}
          dataSource={bibles}
          pagination={{ pageSize: 6 }}
          size="small"
          onRow={(row) => ({ onClick: () => setSelected(row.character_id), style: { cursor: "pointer" } })}
        />
      </Card>

      {bible && (
        <Card
          size="small"
          title={`资产编辑：${bible.identity.name || bible.character_id}`}
          extra={
            <Space>
              <Tag color="geekblue">{Object.keys(bible.versions).length} 版本</Tag>
              <Tag color="green">完整度 {Math.round(bible.completeness.ratio * 100)}%</Tag>
            </Space>
          }
        >
          <Form
            form={assetForm}
            layout="inline"
            onFinish={async (v) => {
              if (v.kind === "view") await addBibleView(bible.character_id, { key: v.key, prompt: v.prompt });
              if (v.kind === "expression") await addBibleExpression(bible.character_id, { key: v.key, prompt: v.prompt });
              if (v.kind === "action") await addBibleAction(bible.character_id, { key: v.key, description: v.prompt });
              if (v.kind === "version") await addBibleVersion(bible.character_id, { version_id: v.key });
              assetForm.resetFields();
              await onChanged();
            }}
          >
            <Form.Item name="kind" initialValue="view">
              <Select style={{ width: 120 }} options={[
                { value: "view", label: "三视图" },
                { value: "expression", label: "表情" },
                { value: "action", label: "动作" },
                { value: "version", label: "版本" },
              ]} />
            </Form.Item>
            <Form.Item name="key" rules={[{ required: true, message: "key 必填" }]}>
              <Select style={{ width: 150 }} options={[
                ...VIEW_KEYS.map((k) => ({ value: k, label: INDUSTRIAL_LABELS[k] })),
                ...EXPRESSION_KEYS.map((k) => ({ value: k, label: INDUSTRIAL_LABELS[k] })),
                ...ACTION_KEYS.map((k) => ({ value: k, label: INDUSTRIAL_LABELS[k] })),
              ]} />
            </Form.Item>
            <Form.Item name="prompt"><Input placeholder="prompt / 描述" style={{ width: 220 }} /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit">添加资产</Button></Form.Item>
          </Form>
        </Card>
      )}
    </Space>
  );
};

// ---------------------------------------------------------------- World
interface WorldBuilderProps {
  projectId: string;
  worlds: WorldBible[];
  scenes: SceneBible[];
  envEntries: number;
  onChanged: () => Promise<void>;
}

const WorldBuilderPanel: React.FC<WorldBuilderProps> = ({ projectId, worlds, scenes, envEntries, onChanged }) => {
  const [worldForm] = Form.useForm();
  const [sceneForm] = Form.useForm();

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Card
        size="small"
        title={<Space><GoldOutlined /> 创建 World Bible</Space>}
        extra={<Statistic title="环境约束" value={envEntries} />}
      >
        <Form form={worldForm} layout="inline" onFinish={async (v) => {
          await createWorld({ project_id: projectId, name: v.name, era: v.era, technology: v.technology, power_system: v.power_system, visual_style: v.visual_style, color_language: v.color_language });
          worldForm.resetFields();
          await onChanged();
        }}>
          <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="世界观名，如 归墟" style={{ width: 130 }} /></Form.Item>
          <Form.Item name="era"><Input placeholder="纪元：未来科幻" style={{ width: 130 }} /></Form.Item>
          <Form.Item name="technology"><Input placeholder="科技：AI文明" style={{ width: 120 }} /></Form.Item>
          <Form.Item name="power_system"><Input placeholder="力量体系" style={{ width: 120 }} /></Form.Item>
          <Form.Item name="visual_style"><Input placeholder="视觉风格" style={{ width: 110 }} /></Form.Item>
          <Form.Item name="color_language"><Input placeholder="色彩语言" style={{ width: 110 }} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit">创建</Button></Form.Item>
        </Form>
      </Card>

      <Card size="small" title="World Bible 列表">
        <Row gutter={8}>
          {worlds.map((w) => (
            <Col span={8} key={w.id}>
              <Card size="small" style={{ marginBottom: 8 }}>
                <Text strong>{w.name}</Text>
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="纪元">{w.era || "-"}</Descriptions.Item>
                  <Descriptions.Item label="力量体系">{w.power_system || "-"}</Descriptions.Item>
                  <Descriptions.Item label="风格">{w.visual_style || "-"} / {w.color_language || "-"}</Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          ))}
          {worlds.length === 0 && <Text type="secondary">尚未创建 World Bible（world_analyzer 可自动生成）</Text>}
        </Row>
      </Card>

      <Card size="small" title="创建 Scene Bible">
        <Form form={sceneForm} layout="inline" onFinish={async (v) => {
          await createScene({
            project_id: projectId,
            world_id: worlds[0]?.id ?? "",
            name: v.name, location: v.location, time: v.time, weather: v.weather,
            forbidden_elements: v.forbidden ? v.forbidden.split(",").map((s: string) => s.trim()).filter(Boolean) : [],
          });
          sceneForm.resetFields();
          await onChanged();
        }}>
          <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="场景名" style={{ width: 120 }} /></Form.Item>
          <Form.Item name="location"><Input placeholder="地点" style={{ width: 110 }} /></Form.Item>
          <Form.Item name="time"><Select placeholder="时间" style={{ width: 90 }} options={[{ value: "day", label: "白天" }, { value: "night", label: "夜晚" }, { value: "dawn", label: "黎明" }]} /></Form.Item>
          <Form.Item name="weather"><Select placeholder="天气" style={{ width: 90 }} options={[{ value: "sunny", label: "晴" }, { value: "rain", label: "雨" }, { value: "snow", label: "雪" }, { value: "storm", label: "风暴" }]} /></Form.Item>
          <Form.Item name="forbidden"><Input placeholder="禁用元素，逗号分隔" style={{ width: 180 }} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit">创建</Button></Form.Item>
        </Form>
      </Card>

      <Card size="small" title="Scene Bible 列表">
        <Table<SceneBible>
          rowKey={(row) => row.id}
          size="small"
          pagination={false}
          dataSource={scenes}
          columns={[
            { title: "场景", dataIndex: "name", key: "name" },
            { title: "地点", dataIndex: "location", key: "location" },
            { title: "时间", dataIndex: "time", key: "time" },
            { title: "天气", dataIndex: "weather", key: "weather" },
            {
              title: "禁用元素",
              dataIndex: "forbidden_elements",
              key: "forbidden",
              render: (list: string[]) => (list ?? []).map((f) => <Tag key={f} color="red">{f}</Tag>),
            },
          ]}
        />
      </Card>
    </Space>
  );
};

// ---------------------------------------------------------------- Shot DNA
interface ShotDNAProps {
  dna: ShotDNA[];
  stats: { total: number; by_category: Record<string, number>; avg_success_rate: number; total_usage: number } | null;
  retrieval: RetrievalResult | null;
  onRetrieved: (r: RetrievalResult | null) => void;
  onChanged: () => Promise<void>;
}

const ShotDNAPanel: React.FC<ShotDNAProps> = ({ dna, stats, retrieval, onRetrieved, onChanged }) => {
  const [retrieveForm] = Form.useForm();
  const [addForm] = Form.useForm();

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Card size="small" title={<Space><DatabaseOutlined /> Shot DNA 统计</Space>}>
        <Row gutter={16}>
          <Col span={6}><Statistic title="镜头经验" value={stats?.total ?? 0} /></Col>
          <Col span={6}><Statistic title="平均成功率" value={stats?.avg_success_rate ?? 0} precision={2} /></Col>
          <Col span={6}><Statistic title="累计使用" value={stats?.total_usage ?? 0} /></Col>
          <Col span={6}>
            <Statistic
              title="检索命中"
              value={retrieval ? (retrieval.is_hit ? "HIT" : "MISS") : "-"}
              valueStyle={{ color: retrieval?.is_hit ? "#3f8600" : "#cf1322" }}
            />
          </Col>
        </Row>
        <Space size={4} style={{ marginTop: 8 }}>
          {CATEGORY_KEYS.map((c) => (
            <Tag key={c} color={stats && (stats.by_category[c] ?? 0) > 0 ? "blue" : "default"}>
              {INDUSTRIAL_LABELS[c]} {stats?.by_category[c] ?? 0}
            </Tag>
          ))}
        </Space>
      </Card>

      <Card size="small" title="Top-K 检索（特征匹配）">
        <Form form={retrieveForm} layout="inline" onFinish={async (v) => {
          const result = await retrieveShotDna({ ...v, top_k: 3 });
          onRetrieved(result);
        }}>
          <Form.Item name="category"><Select placeholder="类型" style={{ width: 110 }} allowClear options={CATEGORY_KEYS.map((c) => ({ value: c, label: INDUSTRIAL_LABELS[c] }))} /></Form.Item>
          <Form.Item name="scene"><Input placeholder="场景，如 battle" style={{ width: 120 }} /></Form.Item>
          <Form.Item name="emotion"><Input placeholder="情绪，如 fury" style={{ width: 110 }} /></Form.Item>
          <Form.Item name="camera_movement"><Input placeholder="运镜，如 push" style={{ width: 110 }} /></Form.Item>
          <Form.Item name="lighting"><Input placeholder="光照，如 low_key" style={{ width: 110 }} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit">检索</Button></Form.Item>
        </Form>
        {retrieval && (
          <Table
            style={{ marginTop: 8 }}
            rowKey={(row) => row.id}
            size="small"
            pagination={false}
            dataSource={retrieval.hits}
            columns={[
              { title: "ID", dataIndex: "id", key: "id" },
              { title: "类型", dataIndex: "category", key: "category", render: (c: string) => <Tag>{INDUSTRIAL_LABELS[c] ?? c}</Tag> },
              { title: "场景", dataIndex: "scene", key: "scene" },
              {
                title: "镜头",
                key: "camera",
                render: (_: unknown, row: ShotDNA) => `${(row.camera?.type as string) ?? ""} ${(row.camera?.movement as string) ?? ""}`,
              },
              { title: "镜头", dataIndex: "lens", key: "lens" },
              { title: "光照", dataIndex: "lighting", key: "lighting" },
              { title: "情绪", dataIndex: "emotion", key: "emotion" },
              {
                title: "成功率",
                dataIndex: "success_rate",
                key: "sr",
                render: (v: number) => <Tag color={v >= 0.85 ? "green" : "orange"}>{v}</Tag>,
              },
              {
                title: "匹配",
                dataIndex: "matched",
                key: "matched",
                render: (m: string[]) => (m ?? []).map((x) => <Tag key={x} color="geekblue">{x}</Tag>),
              },
            ]}
          />
        )}
      </Card>

      <Card size="small" title="添加自定义 Shot DNA">
        <Form form={addForm} layout="inline" onFinish={async (v) => {
          await addShotDna({ category: v.category, scene: v.scene, lens: v.lens, lighting: v.lighting, emotion: v.emotion, success_rate: 0.8 });
          addForm.resetFields();
          await onChanged();
        }}>
          <Form.Item name="category" rules={[{ required: true }]}><Select placeholder="类型" style={{ width: 110 }} options={CATEGORY_KEYS.map((c) => ({ value: c, label: INDUSTRIAL_LABELS[c] }))} /></Form.Item>
          <Form.Item name="scene"><Input placeholder="场景" style={{ width: 110 }} /></Form.Item>
          <Form.Item name="lens"><Input placeholder="镜头，如 35mm" style={{ width: 100 }} /></Form.Item>
          <Form.Item name="lighting"><Input placeholder="光照" style={{ width: 100 }} /></Form.Item>
          <Form.Item name="emotion"><Input placeholder="情绪曲线" style={{ width: 130 }} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit">添加</Button></Form.Item>
        </Form>
      </Card>
    </Space>
  );
};

interface FeedbackPanelProps {
  stats: FeedbackStatsType | null;
  events: FeedbackEvent[];
  candidates: FeedbackCandidate[];
  onChanged: () => Promise<void>;
}

const FeedbackPanel: React.FC<FeedbackPanelProps> = ({ stats, events, candidates, onChanged }) => {
  const [eventForm] = Form.useForm();
  const [pending, setPending] = useState(false);

  const run = async (task: () => Promise<unknown>) => {
    setPending(true);
    try {
      await task();
      await onChanged();
    } finally {
      setPending(false);
    }
  };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size={12}>
      <Row gutter={12}>
        <Col span={6}><Card size="small"><Statistic title="反馈事件" value={stats?.events ?? 0} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="候选更新" value={stats?.candidates ?? 0} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="待审核" value={stats?.by_status?.proposed ?? 0} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已应用" value={stats?.by_status?.applied ?? 0} /></Card></Col>
      </Row>

      <Alert
        type="info"
        showIcon
        message="自动记录反馈 ≠ 自动修改生产资产"
        description="Critic / Identity Gate / QC → 反馈事件 → 候选更新 → 人工审核 → 新版本。锁定资产不会被直接修改；Shot DNA 成功率按统计依据（min_samples=10 + prior_weight=5）重算。"
      />

      <Card size="small" title="记录反馈事件">
        <Form
          form={eventForm}
          layout="inline"
          onFinish={async (v) => {
            await recordFeedbackEvent({
              kind: v.kind, target_type: v.target_type, target_id: v.target_id,
              issues: (v.issues ?? "").split(",").map((x: string) => x.trim()).filter(Boolean),
              severity: v.severity ?? "medium",
            });
            eventForm.resetFields();
            await onChanged();
          }}
        >
          <Form.Item name="kind" initialValue="critic" rules={[{ required: true }]}>
            <Select style={{ width: 120 }} options={[{ value: "critic", label: "Critic" }, { value: "identity_gate", label: "Identity" }, { value: "qc", label: "QC" }]} />
          </Form.Item>
          <Form.Item name="target_type" initialValue="character" rules={[{ required: true }]}>
            <Select style={{ width: 130 }} options={[{ value: "character", label: "角色" }, { value: "world", label: "世界" }, { value: "shot_dna", label: "镜头" }, { value: "prompt_template", label: "提示词" }]} />
          </Form.Item>
          <Form.Item name="target_id" rules={[{ required: true, message: "目标 ID 必填" }]}>
            <Input placeholder="目标 ID（Bible/World/DNA/Template）" style={{ width: 220 }} />
          </Form.Item>
          <Form.Item name="issues"><Input placeholder="问题标签，逗号分隔" style={{ width: 260 }} /></Form.Item>
          <Form.Item name="severity" initialValue="medium">
            <Select style={{ width: 100 }} options={[{ value: "low", label: "低" }, { value: "medium", label: "中" }, { value: "high", label: "高" }]} />
          </Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" loading={pending}>记录</Button></Form.Item>
        </Form>
      </Card>

      <Card
        size="small"
        title="资产候选更新（人工审核门）"
        extra={
          <Button loading={pending} onClick={() => run(() => autoProposeCandidates(10))}>自动提议（≥10 样本）</Button>
        }
      >
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={candidates}
          columns={[
            { title: "候选 ID", dataIndex: "id", key: "id" },
            { title: "目标", dataIndex: "target_id", key: "target_id" },
            { title: "类型", dataIndex: "target_type", key: "target_type", render: (t: string) => <Tag>{t}</Tag> },
            { title: "理由", dataIndex: "reason", key: "reason" },
            { title: "建议变更", dataIndex: "suggested_changes", key: "changes", render: (c: Record<string, unknown>) => JSON.stringify(c) },
            { title: "状态", dataIndex: "status", key: "status", render: (st: string) => <Tag color={st === "applied" ? "green" : st === "approved" ? "blue" : st === "rejected" ? "red" : "orange"}>{st}</Tag> },
            { title: "审核人", dataIndex: "reviewer", key: "reviewer" },
            {
              title: "操作", key: "actions",
              render: (_, c: FeedbackCandidate) => (
                <Space>
                  <Button size="small" disabled={c.status !== "proposed"} onClick={() => run(() => reviewCandidate(c.id, "approve"))}>通过</Button>
                  <Button size="small" disabled={c.status !== "proposed"} onClick={() => run(() => reviewCandidate(c.id, "reject"))}>驳回</Button>
                  <Button size="small" disabled={c.status !== "approved"} onClick={() => run(() => applyCandidate(c.id))}>应用（生成新版本）</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Card size="small" title="反馈事件流（append-only）">
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={events.slice(0, 30)}
          columns={[
            { title: "来源", dataIndex: "source", key: "source" },
            { title: "类型", dataIndex: "kind", key: "kind", render: (k: string) => <Tag>{k}</Tag> },
            { title: "目标", dataIndex: "target_id", key: "target_id" },
            { title: "严重度", dataIndex: "severity", key: "severity", render: (sv: string) => <Tag color={sv === "high" ? "red" : sv === "medium" ? "orange" : "default"}>{sv}</Tag> },
            { title: "问题标签", dataIndex: "issues", key: "issues", render: (issues: string[]) => (issues ?? []).join("，") || "-" },
          ]}
        />
      </Card>
    </Space>
  );
};

export default IndustrialStudio;
