import { request } from "@/api/client";

export interface VisionHealth {
  module: string;
  status: string;
  analyzer_initialized: boolean;
  scorer_initialized: boolean;
  clip_available: boolean | null;
  threshold: number;
  max_retries: number;
}

export const QUALITY_DIMENSIONS = [
  ["character_consistency", "人物一致性"],
  ["composition_score", "构图与画面"],
  ["style_consistency", "风格一致性"],
  ["technical_quality", "技术质量"],
  ["expression_match", "表情匹配"],
  ["camera_match", "机位匹配"],
] as const;

export interface NormalizedQualityReport {
  hasReport: boolean;
  overallScore: number | null;
  passed: boolean | null;
  issues: string[];
  suggestions: string[];
  dimensions: Array<{ key: string; label: string; score: number }>;
}

function normalizedScore(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 10) {
    return null;
  }
  return value <= 1 ? value : value / 10;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

export function normalizeQualityReport(value: unknown): NormalizedQualityReport {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {
      hasReport: false,
      overallScore: null,
      passed: null,
      issues: [],
      suggestions: [],
      dimensions: [],
    };
  }
  const report = value as Record<string, unknown>;
  const overallScore = normalizedScore(report.overall_score);
  const passed = typeof report.passed === "boolean" ? report.passed : null;
  const issues = stringList(report.issues);
  const suggestions = stringList(report.suggestions);
  const dimensions = QUALITY_DIMENSIONS.flatMap(([key, label]) => {
    const score = normalizedScore(report[key]);
    return score === null ? [] : [{ key, label, score }];
  });
  return {
    hasReport:
      overallScore !== null || passed !== null || issues.length > 0 ||
      suggestions.length > 0 || dimensions.length > 0,
    overallScore,
    passed,
    issues,
    suggestions,
    dimensions,
  };
}

export const visionApi = {
  health: () => request<VisionHealth>("/vision/health"),
};
