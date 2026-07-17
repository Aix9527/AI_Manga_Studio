import React, { useEffect, useState } from "react";
import {
  Card,
  Button,
  Table,
  Upload,
  Modal,
  Form,
  Input,
  message,
  Space,
  Tag,
  Typography,
  Divider,
} from "antd";
import {
  PlusOutlined,
  PlayCircleOutlined,
  UploadOutlined,
  FolderOpenOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import axios from "axios";

const { Title, Text } = Typography;

const API_BASE = "http://127.0.0.1:8800";

/* ── Types ─────────────────────────────────────── */

interface Project {
  id: string;
  name: string;
  status: string;
  chapter_count: number;
  shot_count: number;
  created_at: string;
}

interface CreateProjectForm {
  name: string;
  description: string;
}

/* ── Component ─────────────────────────────────── */

const HOME_STYLE: Record<string, React.CSSProperties> = {
  headerRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 24,
  },
  actionBar: { display: "flex", gap: 12 },
};

const statusColorMap: Record<string, string> = {
  idle: "default",
  generating: "processing",
  done: "success",
  failed: "error",
  paused: "warning",
};

const columns: ColumnsType<Project> = [
  { title: "Name", dataIndex: "name", key: "name", sorter: (a, b) => a.name.localeCompare(b.name) },
  { title: "Chapters", dataIndex: "chapter_count", key: "chapters", width: 100 },
  { title: "Shots", dataIndex: "shot_count", key: "shots", width: 80 },
  {
    title: "Status",
    dataIndex: "status",
    key: "status",
    width: 120,
    render: (s: string) => <Tag color={statusColorMap[s] ?? "default"}>{s.toUpperCase()}</Tag>,
  },
  { title: "Created", dataIndex: "created_at", key: "created", width: 180 },
  {
    title: "Action",
    key: "action",
    width: 180,
    render: (_: unknown, rec: Project) => (
      <Space>
        <Button size="small" icon={<PlayCircleOutlined />} type="primary">
          Generate
        </Button>
        <Button size="small" icon={<FolderOpenOutlined />}>
          Open
        </Button>
      </Space>
    ),
  },
];

const Home: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [novelModal, setNovelModal] = useState(false);
  const [currentProject, setCurrentProject] = useState<string>("");
  const [form] = Form.useForm<CreateProjectForm>();

  /* ── Fetch ────────────────────────────────── */

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get<{ projects: Project[] }>(
        `${API_BASE}/api/projects`
      );
      setProjects(data.projects || []);
    } catch {
      message.error("Failed to load projects");
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  /* ── Handlers ─────────────────────────────── */

  const handleCreate = async (values: CreateProjectForm) => {
    try {
      await axios.post(`${API_BASE}/api/projects`, values);
      message.success("Project created");
      setModalOpen(false);
      form.resetFields();
      fetchProjects();
    } catch {
      message.error("Failed to create project");
    }
  };

  const handleUploadNovel = () => {
    setNovelModal(false);
    message.success("Novel uploaded — ready for generation");
  };

  return (
    <div>
      <div style={HOME_STYLE.headerRow}>
        <Title level={4}>Projects</Title>
        <div style={HOME_STYLE.actionBar}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            New Project
          </Button>
        </div>
      </div>

      <Table
        dataSource={projects}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
        locale={{ emptyText: "No projects yet. Create one to start." }}
      />

      {/* ── New Project Modal ────────────────── */}
      <Modal
        title="Create New Project"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="name"
            label="Project Name"
            rules={[{ required: true, message: "Please input project name" }]}
          >
            <Input placeholder="e.g. My Manga Series" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} placeholder="Optional description" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Upload Novel Modal ───────────────── */}
      <Modal
        title="Upload Novel"
        open={novelModal}
        onCancel={() => setNovelModal(false)}
        footer={null}
      >
        <Upload.Dragger
          name="file"
          accept=".txt,.pdf,.docx"
          action={`${API_BASE}/api/projects/${currentProject}/novel`}
          onChange={(info) => {
            if (info.file.status === "done") {
              handleUploadNovel();
            }
          }}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined />
          </p>
          <p>Click or drag novel file here</p>
          <p style={{ color: "#888" }}>.txt / .pdf / .docx</p>
        </Upload.Dragger>
      </Modal>
    </div>
  );
};

export default Home;
