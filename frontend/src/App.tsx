import React, { useState } from "react";
import { Layout, Menu, Typography, theme } from "antd";
import {
  HomeOutlined,
  RocketOutlined,
  DashboardOutlined,
  VideoCameraOutlined,
  DownloadOutlined,
} from "@ant-design/icons";
import Home from "./pages/Home";
import Monitor from "./pages/Monitor";
import ShotManager from "./pages/ShotManager";
import Download from "./pages/Download";
import Pipeline from "./pages/Pipeline";

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

type TabKey = "home" | "monitor" | "shots" | "download" | "pipeline";

interface TabConfig {
  key: TabKey;
  icon: React.ReactNode;
  label: string;
  component: React.ReactNode;
}

const tabs: TabConfig[] = [
  { key: "home", icon: <HomeOutlined />, label: "总览", component: <Home /> },
  { key: "pipeline", icon: <RocketOutlined />, label: "V5 一键生成", component: <Pipeline /> },
  { key: "monitor", icon: <DashboardOutlined />, label: "算力监控", component: <Monitor /> },
  { key: "shots", icon: <VideoCameraOutlined />, label: "镜头管理", component: <ShotManager /> },
  { key: "download", icon: <DownloadOutlined />, label: "成片下载", component: <Download /> },
];

const App: React.FC = () => {
  const [activeKey, setActiveKey] = useState<TabKey>("home");
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const activeTab = tabs.find((t) => t.key === activeKey);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        breakpoint="lg"
        collapsedWidth="64"
        style={{ background: "#001529" }}
      >
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Title level={5} style={{ color: "#fff", margin: 0 }}>
            AI 漫剧工坊
          </Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[activeKey]}
          items={tabs.map((t) => ({
            key: t.key,
            icon: t.icon,
            label: t.label,
          }))}
          onClick={({ key }) => setActiveKey(key as TabKey)}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            padding: "0 24px",
            background: colorBgContainer,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          <Title level={4} style={{ margin: 0 }}>
            {activeTab?.label ?? "AI 漫剧工坊 V5"}
          </Title>
          <span style={{ color: "#888", fontSize: 13 }}>
            V5 &middot; 本地部署
          </span>
        </Header>

        <Content
          style={{
            margin: 24,
            padding: 24,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
            minHeight: 360,
            overflow: "auto",
          }}
        >
          {activeTab?.component}
        </Content>
      </Layout>
    </Layout>
  );
};

export default App;
