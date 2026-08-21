/**
 * Prompt Studio (Phase 13.4-A, GPT spec).
 *
 * Versioned Prompt Intelligence: 模板库（Character/World/Shot Composer）、
 * Prompt Version + Diff + Review + Approval（人工审批门）+ A/B Test + 提示词试炼。
 */

import React, { useEffect, useState } from "react";

import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Modal,
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
  ExperimentOutlined,
  FileTextOutlined,
  PartitionOutlined,
} from "@ant-design/icons";

import {
  addPromptReview,
  composeCharacter,
  composeShot,
  composeWorld,
  createABTest,
  createPromptTemplate,
  createPromptVersion,
  decideAB,
  diffPromptVersions,
  listABTests,
  listPromptTemplates,
  listPromptReviews,
  promptStats,
  recordABResult,
  setPromptVersionStatus,
  type ComposeResult,
  type PromptABTestRecord,
  type PromptTemplateRecord,
} from "@/api/promptIntelligence";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;
const { TextArea } = Input;

const KIND_OPTIONS = [
  { value: "character", label: "角色 Character" },
  { value: "world", label: "世界 World" },
  { value: "shot", label: "镜头 Shot" },
  { value: "generic", label: "通用 Generic" },
];

const STATUS_COLORS: Record<string, string> = {
  draft: "default", approved: "blue", locked: "green",
  pending: "orange", rejected: "red", running: "processing", completed: "success",
};

