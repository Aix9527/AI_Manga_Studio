"""AI_Manga_Studio v1.0 Phase 6-9：平台/公司/创意生态/基础设施（聚合核心）.

Phase 6：Project/IP/Template/Cost
Phase 7：CEO/Marketing/Finance/Audience
Phase 8：Creative Brain（Idea/Originality/Emotion Curve）
Phase 9：Worker Registry / Render Scheduler / Certification
"""

from __future__ import annotations

import json
from pathlib import Path


def _load_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_dict(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ----------------------------------------------------------------- Phase 6
class ProjectManager:
    """多项目管理（GPT Phase 6 Project Operating System）。"""

    PROJECT_TYPES = ["NOVEL_ADAPTATION", "MANGA", "SHORT_DRAMA", "ADVERTISEMENT", "FILM"]

    def __init__(self, root: str | Path = "storage/platform"):
        self.root = Path(root)
        self._projects: dict[str, dict] = _load_dict(self.root / "projects.json")

    def create(self, *, owner_id: str, name: str, project_type: str,
               genre: str = "", style: str = "") -> dict:
        if project_type not in self.PROJECT_TYPES:
            raise ValueError(f"invalid project type: {project_type}")
        pid = f"PRJ-{len(self._projects) + 1:03d}"
        project = {"id": pid, "owner_id": owner_id, "name": name, "type": project_type,
                   "genre": genre, "style": style, "status": "planning"}
        self._projects[pid] = project
        _save_dict(self.root / "projects.json", self._projects)
        return project

    def list(self, owner_id: str | None = None) -> list[dict]:
        rows = list(self._projects.values())
        if owner_id:
            rows = [r for r in rows if r.get("owner_id") == owner_id]
        return rows


class IPManager:
    """IP 资产管理（GPT Phase 6 IP Asset OS）。"""

    def __init__(self, root: str | Path = "storage/platform"):
        self.root = Path(root)
        self._assets: dict[str, dict] = _load_dict(self.root / "ip_assets.json")

    def register(self, *, ip_id: str, name: str, asset_type: str,
                 version: str = "v1", usage: list | None = None) -> dict:
        asset = {"name": name, "type": asset_type, "version": version,
                 "usage": usage or [], "ip_id": ip_id}
        key = f"{ip_id}:{name}"
        self._assets[key] = asset
        _save_dict(self.root / "ip_assets.json", self._assets)
        return asset

    def assets(self, ip_id: str) -> list[dict]:
        return [a for k, a in self._assets.items() if k.startswith(ip_id)]


class TemplateMarket:
    """模板市场（GPT Phase 6 Template Store）。"""

    TEMPLATES = {
        "短剧": ["霸总短剧模板", "玄幻逆袭模板", "悬疑模板", "恐怖模板"],
        "导演": ["诺兰风格", "宫崎骏风格", "赛博朋克风格", "古装电影风格"],
        "镜头": ["英雄登场", "反派出现", "战斗高潮", "情感告白"],
    }

    def list(self, category: str | None = None) -> dict:
        if category:
            return {category: self.TEMPLATES.get(category, [])}
        return self.TEMPLATES


# ----------------------------------------------------------------- Phase 7
class StudioCouncil:
    """AI 制片委员会（GPT Phase 7）：CEO 决策 + 市场 + 财务 + 观众。"""

    def __init__(self):
        pass

    def ceo_decide(self, *, market_signals: dict) -> dict:
        """CEO：根据市场信号决定做什么内容。"""
        trend = market_signals.get("trend", "玄幻")
        audience = market_signals.get("audience", "18-35 男性")
        return {
            "project": {
                "name": f"《{trend}觉醒》",
                "type": trend,
                "episodes": 12,
                "priority": "high",
            },
            "audience": audience,
            "reason": f"市场趋势 {trend}，目标受众 {audience}",
        }

    def finance_estimate(self, *, episodes: int = 12, cost_per_episode: float = 25.0) -> dict:
        total = episodes * cost_per_episode
        return {
            "budget": round(total, 2),
            "estimated_revenue_range": [round(total * 4, 2), round(total * 10, 2)],
            "roi_note": "预计收益 4-10 倍成本",
        }

    def audience_test(self, *, opening: str, hook: str = "") -> dict:
        """AI 观众测试：预测完播率 + 风险。"""
        length = len(opening)
        retention = min(95, 70 + length // 10 + (10 if hook else 0))
        risk = []
        if not hook:
            risk.append("缺少开头钩子")
        if retention < 70:
            risk.append("第 4 分钟节奏可能下降")
        return {"predicted_retention": retention, "risk": risk}


# ----------------------------------------------------------------- Phase 8
class CreativeBrain:
    """AI 创意大脑（GPT Phase 8）：创意生成 + 原创检测 + 情绪曲线。"""

    def generate_ideas(self, *, market: list[str]) -> list[dict]:
        ideas = []
        for m in market[:3]:
            ideas.append({
                "title": f"《{m}·新纪元》",
                "type": m,
                "core": f"{m}题材 + 逆袭成长 + 时间循环",
                "hook": "第一集最后 30 秒出现时间循环",
            })
        return ideas

    def originality_check(self, *, story: str, common_tropes: list[str]) -> dict:
        matches = sum(1 for t in common_tropes if t in story)
        score = max(30, 100 - matches * 18)
        improve = ["增加世界规则", "强化角色矛盾"] if score < 80 else []
        return {"originality_score": score, "improve": improve}

    def emotion_curve(self, *, duration_minutes: int = 5) -> dict:
        """情绪曲线（5 分钟：震撼→疑问→冲突→高潮→反转）。"""
        beats = [
            {"time": "0:00", "emotion": "震撼"},
            {"time": "1:00", "emotion": "疑问"},
            {"time": "2:00", "emotion": "冲突"},
            {"time": "3:30", "emotion": "高潮"},
            {"time": f"{duration_minutes}:00", "emotion": "反转"},
        ]
        return {"beats": beats, "note": "中间平淡时自动增加冲突节点"}


# ----------------------------------------------------------------- Phase 9
class WorkerRegistry:
    """Worker 注册中心（GPT Phase 9，类 Kubernetes）。"""

    def __init__(self, root: str | Path = "storage/workers"):
        self.root = Path(root)
        self._workers: dict[str, dict] = _load_dict(self.root / "workers.json")

    def register(self, *, worker_id: str, worker_type: str, gpu: str,
                 memory_gb: int, models: list[str], healthy: bool = True) -> dict:
        worker = {"id": worker_id, "type": worker_type, "gpu": gpu,
                  "memory_gb": memory_gb, "models": models, "healthy": healthy}
        self._workers[worker_id] = worker
        _save_dict(self.root / "workers.json", self._workers)
        return worker

    def find(self, *, worker_type: str | None = None, model: str | None = None) -> list[dict]:
        rows = [w for w in self._workers.values() if w.get("healthy")]
        if worker_type:
            rows = [w for w in rows if w.get("type") == worker_type]
        if model:
            rows = [w for w in rows if model in w.get("models", [])]
        return rows


class RenderScheduler:
    """AI 渲染调度器：关键场景 → 高性能 Worker；普通 → 低成本。"""

    def route(self, *, task_type: str, important: bool = False) -> str:
        if task_type == "video":
            return "high_gpu" if important else "standard_gpu"
        if task_type == "image":
            return "low_gpu"
        return "standard_gpu"


class FilmCertifier:
    """AI Film Certification（GPT Phase 9 质量认证）。"""

    WEIGHTS = {"technical": 0.2, "character": 0.2, "motion": 0.2,
               "cinematic": 0.2, "audience": 0.2}

    def certify(self, **scores: float) -> dict:
        total = sum(scores.get(k, 0) * w for k, w in self.WEIGHTS.items())
        total = round(total, 1)
        grade = "S" if total >= 90 else "A" if total >= 80 else "B" if total >= 65 else "C"
        return {"certificate": grade, "score": total, "level": {
            "S": "电影级", "A": "商业短剧", "B": "普通内容", "C": "需重做"}[grade]}
