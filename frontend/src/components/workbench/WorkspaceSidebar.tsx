import React, { useState } from "react";
import {
  ApartmentOutlined,
  BookOutlined,
  ControlOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  ExportOutlined,
  PictureOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import { NavLink } from "react-router-dom";

import { useWorkspaceStore } from "@/state/workspaceStore";

interface SidebarItem {
  path: string;
  label: string;
  icon: typeof DashboardOutlined;
  badge?: "active_jobs" | "pending_reviews";
}

interface SidebarGroup {
  key: string;
  label: string;
  icon: typeof DashboardOutlined;
  items: readonly SidebarItem[];
}

/* GPT P4: 40+ 页面收敛为 5 个一级模块。
 * 项目 / 创作 / 制作 / 审片 / 设置 —— 旧路径全部保留（仅分组，不破坏路由）。 */
const groups: readonly SidebarGroup[] = [
  {
    key: "project",
    label: "项目",
    icon: DashboardOutlined,
    items: [
      { path: "/overview", label: "项目总览", icon: DashboardOutlined },
      { path: "/command-center", label: "生产指挥中心", icon: ControlOutlined },
      { path: "/production-intelligence", label: "生产智能", icon: ApartmentOutlined },
    ],
  },
  {
    key: "create",
    label: "创作",
    icon: BookOutlined,
    items: [
      { path: "/story", label: "故事与角色", icon: BookOutlined },
      { path: "/director", label: "分镜导演台", icon: VideoCameraOutlined },
      { path: "/creator", label: "AI 创作台", icon: ExperimentOutlined },
      { path: "/studio", label: "导演工作台", icon: ControlOutlined },
    ],
  },
  {
    key: "produce",
    label: "制作",
    icon: ThunderboltOutlined,
    items: [
      { path: "/production-studio-v1", label: "生产工作台", icon: VideoCameraOutlined },
      { path: "/production-console", label: "生产控制台", icon: ControlOutlined },
      { path: "/industrial", label: "工业资产", icon: ApartmentOutlined },
      { path: "/assets", label: "素材库", icon: PictureOutlined },
      { path: "/tasks", label: "生成任务", icon: ThunderboltOutlined, badge: "active_jobs" },
    ],
  },
  {
    key: "review",
    label: "审片",
    icon: SafetyCertificateOutlined,
    items: [
      { path: "/quality", label: "视觉质检", icon: SafetyCertificateOutlined, badge: "pending_reviews" },
      { path: "/export", label: "成片与导出", icon: ExportOutlined },
    ],
  },
  {
    key: "settings",
    label: "设置",
    icon: SettingOutlined,
    items: [
      { path: "/prompt-studio", label: "Prompt 中心", icon: ExperimentOutlined },
      { path: "/prompt-os", label: "Prompt OS", icon: ExperimentOutlined },
      { path: "/sop-center", label: "SOP 中心", icon: ApartmentOutlined },
      { path: "/workflow", label: "工作流总览", icon: ApartmentOutlined },
      { path: "/evolution", label: "导演进化", icon: ExperimentOutlined },
      { path: "/digital-twin", label: "数字孪生", icon: ApartmentOutlined },
      { path: "/knowledge-graph", label: "知识图谱", icon: ApartmentOutlined },
      { path: "/producer-agent", label: "AI 制片人", icon: ApartmentOutlined },
    ],
  },
];

const WorkspaceSidebar: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({
    settings: true, // 低频设置项默认收起
  });

  const toggle = (key: string) => {
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <aside className="wb-sidebar">
      <nav aria-label="项目工作区">
        <p className="wb-sidebar__label">工作区</p>
        {groups.map((group) => {
          const GroupIcon = group.icon;
          const isCollapsed = !!collapsed[group.key];
          const totalBadge = group.items.reduce(
            (sum, item) => sum + (item.badge ? (snapshot?.[item.badge] ?? 0) : 0),
            0,
          );
          return (
            <div className="wb-sidebar__group" key={group.key}>
              <button
                type="button"
                className="wb-sidebar__group-head"
                aria-expanded={!isCollapsed}
                onClick={() => toggle(group.key)}
              >
                <GroupIcon aria-hidden="true" />
                <span className="wb-sidebar__group-label">{group.label}</span>
                {totalBadge > 0 ? (
                  <span className="wb-sidebar__badge" aria-hidden="true">{totalBadge}</span>
                ) : null}
                <span className="wb-sidebar__group-caret" aria-hidden="true">
                  {isCollapsed ? "▸" : "▾"}
                </span>
              </button>
              {!isCollapsed ? (
                <ul>
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const count = item.badge ? (snapshot?.[item.badge] ?? 0) : 0;
                    const accessibleLabel =
                      count > 0 && item.badge === "active_jobs"
                        ? `${item.label}，${count} 个运行中`
                        : count > 0 && item.badge === "pending_reviews"
                          ? `${item.label}，${count} 个待审核`
                          : item.label;
                    return (
                      <li key={item.path}>
                        <NavLink
                          to={item.path}
                          aria-label={accessibleLabel}
                          className={({ isActive }) =>
                            `wb-sidebar__link wb-sidebar__link--child${
                              isActive ? " wb-sidebar__link--active" : ""
                            }`
                          }
                        >
                          <Icon aria-hidden="true" />
                          <span className="wb-sidebar__text">{item.label}</span>
                          {count > 0 ? (
                            <span className="wb-sidebar__badge" aria-hidden="true">{count}</span>
                          ) : null}
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </div>
          );
        })}
      </nav>
    </aside>
  );
};

export default WorkspaceSidebar;
