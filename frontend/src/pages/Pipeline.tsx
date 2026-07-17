import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  InputNumber,
  List,
  message,
  Progress,
  Row,
  Select,
  Space,
  Steps,
  Tag,
  Typography,
  Upload,
} from "antd";
import {
  CloudUploadOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  StopOutlined,
  VideoCameraOutlined,
  WarningOutlined,
} from "@ant-design/icons";

const API_BASE = "http://localhost:8800/api/pipeline";
const { Dragger } = Upload;
const { Text, Title } = Typography;

type StageStatus = "pending" | "running" | "completed" | "warning" | "failed";

interface Novel {
  name: string;
  path: string;
  size: number;
  modified?: string;
}

interface StageItem {
  key: string;
  label: string;
  status: StageStatus;
  detail?: string;
  output?: string;
}

interface JobStatus {
  job_id: string;
  novel: string;
  status: string;
  progress: number;
  message: string;
  output_dir?: string;
  final_video?: string;
  warnings?: string[];
  stage_list?: StageItem[];
}

const statusText: Record<string, string> = {
  pending: "排队中",
  running: "生成中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const stepStatus = (status: StageStatus) => {
  if (status === "completed" || status === "warning") return "finish";
  if (status === "running") return "process";
  if (status === "failed") return "error";
  return "wait";
};

const stageColor = (status: StageStatus) => {
  if (status === "completed") return "success";
  if (status === "warning") return "warning";
  if (status === "running") return "processing";
  if (status === "failed") return "error";
  return "default";
};

const fileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