const PromptStudio: React.FC = () => {
  const [templates, setTemplates] = useState<PromptTemplateRecord[]>([]);
  const [tests, setTests] = useState<PromptABTestRecord[]>([]);
  const [stats, setStats] = useState<{ templates: number; versions: number; reviews: number; ab_tests: number; locked_versions: number } | null>(null);
  const [reviews, setReviews] = useState<{ id: string; template_id: string; version_id: string; reviewer: string; status: string; comments: string }[]>([]);
  const [error, setError] = useState("");
  const [diff, setDiff] = useState<string[] | null>(null);
  const [diffVersions, setDiffVersions] = useState<{ from: string; to: string }>({ from: "", to: "" });
  const [composeResult, setComposeResult] = useState<ComposeResult | null>(null);

  const load = async () => {
    const [t, ab, s, r] = await Promise.all([
      listPromptTemplates(), listABTests(), promptStats(), listPromptReviews(),
    ]).catch((err: unknown) => {
      setError(userMessage(err));
      return [null, null, null, null];
    });
    setTemplates(t?.templates ?? []);
    setTests(ab?.tests ?? []);
    setStats(s ?? null);
    setReviews(r?.reviews ?? []);
  };

  useEffect(() => {
    void load();
  }, []);

  const notify = (ok: boolean, message: string) => {
    setError(ok ? "" : message);
    void load();
  };

  const handleCreateTemplate = async (values: {
    name: string; kind: string; base_template: string; negative_prompt?: string; quality_tags?: string; variables?: string; description?: string;
  }) => {
    try {
      await createPromptTemplate({
        name: values.name,
        kind: values.kind,
        base_template: values.base_template,
        negative_prompt: values.negative_prompt ?? "",
        quality_tags: values.quality_tags ?? "",
        variables: (values.variables ?? "").split(",").map((v) => v.trim()).filter(Boolean),
        description: values.description ?? "",
      });
      notify(true, "");
    } catch (err) {
      notify(false, userMessage(err));
    }
  };

  const handleNewVersion = async (templateId: string, values: { base_template: string; negative_prompt?: string; quality_tags?: string; notes?: string }) => {
    try {
      await createPromptVersion(templateId, {
        base_template: values.base_template,
        negative_prompt: values.negative_prompt ?? "",
        quality_tags: values.quality_tags ?? "",
        notes: values.notes ?? "",
      });
      notify(true, "");
    } catch (err) {
      notify(false, userMessage(err));
    }
  };

  const handleStatus = async (templateId: string, versionId: string, status: "approved" | "locked") => {
    try {
      await setPromptVersionStatus(templateId, versionId, { status, approved_by: "导演" });
      notify(true, "");
    } catch (err) {
      notify(false, userMessage(err));
    }
  };

  const handleReview = async (templateId: string, versionId: string, values: Record<string, string>) => {
    try {
      await addPromptReview(templateId, versionId, {
        reviewer: values.reviewer,
        status: values.status as "pending" | "approved" | "rejected",
        comments: values.comments ?? "",
      });
      notify(true, "");
    } catch (err) {
      notify(false, userMessage(err));
    }
  };

  const handleDiff = async (templateId: string) => {
    if (!diffVersions.from || !diffVersions.to || diffVersions.from === diffVersions.to) return;
    try {
      const result = await diffPromptVersions(templateId, diffVersions.to, diffVersions.from);
      setDiff(result.diff);
    } catch (err) {
      notify(false, userMessage(err));
    }
  };

  const handleCreateAB = async (values: { name?: string; template_id: string; base_version: string; variant_version: string; metric?: string }) => {
    try {
      await createABTest(values);
      notify(true, "");
    } catch (err) {
      notify(false, userMessage(err));
    }
  };

  const handleCompose = async (kind: string, values: Record<string, string>) => {
    try {
      if (kind === "character") {
        setComposeResult(await composeCharacter({ character_id: values.character_id, asset_type: values.asset_type ?? "portrait", asset_key: values.asset_key ?? "" }));
      } else if (kind === "world") {
        setComposeResult(await composeWorld({ project_id: values.project_id ?? "", world_id: values.world_id ?? "", scene_id: values.scene_id ?? "" }));
      } else {
        setComposeResult(await composeShot({ dna_id: values.dna_id ?? "", features: values.features ? Object.fromEntries(values.features.split(",").map((pair) => pair.split(":").map((p) => p.trim()))) : {}, top_k: 1 }));
      }
      setError("");
    } catch (err) {
      setComposeResult(null);
      setError(userMessage(err));
    }
  };

  const templateColumns = [
    { title: "模板", dataIndex: "name", key: "name" },
    { title: "类型", dataIndex: "kind", key: "kind", render: (kind: string) => <Tag>{kind}</Tag> },
    { title: "版本数", dataIndex: "versions", key: "versions", render: (versions: PromptTemplateRecord["versions"]) => versions.length },
    { title: "生产版本", dataIndex: "active_version", key: "active_version", render: (v: string) => (v ? <Tag color="green">{v}</Tag> : <Text type="secondary">未锁定</Text>) },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Title level={4} style={{ marginTop: 0 }}>
        <FileTextOutlined /> Prompt Studio
        <Text type="secondary" style={{ fontSize: 13, marginLeft: 12 }}>
          Phase 13.4-A：可版本化、可审批、可 A/B 的 Prompt Intelligence
        </Text>
      </Title>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={6}><Card size="small"><Statistic title="模板" value={stats?.templates ?? 0} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="版本" value={stats?.versions ?? 0} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="锁定生产版本" value={stats?.locked_versions ?? 0} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="A/B 测试" value={stats?.ab_tests ?? 0} /></Card></Col>
      </Row>

      <Tabs
        defaultActiveKey="templates"
        items={[
          {
            key: "templates",
            label: <Space><PartitionOutlined />模板库与版本</Space>,
            children: (
              <Space direction="vertical" style={{ width: "100%" }} size={12}>
                <Card size="small" title="创建模板（v1 草稿）">
                  <Form layout="inline" onFinish={handleCreateTemplate}>
                    <Form.Item name="name" rules={[{ required: true, message: "模板名必填" }]}>
                      <Input placeholder="模板名，如 character_portrait" style={{ width: 220 }} />
                    </Form.Item>
                    <Form.Item name="kind" initialValue="character" rules={[{ required: true }]}>
                      <Select options={KIND_OPTIONS} style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item name="base_template" rules={[{ required: true, message: "模板正文必填" }]}>
                      <Input placeholder="模板正文，支持 {变量}" style={{ width: 320 }} />
                    </Form.Item>
                    <Form.Item name="negative_prompt">
                      <Input placeholder="负面提示（可空）" style={{ width: 240 }} />
                    </Form.Item>
                    <Form.Item name="quality_tags">
                      <Input placeholder="质量标签（可空）" style={{ width: 240 }} />
                    </Form.Item>
                    <Form.Item name="variables">
                      <Input placeholder="变量，逗号分隔（可空）" style={{ width: 200 }} />
                    </Form.Item>
                    <Form.Item>
                      <Button type="primary" htmlType="submit">创建</Button>
                    </Form.Item>
                  </Form>
                </Card>

                <Card size="small" title="模板列表（点击展开版本管理）">
                  <Table
                    rowKey="id"
                    dataSource={templates}
                    columns={templateColumns}
                    pagination={false}
                    expandable={{
                      expandedRowRender: (template) => (
                        <Space direction="vertical" style={{ width: "100%" }} size={8}>
                          <Form layout="inline" onFinish={(v) => handleNewVersion(template.id, v)}>
                            <Form.Item name="base_template" rules={[{ required: true, message: "正文必填" }]}>
                              <Input placeholder="新版本正文" style={{ width: 360 }} />
                            </Form.Item>
                            <Form.Item name="negative_prompt"><Input placeholder="负面提示" style={{ width: 200 }} /></Form.Item>
                            <Form.Item name="quality_tags"><Input placeholder="质量标签" style={{ width: 200 }} /></Form.Item>
                            <Form.Item name="notes"><Input placeholder="变更说明" style={{ width: 200 }} /></Form.Item>
                            <Form.Item><Button htmlType="submit">新建版本</Button></Form.Item>
                          </Form>
                          <Table
                            rowKey="version_id"
                            size="small"
                            pagination={false}
                            dataSource={template.versions}
                            columns={[
                              { title: "版本", dataIndex: "version_id", key: "version_id" },
                              { title: "父版本", dataIndex: "parent_version", key: "parent_version" },
                              { title: "状态", dataIndex: "status", key: "status", render: (s: string) => <Tag color={STATUS_COLORS[s]}>{s}</Tag> },
                              { title: "审批人", dataIndex: "approved_by", key: "approved_by" },
                              { title: "哈希", dataIndex: "content_hash", key: "content_hash", render: (h: string) => <Text code style={{ fontSize: 11 }}>{h}</Text> },
                              {
                                title: "操作", key: "actions",
                                render: (_, v: PromptTemplateRecord["versions"][number]) => (
                                  <Space>
                                    <Button size="small" disabled={v.status !== "draft"} onClick={() => handleStatus(template.id, v.version_id, "approved")}>审批</Button>
                                    <Button size="small" disabled={v.status !== "approved"} onClick={() => handleStatus(template.id, v.version_id, "locked")}>锁定生产</Button>
                                    <ModalForm
                                      title="人工审核"
                                      buttonLabel="审核"
                                      fields={[
                                        { name: "reviewer", label: "审核人", required: true },
                                        { name: "status", label: "结论", required: true, select: ["approved", "rejected", "pending"] },
                                        { name: "comments", label: "意见", textarea: true },
                                      ]}
                                      onSubmit={(values) => handleReview(template.id, v.version_id, values)}
                                    />
                                  </Space>
                                ),
                              },
                            ]}
                          />
                          <Space>
                            <Select
                              placeholder="对比基准版本"
                              style={{ width: 160 }}
                              options={template.versions.map((v) => ({ value: v.version_id, label: v.version_id }))}
                              onChange={(from) => setDiffVersions((prev) => ({ ...prev, from }))}
                            />
                            <Select
                              placeholder="对比目标版本"
                              style={{ width: 160 }}
                              options={template.versions.map((v) => ({ value: v.version_id, label: v.version_id }))}
                              onChange={(to) => setDiffVersions((prev) => ({ ...prev, to }))}
                            />
                            <Button onClick={() => handleDiff(template.id)}>查看 Diff</Button>
                          </Space>
                          {diff ? (
                            <pre style={{ maxHeight: 200, overflow: "auto", background: "#fafafa", padding: 8, fontSize: 12 }}>
                              {diff.length ? diff.join("\n") : "（无差异）"}
                            </pre>
                          ) : null}
                        </Space>
                      ),
                    }}
                  />
                </Card>

                <Card size="small" title="审核记录">
                  <Table
                    rowKey="id"
                    size="small"
                    pagination={false}
                    dataSource={reviews}
                    columns={[
                      { title: "模板", dataIndex: "template_id", key: "template_id" },
                      { title: "版本", dataIndex: "version_id", key: "version_id" },
                      { title: "审核人", dataIndex: "reviewer", key: "reviewer" },
                      { title: "结论", dataIndex: "status", key: "status", render: (s: string) => <Tag color={STATUS_COLORS[s]}>{s}</Tag> },
                      { title: "意见", dataIndex: "comments", key: "comments" },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
          {
            key: "ab",
            label: <Space><ExperimentOutlined />A/B 测试</Space>,
            children: (
              <Space direction="vertical" style={{ width: "100%" }} size={12}>
                <Card size="small" title="新建 A/B 测试（基准 vs 变体）">
                  <ABTestForm templates={templates} onCreate={handleCreateAB} />
                </Card>
                <Card size="small" title="测试列表">
                  <Table
                    rowKey="id"
                    dataSource={tests}
                    pagination={false}
                    columns={[
                      { title: "名称", dataIndex: "name", key: "name" },
                      { title: "模板", dataIndex: "template_id", key: "template_id" },
                      { title: "基准", dataIndex: "base_version", key: "base_version" },
                      { title: "变体", dataIndex: "variant_version", key: "variant_version" },
                      { title: "指标", dataIndex: "metric", key: "metric" },
                      { title: "状态", dataIndex: "status", key: "status", render: (s: string) => <Tag color={STATUS_COLORS[s]}>{s}</Tag> },
                      { title: "结果", dataIndex: "results", key: "results", render: (r: PromptABTestRecord["results"]) => (
                          <Space size={8}>
                            {Object.entries(r).map(([arm, v]) => (
                              <Tag key={arm} color={arm === "base" ? "blue" : "purple"}>
                                {arm} {v.samples}次 {v.score}
                              </Tag>
                            ))}
                          </Space>
                        ) },
                      { title: "胜者", dataIndex: "winner", key: "winner" },
                      {
                        title: "操作", key: "actions",
                        render: (_, test: PromptABTestRecord) => (
                          <Space>
                            <Button size="small" disabled={test.status === "completed"} onClick={() => recordABResult(test.id, { arm: "base", success: true }).then(() => void load()).catch((err) => setError(userMessage(err)))}>
                              基准+1
                            </Button>
                            <Button size="small" disabled={test.status === "completed"} onClick={() => recordABResult(test.id, { arm: "variant", success: true }).then(() => void load()).catch((err) => setError(userMessage(err)))}>
                              变体+1
                            </Button>
                            <Button size="small" disabled={test.status === "completed"} onClick={() => decideAB(test.id).then(() => void load()).catch((err) => setError(userMessage(err)))}>
                              裁决
                            </Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
          {
            key: "compose",
            label: <Space><ExperimentOutlined />提示词试炼</Space>,
            children: (
              <Card size="small" title="Composer 试炼（消费 13.1 冻结资产）">
                <ComposeForm onCompose={handleCompose} />
                {composeResult ? (
                  <Descriptions column={1} bordered size="small" style={{ marginTop: 16 }}>
                    <Descriptions.Item label="类型">{composeResult.kind}</Descriptions.Item>
                    <Descriptions.Item label="模板版本">{composeResult.version_id || "内置默认"}</Descriptions.Item>
                    <Descriptions.Item label="来源">{composeResult.source_id}</Descriptions.Item>
                    <Descriptions.Item label="正向提示"><pre style={{ whiteSpace: "pre-wrap" }}>{composeResult.positive_prompt}</pre></Descriptions.Item>
                    <Descriptions.Item label="负面提示"><pre style={{ whiteSpace: "pre-wrap" }}>{composeResult.negative_prompt}</pre></Descriptions.Item>
                  </Descriptions>
                ) : null}
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
};

function ModalForm(props: {
  title: string;
  buttonLabel: string;
  fields: Array<{ name: string; label: string; required?: boolean; select?: string[]; textarea?: boolean }>;
  onSubmit: (values: Record<string, string>) => void;
}) {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<Record<string, string>>();
  return (
    <>
      <Button size="small" onClick={() => setOpen(true)}>{props.buttonLabel}</Button>
      <Modal
        open={open}
        title={props.title}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => {
            props.onSubmit(values);
            setOpen(false);
          }}
        >
          {props.fields.map((field) => (
            <Form.Item key={field.name} name={field.name} label={field.label} rules={field.required ? [{ required: true, message: `${field.label}必填` }] : []}>
              {field.select ? (
                <Select options={field.select.map((v) => ({ value: v, label: v }))} />
              ) : field.textarea ? (
                <TextArea rows={2} />
              ) : (
                <Input />
              )}
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </>
  );
}

function ABTestForm(props: {
  templates: PromptTemplateRecord[];
  onCreate: (values: { name?: string; template_id: string; base_version: string; variant_version: string; metric?: string }) => void;
}) {
  const [form] = Form.useForm();
  const selected = Form.useWatch("template_id", form);
  const versions = props.templates.find((t) => t.id === selected)?.versions ?? [];
  return (
    <Form
      form={form}
      layout="inline"
      onFinish={props.onCreate}
    >
      <Form.Item name="name"><Input placeholder="测试名称（可空）" style={{ width: 180 }} /></Form.Item>
      <Form.Item name="template_id" rules={[{ required: true, message: "模板必选" }]}>
        <Select
          placeholder="选择模板"
          style={{ width: 220 }}
          options={props.templates.map((t) => ({ value: t.id, label: `${t.name}（${t.kind}）` }))}
        />
      </Form.Item>
      <Form.Item name="base_version" rules={[{ required: true, message: "基准版本必选" }]}>
        <Select placeholder="基准版本" style={{ width: 140 }} options={versions.map((v) => ({ value: v.version_id, label: v.version_id }))} />
      </Form.Item>
      <Form.Item name="variant_version" rules={[{ required: true, message: "变体版本必选" }]}>
        <Select placeholder="变体版本" style={{ width: 140 }} options={versions.map((v) => ({ value: v.version_id, label: v.version_id }))} />
      </Form.Item>
      <Form.Item name="metric" initialValue="success_rate">
        <Select style={{ width: 160 }} options={[{ value: "success_rate", label: "成功率" }, { value: "vision_accept_rate", label: "视觉通过率" }, { value: "identity_score", label: "一致性得分" }]} />
      </Form.Item>
      <Form.Item><Button type="primary" htmlType="submit">创建测试</Button></Form.Item>
    </Form>
  );
}

function ComposeForm(props: { onCompose: (kind: string, values: Record<string, string>) => void }) {
  const [kind, setKind] = useState("character");
  const [form] = Form.useForm<Record<string, string>>();
  return (
    <>
      <Select
        value={kind}
        style={{ width: 200, marginBottom: 12 }}
        options={KIND_OPTIONS}
        onChange={(value) => setKind(value)}
      />
      <Form
        form={form}
        layout="inline"
        onFinish={(values) => props.onCompose(kind, values)}
      >
        {kind === "character" ? (
          <>
            <Form.Item name="character_id" rules={[{ required: true, message: "角色ID必填" }]}><Input placeholder="角色ID（Bible）" /></Form.Item>
            <Form.Item name="asset_type" initialValue="portrait">
              <Select style={{ width: 160 }} options={[{ value: "portrait", label: "人像" }, { value: "view", label: "三视图" }, { value: "expression", label: "表情" }, { value: "action", label: "动作" }]} />
            </Form.Item>
            <Form.Item name="asset_key"><Input placeholder="资产 key（如 front/smile/walk）" /></Form.Item>
          </>
        ) : kind === "world" ? (
          <>
            <Form.Item name="project_id"><Input placeholder="项目ID" /></Form.Item>
            <Form.Item name="world_id"><Input placeholder="World ID（可空）" /></Form.Item>
            <Form.Item name="scene_id"><Input placeholder="Scene ID（可空）" /></Form.Item>
          </>
        ) : (
          <>
            <Form.Item name="dna_id"><Input placeholder="Shot DNA ID（可空）" /></Form.Item>
            <Form.Item name="features"><Input placeholder="特征 category:action,scene:battle" /></Form.Item>
          </>
        )}
        <Form.Item><Button type="primary" htmlType="submit">生成提示词</Button></Form.Item>
      </Form>
    </>
  );
}

export default PromptStudio;