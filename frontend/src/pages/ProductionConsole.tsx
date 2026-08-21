/**
 * Multi-Project Production Console (Phase 13.5-A, GPT spec).
 *
 * 执行中心（与 Director 智能决策中心职责分离）：Projects/Seasons/
 * Resource Planner / GPU Queue / Budget / Scheduler / Audit。
 * 所有 GPU/预算/调度输出均为「推荐 + 人工审批」，无自动越权。
 */

import React, { useEffect, useState } from "react";

import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
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
  AuditOutlined,
  CalendarOutlined,
  CloudServerOutlined,
  ControlOutlined,
  DollarOutlined,
  PartitionOutlined,
  TeamOutlined,
} from "@ant-design/icons";

import {
  approveBudgetOverride,
  approveSchedulePlan,
  attachSeasonEpisode,
  authorizeBudget,
  budgetSummary,
  buildSchedulePlan,
  createSeason,
  dispatchSchedulePlan,
  gpuQueueRecommend,
  listResources,
  listSchedulePlans,
  listSeasons,
  orchestratorAudit,
  planResource,
  recordBudgetCost,
  registerDependency,
  resourceStats,
  seasonStats,
  setBudgetPolicy,
  setSeasonStatus,
  type BudgetSummary,
  type ProjectResource,
  type SchedulePlan,
  type Season,
} from "@/api/productionConsole";
import { userMessage } from "@/api/client";
import TeamCollaboration from "@/pages/TeamCollaboration";

const { Title, Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  planning: "default", production: "processing", paused: "warning",
  review: "blue", completed: "success", draft: "default", active: "processing",
  ok: "success", warning: "warning", exceeded: "red",
  proposed: "orange", approved: "blue", dispatched: "green", rejected: "red",
};