export default function Pipeline() {
  const [novels, setNovels] = useState<Novel[]>([]);
  const [selectedNovel, setSelectedNovel] = useState<string>();
  const [maxShots, setMaxShots] = useState(1);
  const [currentJob, setCurrentJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    fetchNovels();
  }, []);

  useEffect(() => {
    if (!polling || !currentJob?.job_id) return;
    const timer = window.setInterval(() => checkStatus(currentJob.job_id), 1500);
    return () => window.clearInterval(timer);
  }, [polling, currentJob?.job_id]);

  const selectedNovelInfo = useMemo(
    () => novels.find((item) => item.path === selectedNovel),
    [novels, selectedNovel]
  );

  const fetchNovels = async () => {
    try {
      const res = await fetch(`${API_BASE}/novels`);
      const data = await res.json();
      setNovels(data.novels || []);
      if (!selectedNovel && data.novels?.length) setSelectedNovel(data.novels[0].path);
    } catch {
      setNovels([]);
    }
  };

  const startPipeline = async (novelPath = selectedNovel) => {
    if (!novelPath) {
      message.warning("请先选择或上传小说文件");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ novel_path: novelPath, max_shots: maxShots }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setCurrentJob({
        job_id: data.job_id,
        novel: data.novel,
        status: "pending",
        progress: 0,
        message: "任务已创建",
        stage_list: [],
      });
      setPolling(true);
      message.success("V5 一键生成已启动");
    } catch (error: any) {
      message.error(`启动失败：${error.message || "未知错误"}`);
    } finally {
      setLoading(false);
    }
  };

  const checkStatus = async (jobId: string) => {
    try {
      const res = await fetch(`${API_BASE}/status/${jobId}`);
      if (!res.ok) return;
      const data = await res.json();
      setCurrentJob(data);
      if (["completed", "failed", "cancelled"].includes(data.status)) setPolling(false);
    } catch {
      // keep current display stable during transient backend reloads
    }
  };

  const cancelJob = async () => {
    if (!currentJob?.job_id) return;
    await fetch(`${API_BASE}/jobs/${currentJob.job_id}`, { method: "DELETE" });
    setCurrentJob({ ...currentJob, status: "cancelled", message: "已取消" });
    setPolling(false);
  };

  const uploadProps = {
    name: "file",
    multiple: false,
    action: `${API_BASE}/upload`,
    accept: ".txt",
    showUploadList: false,
    onChange: async (info: any) => {
      if (info.file.status === "uploading") {
        setLoading(true);
        return;
      }
      setLoading(false);
      if (info.file.status === "done") {
        await fetchNovels();
        const response = info.file.response;
        setCurrentJob({
          job_id: response.job_id,
          novel: response.novel || info.file.name,
          status: response.status || "pending",
          progress: 0,
          message: "上传完成，V5 已启动",
          stage_list: [],
        });
        setPolling(true);
        message.success("上传完成，已自动启动 V5");
      }
      if (info.file.status === "error") message.error("上传失败");
    },
    beforeUpload: (file: File) => {
      if (!file.name.endsWith(".txt")) {
        message.error("仅支持 .txt 小说文件");
        return Upload.LIST_IGNORE;
      }
      return true;
    },
  };

  const stages = currentJob?.stage_list || [];
  const percent = Math.round((currentJob?.progress || 0) * 100);
  const jobTagColor = currentJob?.status === "failed" ? "error" : currentJob?.status === "completed" ? "success" : "processing";

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto" }}>
      <Space direction="vertical" size={20} style={{ width: "100%" }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>V5 一键漫剧生成控制台</Title>
          <Text type="secondary">小说解析、首帧、尾帧、首尾帧视频和成片输出一次完成。</Text>
        </div>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={10}>
            <Card title="输入小说" extra={<Button icon={<ReloadOutlined />} onClick={fetchNovels}>刷新</Button>}>
              <Space direction="vertical" size={14} style={{ width: "100%" }}>
                <Dragger {...uploadProps} style={{ padding: 18 }}>
                  <p className="ant-upload-drag-icon"><CloudUploadOutlined /></p>
                  <p className="ant-upload-text">点击或拖拽 .txt 文件上传</p>
                  <p className="ant-upload-hint">上传后会自动启动 V5 流程</p>
                </Dragger>

                <Select
                  value={selectedNovel}
                  placeholder="选择已有小说"
                  onChange={setSelectedNovel}
                  options={novels.map((novel) => ({
                    label: `${novel.name} · ${fileSize(novel.size)}`,
                    value: novel.path,
                  }))}
                  style={{ width: "100%" }}
                />

                <Space style={{ width: "100%", justifyContent: "space-between" }}>
                  <Text>每章镜头数</Text>
                  <InputNumber min={1} max={6} value={maxShots} onChange={(value) => setMaxShots(value || 1)} />
                </Space>

                {selectedNovelInfo && (
                  <Alert
                    type="info"
                    showIcon
                    icon={<FileTextOutlined />}
                    message={selectedNovelInfo.name}
                    description={selectedNovelInfo.path}
                  />
                )}

                <Button
                  type="primary"
                  size="large"
                  icon={<PlayCircleOutlined />}
                  loading={loading}
                  block
                  onClick={() => startPipeline()}
                >
                  启动 V5 一键生成
                </Button>
              </Space>
            </Card>
          </Col>

          <Col xs={24} lg={14}>
            <Card
              title="阶段进度"
              extra={currentJob && <Tag color={jobTagColor}>{statusText[currentJob.status] || currentJob.status}</Tag>}
            >
              {currentJob ? (
                <Space direction="vertical" size={16} style={{ width: "100%" }}>
                  <div>
                    <Text type="secondary">任务 {currentJob.job_id} · {currentJob.novel}</Text>
                    <Progress percent={percent} status={currentJob.status === "failed" ? "exception" : currentJob.status === "completed" ? "success" : "active"} />
                    <Text>{currentJob.message}</Text>
                  </div>

                  <Steps
                    direction="vertical"
                    size="small"
                    current={stages.findIndex((stage) => stage.status === "running")}
                    items={stages.map((stage) => ({
                      title: stage.label,
                      status: stepStatus(stage.status) as any,
                      description: (
                        <Space direction="vertical" size={4}>
                          <Space>
                            <Tag color={stageColor(stage.status)}>{stage.status}</Tag>
                            <Text type="secondary">{stage.detail}</Text>
                          </Space>
                          {stage.output && <Text copyable code>{stage.output}</Text>}
                        </Space>
                      ),
                    }))}
                  />

                  {!!currentJob.warnings?.length && (
                    <Alert
                      type="warning"
                      showIcon
                      icon={<WarningOutlined />}
                      message="生成告警"
                      description={currentJob.warnings.join("；")}
                    />
                  )}

                  {currentJob.final_video && (
                    <Alert
                      type="success"
                      showIcon
                      icon={<VideoCameraOutlined />}
                      message="实际视频文件已生成"
                      description={<Text copyable code>{currentJob.final_video}</Text>}
                    />
                  )}

                  {(currentJob.status === "pending" || currentJob.status === "running") && (
                    <Button danger icon={<StopOutlined />} onClick={cancelJob}>取消任务</Button>
                  )}
                </Space>
              ) : (
                <Alert
                  type="info"
                  showIcon
                  message="等待启动"
                  description="选择小说后点击启动，或上传新小说自动开始。"
                />
              )}
            </Card>
          </Col>
        </Row>

        <Card title="已有小说">
          <List
            dataSource={novels}
            locale={{ emptyText: "novels 目录中暂无 .txt 文件" }}
            renderItem={(novel) => (
              <List.Item
                actions={[
                  <Button key="run" icon={<PlayCircleOutlined />} onClick={() => startPipeline(novel.path)}>生成</Button>,
                ]}
              >
                <List.Item.Meta
                  avatar={<FileTextOutlined />}
                  title={novel.name}
                  description={`${fileSize(novel.size)} · ${novel.path}`}
                />
              </List.Item>
            )}
          />
        </Card>
      </Space>
    </div>
  );
}
