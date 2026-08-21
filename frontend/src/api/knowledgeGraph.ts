/**
 * Knowledge Graph API (GPT Priority 2).
 * 多源摄取 / 统计 / 检索 / 邻居 / 路径 / 智能推荐。
 */

import { request } from "@/api/client";

export interface KGNode {
  id: string;
  type: string;
  label: string;
  properties: Record<string, unknown>;
  project_id: string;
  created_at: string;
}

export interface KGStats {
  nodes: number;
  edges: number;
  node_types: string[];
  by_type: Record<string, number>;
  by_edge: Record<string, number>;
  by_project: Record<string, number>;
}

export interface KGNeighbors {
  node_id: string;
  depth: number;
  neighbors: Array<{ node: KGNode; edge: { type: string; properties: Record<string, unknown> } }>;
  count: number;
}

export interface KGPaths {
  from: string;
  to: string;
  paths: Array<Array<{ id: string; edge: string }>>;
}

export interface KGRecommend {
  node_id: string;
  recommendations: Array<{ node: KGNode; score: number }>;
  note: string;
}

export const kgStats = (): Promise<KGStats> => request("/knowledge-graph/stats");

export const kgIngest = (body: Record<string, unknown>): Promise<Record<string, unknown>> =>
  request("/knowledge-graph/ingest", { method: "POST", body: JSON.stringify(body) });

export const kgNodes = (params: Record<string, string> = {}): Promise<{ nodes: KGNode[] }> => {
  const query = new URLSearchParams(params).toString();
  return request(`/knowledge-graph/nodes${query ? `?${query}` : ""}`);
};

export const kgGetNode = (id: string): Promise<KGNode> =>
  request(`/knowledge-graph/nodes/${encodeURIComponent(id)}`);

export const kgNeighbors = (id: string, edgeType?: string): Promise<KGNeighbors> =>
  request(`/knowledge-graph/neighbors/${encodeURIComponent(id)}${edgeType ? `?edge_type=${edgeType}` : ""}`);

export const kgPaths = (fromId: string, toId: string): Promise<KGPaths> =>
  request(`/knowledge-graph/paths?from_id=${encodeURIComponent(fromId)}&to_id=${encodeURIComponent(toId)}`);

export const kgSearch = (q: string, limit = 20): Promise<{ query: string; results: KGNode[]; count: number }> =>
  request(`/knowledge-graph/search?q=${encodeURIComponent(q)}&limit=${limit}`);

export const kgRecommend = (id: string, limit = 5): Promise<KGRecommend> =>
  request(`/knowledge-graph/recommend/${encodeURIComponent(id)}?limit=${limit}`);