const ProductionConsole: React.FC = () => {
  const [projectId, setProjectId] = useState("default");
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [seasonStatsData, setSeasonStatsData] = useState<{ seasons: number; episodes_attached: number } | null>(null);
  const [resources, setResources] = useState<ProjectResource[]>([]);
  const [resourceStatsData, setResourceStatsData] = useState<{ projects: number; gpu_capacity: number; budget_allocated: number } | null>(null);
  const [gpuRec, setGpuRec] = useState<{ queued: number; recommended: Array<Record<string, unknown>>; note: string } | null>(null);
  const [budget, setBudget] = useState<BudgetSummary | null>(null);
  const [plans, setPlans] = useState<SchedulePlan[]>([]);
  const [auditRows, setAuditRows] = useState<Array<{ action: string; target: string; detail: string; actor: string; at: string }>>([]);
  const [error, setError] = useState("");

  const load = async () => {
    const [s, ss, r, rs, b, p, a] = await Promise.all([
      listSeasons(projectId), seasonStats(projectId), listResources(projectId),
      resourceStats(), budgetSummary(projectId), listSchedulePlans(projectId),
      orchestratorAudit(),
    ]).catch((err: unknown) => {
      setError(userMessage(err));
      return [null, null, null, null, null, null, null];
    });
    setSeasons(s?.seasons ?? []);
    setSeasonStatsData(ss ?? null);
    setResources(r?.resources ?? []);
    setResourceStatsData(rs ?? null);
    setBudget(b ?? null);
    setPlans(p?.plans ?? []);
    setAuditRows(a?.audit ?? []);
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const notify = (ok: boolean, message: string) => {
    setError(ok ? "" : message);
    void load();
  };

  const run = async (task: () => Promise<unknown>) => {
    try {
      await task();
      notify(true, "");
    } catch (err) {
      notify(false, userMessage(err));
    }
  };

  return (
    <div style={{ padding: 16 }}>
      <Title level={4} style={{ marginTop: 0 }}>
        <ControlOutlined /> Production Console
        <Text type="secondary" style={{ fontSize: 13, marginLeft: 12 }}>
          Phase 13.5-A：多项目 / 多季 / 资源 / GPU 队列 / 预算 / 并行调度（执行中心）
        </Text>
      </Title>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={4}><Card size="small"><Statistic title="项目" value={resourceStatsData?.projects ?? 0} /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="季" value={seasonStatsData?.seasons ?? 0} /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="已关联 Episode" value={seasonStatsData?.episodes_attached ?? 0} /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="GPU 容量" value={resourceStatsData?.gpu_capacity ?? 0} /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="预算状态" value={budget?.status ?? "-"} valueStyle={{ color: budget?.status === "exceeded" ? "#cf1322" : budget?.status === "warning" ? "#d46b08" : "#3f8600" }} /></Card></Col>
      </Row>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="推荐 ≠ 自动执行"
        description="GPU 分配 / 并行度 / 预算均为推荐；预算超额不自动停止，需 Producer 审批覆盖；调度计划需人工批准后才 dispatch（复用现有 TaskQueue / Worker / LeaseLock / CostMeter）。"
      />

      <Tabs
        items={[
          {
            key: "seasons",
            label: <Space><PartitionOutlined />季管理</Space>,
            children: <SeasonPanel projectId={projectId} seasons={seasons} onChanged={load} />,
          },
          {
            key: "resources",
            label: <Space><CloudServerOutlined />项目资源</Space>,
            children: <ResourcePanel projectId={projectId} resources={resources} onChanged={load} />,
          },
          {
            key: "gpu",
            label: <Space><ControlOutlined />GPU 队列</Space>,
            children: <GpuPanel onRecommend={async (limit, capacity) => { await run(async () => { setGpuRec(await gpuQueueRecommend({ limit, gpu_capacity: capacity })); }); }} gpuRec={gpuRec} />,
          },
          {
            key: "budget",
            label: <Space><DollarOutlined />预算</Space>,
            children: <BudgetPanel projectId={projectId} budget={budget} onChanged={load} />,
          },
          {
            key: "scheduler",
            label: <Space><CalendarOutlined />并行调度</Space>,
            children: <SchedulerPanel projectId={projectId} plans={plans} onChanged={load} />,
          },
          {
            key: "team",
            label: <Space><TeamOutlined />团队协作</Space>,
            children: <TeamCollaboration projectId={projectId} />,
          },
          {
            key: "audit",
            label: <Space><AuditOutlined />审计</Space>,
            children: (
              <Card size="small" title="审计链（append-only）">
                <Table
                  rowKey={(row) => `${row.at}-${row.action}-${row.target}`}
                  size="small"
                  pagination={{ pageSize: 20 }}
                  dataSource={auditRows}
                  columns={[
                    { title: "动作", dataIndex: "action", key: "action" },
                    { title: "目标", dataIndex: "target", key: "target" },
                    { title: "详情", dataIndex: "detail", key: "detail" },
                    { title: "操作人", dataIndex: "actor", key: "actor" },
                    { title: "时间", dataIndex: "at", key: "at" },
                  ]}
                />
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
};

// ---------------------------------------------------------------- Seasons
function SeasonPanel(props: { projectId: string; seasons: Season[]; onChanged: () => Promise<void> }) {
  const [form] = Form.useForm();
  return (
    <Space direction="vertical" style={{ width: "100%" }} size={12}>
      <Card size="small" title="创建季">
        <Form layout="inline" form={form} onFinish={async (v) => {
          await createSeason({ project_id: props.projectId, season_no: v.season_no, name: v.name, target_episodes: v.target_episodes ?? 0 });
          form.resetFields();
          await props.onChanged();
        }}>
          <Form.Item name="season_no" initialValue={1} rules={[{ required: true }]}><InputNumber min={1} /></Form.Item>
          <Form.Item name="name"><Input placeholder="季名（可空）" /></Form.Item>
          <Form.Item name="target_episodes"><InputNumber min={0} placeholder="目标集数" /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit">创建</Button></Form.Item>
        </Form>
      </Card>
      <Card size="small" title="季列表（点击行展开关联 Episode）">
        <Table
          rowKey="id"
          dataSource={props.seasons}
          pagination={false}
          columns={[
            { title: "季", dataIndex: "season_no", key: "season_no", render: (n: number) => `第${n}季` },
            { title: "名称", dataIndex: "name", key: "name" },
            { title: "状态", dataIndex: "status", key: "status", render: (s: string) => <Tag color={STATUS_COLORS[s]}>{s}</Tag> },
            { title: "目标集数", dataIndex: "target_episodes", key: "target" },
            { title: "已关联", dataIndex: "episode_ids", key: "episodes", render: (ids: string[]) => ids.length },
            {
              title: "操作", key: "ops",
              render: (_, season: Season) => (
                <Space>
                  <Select
                    placeholder="推进状态"
                    size="small"
                    style={{ width: 130 }}
                    options={["planning", "production", "paused", "review", "completed"].map((s) => ({ value: s, label: s }))}
                    onChange={(status) => void setSeasonStatus(season.id, status).then(props.onChanged)}
                  />
                </Space>
              ),
            },
          ]}
          expandable={{
            expandedRowRender: (season) => (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space wrap>
                  {season.episode_ids.map((eid) => <Tag key={eid}>{eid}</Tag>)}
                </Space>
                <Form layout="inline" onFinish={async (v) => {
                  await attachSeasonEpisode(season.id, v.episode_id);
                  await props.onChanged();
                }}>
                  <Form.Item name="episode_id" rules={[{ required: true, message: "Episode ID 必填" }]}>
                    <Input placeholder="Episode ID（如 EP-001）" />
                  </Form.Item>
                  <Form.Item><Button htmlType="submit">关联</Button></Form.Item>
                </Form>
              </Space>
            ),
          }}
        />
      </Card>
    </Space>
  );
}

// ---------------------------------------------------------------- Resources
function ResourcePanel(props: { projectId: string; resources: ProjectResource[]; onChanged: () => Promise<void> }) {
  const [form] = Form.useForm();
  return (
    <Space direction="vertical" style={{ width: "100%" }} size={12}>
      <Card size="small" title="资源规划（GPU / 预算 / 优先级）">
        <Form layout="inline" form={form} onFinish={async (v) => {
          await planResource({ project_id: props.projectId, gpu_capacity: v.gpu_capacity ?? 1, budget_allocated: v.budget_allocated ?? 0, deadline: v.deadline ?? "", priority: v.priority ?? 3 });
          form.resetFields();
          await props.onChanged();
        }}>
          <Form.Item name="gpu_capacity" initialValue={1} rules={[{ required: true }]}><InputNumber min={0} addonBefore="GPU" /></Form.Item>
          <Form.Item name="budget_allocated"><InputNumber min={0} addonBefore="预算" /></Form.Item>
          <Form.Item name="deadline"><Input placeholder="截止日期 ISO" /></Form.Item>
          <Form.Item name="priority" initialValue={3}><InputNumber min={1} max={5} addonBefore="优先级" /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit">规划</Button></Form.Item>
        </Form>
      </Card>
      <Card size="small" title="资源列表">
        <Table
          rowKey="id"
          dataSource={props.resources}
          pagination={false}
          columns={[
            { title: "项目", dataIndex: "project_id", key: "project" },
            { title: "GPU", dataIndex: "gpu_capacity", key: "gpu" },
            { title: "预算", dataIndex: "budget_allocated", key: "budget" },
            { title: "截止", dataIndex: "deadline", key: "deadline" },
            { title: "优先级", dataIndex: "priority", key: "priority", render: (p: number) => <Tag color={p >= 4 ? "red" : p >= 3 ? "orange" : "default"}>{p}</Tag> },
            { title: "状态", dataIndex: "status", key: "status", render: (s: string) => <Tag color={STATUS_COLORS[s]}>{s}</Tag> },
          ]}
        />
      </Card>
    </Space>
  );
}

// ---------------------------------------------------------------- GPU Queue
function GpuPanel(props: { gpuRec: { queued: number; recommended: Array<Record<string, unknown>>; note: string } | null; onRecommend: (limit: number, capacity: number) => Promise<void> }) {
  return (
    <Card size="small" title="GPU 队列推荐（复用 TaskQueue，只读推荐）">
      <Space direction="vertical" style={{ width: "100%" }} size={12}>
        <Space>
          <Button type="primary" onClick={() => props.onRecommend(10, 1)}>生成推荐</Button>
          <Text type="secondary">schedule_score = priority + deadline + gpu_fit + retry_penalty</Text>
        </Space>
        {props.gpuRec ? (
          <>
            <Statistic title="排队任务" value={props.gpuRec.queued} />
            <Table
              rowKey="task_id"
              size="small"
              pagination={false}
              dataSource={props.gpuRec.recommended}
              columns={[
                { title: "任务", dataIndex: "task_id", key: "task" },
                { title: "类型", dataIndex: "task_type", key: "type" },
                { title: "项目", dataIndex: "project_id", key: "project" },
                { title: "优先级", dataIndex: "priority", key: "priority" },
                { title: "期限因子", dataIndex: "deadline_factor", key: "deadline" },
                { title: "GPU 适配", dataIndex: "gpu_fit_score", key: "fit" },
                { title: "重试惩罚", dataIndex: "retry_penalty", key: "retry" },
                { title: "评分", dataIndex: "score", key: "score", render: (v: number) => <Tag color={v >= 10 ? "green" : "default"}>{v}</Tag> },
              ]}
            />
          </>
        ) : null}
      </Space>
    </Card>
  );
}

// ---------------------------------------------------------------- Budget
function BudgetPanel(props: { projectId: string; budget: BudgetSummary | null; onChanged: () => Promise<void> }) {
  const [policyForm] = Form.useForm();
  const [costForm] = Form.useForm();
  const [authMsg, setAuthMsg] = useState("");
  return (
    <Space direction="vertical" style={{ width: "100%" }} size={12}>
      <Card size="small" title={`预算概览：${props.projectId}`}>
        {props.budget ? (
          <Row gutter={12}>
            <Col span={6}><Statistic title="已消耗" value={props.budget.spent} /></Col>
            <Col span={6}><Statistic title="月度上限" value={props.budget.monthly_limit} /></Col>
            <Col span={6}><Statistic title="使用率" value={props.budget.ratio} precision={3} /></Col>
            <Col span={6}><Statistic title="Cost Meter 镜数" value={props.budget.cost_meter_shots} /></Col>
          </Row>
        ) : <Text type="secondary">未设置预算策略</Text>}
      </Card>
      <Card size="small" title="预算策略（warning 0.8 / hard 1.0 / 超额需 Producer 审批）">
        <Form layout="inline" form={policyForm} onFinish={async (v) => {
          await setBudgetPolicy(props.projectId, { monthly_limit: v.monthly_limit, episode_limit: v.episode_limit ?? 0, warning_threshold: v.warning_threshold ?? 0.8, hard_limit: v.hard_limit ?? 1.0, override_requires_approval: true });
          policyForm.resetFields();
          await props.onChanged();
        }}>
          <Form.Item name="monthly_limit" rules={[{ required: true, message: "上限必填" }]}><InputNumber min={0} addonBefore="月度上限" /></Form.Item>
          <Form.Item name="warning_threshold" initialValue={0.8}><InputNumber min={0} max={1} step={0.05} /></Form.Item>
          <Form.Item name="hard_limit" initialValue={1.0}><InputNumber min={0} max={2} step={0.05} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit">保存策略</Button></Form.Item>
        </Form>
      </Card>
      <Card size="small" title="成本记账（接入 Cost Meter）">
        <Form layout="inline" form={costForm} onFinish={async (v) => {
          await recordBudgetCost(props.projectId, { amount: v.amount, note: v.note ?? "" });
          costForm.resetFields();
          await props.onChanged();
        }}>
          <Form.Item name="amount" rules={[{ required: true, message: "金额必填" }]}><InputNumber min={0} addonBefore="金额" /></Form.Item>
          <Form.Item name="note"><Input placeholder="备注" /></Form.Item>
          <Form.Item><Button htmlType="submit">记账</Button></Form.Item>
        </Form>
      </Card>
      <Card size="small" title="超额审批（不自动停止）">
        <Space>
          <Button onClick={() => void authorizeBudget(props.projectId, 0).then((r) => setAuthMsg(r.allowed ? "预算正常" : `需 Producer 审批：${r.reason}`))}>检查授权</Button>
          <Button type="primary" onClick={() => void approveBudgetOverride(props.projectId).then(props.onChanged)}>Producer 审批覆盖</Button>
        </Space>
        {authMsg ? <div style={{ marginTop: 8 }}><Text type={authMsg === "预算正常" ? "success" : "warning"}>{authMsg}</Text></div> : null}
      </Card>
    </Space>
  );
}

// ---------------------------------------------------------------- Scheduler
function SchedulerPanel(props: { projectId: string; plans: SchedulePlan[]; onChanged: () => Promise<void> }) {
  const [depForm] = Form.useForm();
  return (
    <Space direction="vertical" style={{ width: "100%" }} size={12}>
      <Card size="small" title="依赖注册（EpisodeDependency）">
        <Form layout="inline" form={depForm} onFinish={async (v) => {
          await registerDependency({ episode_id: v.episode_id, requires: (v.requires ?? "").split(",").map((x: string) => x.trim()).filter(Boolean) });
          depForm.resetFields();
          await props.onChanged();
        }}>
          <Form.Item name="episode_id" rules={[{ required: true, message: "Episode ID 必填" }]}><Input placeholder="Episode ID" /></Form.Item>
          <Form.Item name="requires"><Input placeholder="依赖资产，逗号分隔（如 character_version）" style={{ width: 280 }} /></Form.Item>
          <Form.Item><Button htmlType="submit">注册依赖</Button></Form.Item>
        </Form>
      </Card>
      <Card size="small" title="调度计划（Asset Ready → Prompt Ready → Resource Ready → Production Ready）">
        <Space style={{ marginBottom: 12 }}>
          <Button type="primary" onClick={() => void buildSchedulePlan(props.projectId, 2).then(props.onChanged)}>构建计划</Button>
        </Space>
        <Table
          rowKey="id"
          dataSource={props.plans}
          pagination={false}
          columns={[
            { title: "计划", dataIndex: "id", key: "id" },
            { title: "状态", dataIndex: "status", key: "status", render: (s: string) => <Tag color={STATUS_COLORS[s]}>{s}</Tag> },
            { title: "并行度", dataIndex: "parallelism", key: "parallel" },
            { title: "已排期", dataIndex: "scheduled", key: "scheduled", render: (ids: string[]) => ids.join("，") || "-" },
            { title: "受阻", dataIndex: "blocked", key: "blocked", render: (blocked: Array<{ episode_id: string; reasons: string[] }>) => blocked.length ? blocked.map((b) => <Tag key={b.episode_id} color="orange">{b.episode_id}:{b.reasons.join("/")}</Tag>) : "-" },
            { title: "审核人", dataIndex: "reviewer", key: "reviewer" },
            {
              title: "操作", key: "ops",
              render: (_, plan: SchedulePlan) => (
                <Space>
                  <Button size="small" disabled={plan.status !== "draft"} onClick={() => void approveSchedulePlan(plan.id, "producer").then(props.onChanged)}>审批</Button>
                  <Button size="small" disabled={plan.status !== "approved"} onClick={() => void dispatchSchedulePlan(plan.id).then(props.onChanged)}>Dispatch（入 TaskQueue）</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}

export default ProductionConsole;