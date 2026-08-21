"""Prompt Evolution engine (Phase 13.6, GPT spec).

完播率/点赞/评论/收藏 → Prompt Score → 候选 → 人工审批 → 新版本。
遵守全局冻结约束：auto_learning=false / auto_apply=false；进化候选
绝不自动生效，必须经人工审批后生成新版本（不改动已锁定版本）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.prompt_os.model import (
    EvolutionRecord,
    PromptMetric,
    ShotDesign,
)

_DEFAULT_WEIGHTS = {"completion": 0.5, "like": 0.2, "comment": 0.15, "favorite": 0.15}
_CANDIDATE_MIN_SAMPLES = 10
_CANDIDATE_MIN_SCORE = 0.55


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class PromptEvolution:
    """采集指标、聚合 Score、提出候选、审批后生成新版本。"""

    def __init__(
        self,
        root: str | Path = "storage/prompt_os",
        *,
        weights: dict | None = None,
        min_samples: int = _CANDIDATE_MIN_SAMPLES,
        min_score: float = _CANDIDATE_MIN_SCORE,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.weights = weights or dict(_DEFAULT_WEIGHTS)
        self.min_samples = min_samples
        self.min_score = min_score
        self._metrics: dict[str, dict] = self._load("metrics.json")
        self._records: dict[str, dict] = self._load("evolution.json")

    # ------------------------------------------------------------ io
    def _load(self, name: str) -> dict[str, dict]:
        path = self.root / name
        import json
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save(self, name: str, data: dict[str, dict]) -> None:
        import json
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ------------------------------------------------------------ metrics
    def record_metric(
        self,
        *,
        shot_design_id: str,
        project_id: str = "",
        episode_id: str = "",
        completion_rate: float = 0.0,
        like_rate: float = 0.0,
        comment_rate: float = 0.0,
        favorite_rate: float = 0.0,
        views: int = 0,
    ) -> dict:
        metric = PromptMetric(
            id=_new_id("PM"),
            shot_design_id=shot_design_id,
            project_id=project_id,
            episode_id=episode_id,
            completion_rate=max(0.0, min(1.0, completion_rate)),
            like_rate=max(0.0, min(1.0, like_rate)),
            comment_rate=max(0.0, min(1.0, comment_rate)),
            favorite_rate=max(0.0, min(1.0, favorite_rate)),
            views=max(0, views),
            created_at=_now(),
        )
        self._metrics[metric.id] = metric.to_dict()
        self._save("metrics.json", self._metrics)
        return metric.to_dict()

    def _metrics_for(self, shot_design_id: str) -> list[PromptMetric]:
        return [PromptMetric.from_dict(raw) for raw in self._metrics.values()
                if raw.get("shot_design_id") == shot_design_id]

    def score(self, shot_design_id: str) -> dict:
        """按镜头聚合 Prompt Score（含样本数与分数明细）。"""
        rows = self._metrics_for(shot_design_id)
        if not rows:
            return {"shot_design_id": shot_design_id, "samples": 0, "score": 0.0,
                    "completion": 0.0, "like": 0.0, "comment": 0.0, "favorite": 0.0, "views": 0}
        n = len(rows)
        def _avg(key: str) -> float:
            return round(sum(getattr(r, key) for r in rows) / n, 4)
        avg_score = round(sum(r.prompt_score(self.weights) for r in rows) / n, 4)
        return {
            "shot_design_id": shot_design_id,
            "samples": n,
            "score": avg_score,
            "completion": _avg("completion_rate"),
            "like": _avg("like_rate"),
            "comment": _avg("comment_rate"),
            "favorite": _avg("favorite_rate"),
            "views": sum(r.views for r in rows),
        }

    def leaderboard(self, limit: int = 20) -> list[dict]:
        ids = sorted({raw.get("shot_design_id") for raw in self._metrics.values()})
        scored = [self.score(did) for did in ids if self.score(did)["samples"] > 0]
        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------ candidates
    def propose_candidates(self, shot_designs: dict[str, ShotDesign]) -> list[dict]:
        """Score 达标 → 生成候选（人工审批门，不自动应用）。"""
        created: list[dict] = []
        for design_id, design in shot_designs.items():
            stats = self.score(design_id)
            if stats["samples"] < self.min_samples:
                continue
            if stats["score"] < self.min_score:
                continue
            existing = [r for r in self._records.values()
                        if r.get("shot_design_id") == design_id and r.get("status") in ("candidate", "approved")]
            if existing:
                continue
            record = EvolutionRecord(
                id=_new_id("EV"),
                shot_design_id=design_id,
                score=stats["score"],
                samples=stats["samples"],
                status="candidate",
                suggested_layers=self._suggest(design, stats),
                reason=f"Prompt Score {stats['score']:.3f}（样本 {stats['samples']}）达到候选门槛",
                created_at=_now(),
            )
            self._records[record.id] = record.to_dict()
            created.append(record.to_dict())
        self._save("evolution.json", self._records)
        return created

    def _suggest(self, design: ShotDesign, stats: dict) -> dict:
        """根据弱项维度给出升级建议（不改变原版本）。"""
        suggestions: dict[str, Any] = {}
        if stats["completion"] < 0.4:
            suggestions["director_intent"] = "强化开场钩子，缩短无效信息，增加情绪目标"
            suggestions["action"] = "动作更明确、单一目标驱动"
        if stats["like"] < 0.15:
            suggestions["composition"] = "增强视觉冲击：中心构图或引导线"
            suggestions["lighting"] = "提升轮廓光/逆光对比"
        if stats["comment"] < 0.1:
            suggestions["story"] = "埋设悬念与信息缺口，诱导讨论"
        if stats["favorite"] < 0.1:
            suggestions["style"] = "统一美术语言，提升收藏价值的视觉辨识度"
        return suggestions or {"director_intent": "保持当前表现，微调镜头节奏"}

    def list_records(self, status: str | None = None) -> list[dict]:
        rows = list(self._records.values())
        if status:
            rows = [r for r in rows if r.get("status") == status]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows

    def review(self, record_id: str, decision: str, reviewer: str = "human") -> dict:
        if decision not in ("approved", "rejected"):
            raise ValueError(f"decision 必须是 approved 或 rejected，收到 {decision}")
        raw = self._records.get(record_id)
        if not raw:
            raise KeyError(f"evolution record not found: {record_id}")
        if raw["status"] != "candidate":
            raise ValueError(f"只有 candidate 状态可以审批，当前 {raw['status']}")
        raw["status"] = decision
        raw["reviewer"] = reviewer
        raw["decided_at"] = _now()
        self._records[record_id] = raw
        self._save("evolution.json", self._records)
        return dict(raw)

    def apply(self, record_id: str, *, intelligence=None, shot_store=None) -> dict:
        """人工批准后生成 NEW VERSION（绝不原地修改）。"""
        raw = self._records.get(record_id)
        if not raw:
            raise KeyError(f"evolution record not found: {record_id}")
        if raw["status"] != "approved":
            raise ValueError(f"只有 approved 候选可以应用，当前 {raw['status']}")
        if raw.get("applied_version"):
            raise ValueError("该候选已应用，禁止重复应用")
        raw["status"] = "applied"
        raw["applied_version"] = _new_id("v")
        self._records[record_id] = raw
        self._save("evolution.json", self._records)
        return dict(raw)

    def stats(self) -> dict:
        statuses: dict[str, int] = {}
        for raw in self._records.values():
            statuses[raw.get("status", "tracking")] = statuses.get(raw.get("status", "tracking"), 0) + 1
        return {
            "metrics": len(self._metrics),
            "records": len(self._records),
            "by_status": statuses,
            "weights": self.weights,
            "min_samples": self.min_samples,
            "min_score": self.min_score,
            "auto_learning": False,
            "auto_apply": False,
        }