import type { ElementType } from "react";
import {
  ApartmentOutlined,
  AppstoreOutlined,
  DashboardOutlined,
  NodeIndexOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";

export interface StudioNavItem {
  path: string;
  label: string;
  shortLabel: string;
  icon: ElementType;
}

export const STUDIO_NAVIGATION: StudioNavItem[] = [
  { path: "/project", label: "项目", shortLabel: "项目台", icon: DashboardOutlined },
  { path: "/story-assets", label: "故事·资产", shortLabel: "故事资产台", icon: AppstoreOutlined },
  { path: "/director", label: "分镜导演台", shortLabel: "导演台", icon: VideoCameraOutlined },
  { path: "/canvas", label: "高级画布", shortLabel: "精修", icon: NodeIndexOutlined },
  { path: "/timeline", label: "时间线·质检", shortLabel: "时间线", icon: ApartmentOutlined },
];

export const LEGACY_ROUTE_REDIRECTS: Record<string, string> = {
  "/overview": "/project",
  "/story": "/story-assets",
  "/assets": "/story-assets",
  "/characters": "/story-assets",
  "/story-graph": "/story-assets",
  "/storyboard": "/director",
  "/creator": "/project",
  "/studio": "/project",
  "/evolution": "/director",
  "/industrial": "/canvas",
  "/prompt-studio": "/canvas",
  "/production-console": "/project",
  "/prompt-os": "/canvas",
  "/production-intelligence": "/timeline",
  "/knowledge-graph": "/story-assets",
  "/digital-twin": "/director",
  "/command-center": "/project",
  "/producer-agent": "/project",
  "/workflow": "/canvas",
  "/sop-center": "/project",
  "/production-studio-v1": "/project",
  "/tasks": "/timeline",
  "/quality": "/timeline",
  "/export": "/timeline",
  "/pipeline": "/timeline",
};
