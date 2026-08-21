"""AI_Manga_Studio v1.0 Phase 3：一致性引擎 + 自动修复 + 电影评分.

Character/Scene/Style/Motion 一致性检查、Repair Engine（问题→策略→重生成）、
Cinema Score（GPT Phase 3 加权评分）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _load_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


class IdentityLock:
    """角色一致性锁定（Character Identity Vector）。"""

    def __init__(self, root: str | Path = "storage/consistency"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, dict] = _load_dict(self.root / "identity_locks.json")

    def register(self, *, character: str, fixed: dict, embeddings: dict | None = None) -> dict:
        lock = {
            "id": character,
            "fixed": fixed,
            "embedding": embeddings or {},
        }
        self._locks[character] = lock
        self._save()
        return lock

    def lock_for(self, character: str) -> dict:
        lock = self._locks.get(character)
        if not lock:
            raise KeyError(f"no identity lock: {character}")
        return dict(lock)

    def check(self, *, character: str, observed: dict,
              face_similarity: float = 1.0) -> dict:
        """检测角色漂移：相似度 <0.75 失败；服装/道具变化失败。"""
        lock = self.lock_for(character)
        issues: list[str] = []
        if face_similarity < 0.75:
            issues.append("face_drift")
        fixed = lock.get("fixed", {})
        for key, expected in fixed.items():
            if key in observed and observed[key] != expected:
                issues.append(f"COSTUME_CHANGED:{key}")
        return {
            "character": character,
            "passed": not issues,
            "issues": issues,
            "face_similarity": face_similarity,
            "repair": ["enable_face_lock"] if "face_drift" in issues else [],
        }

    def _save(self) -> None:
        path = self.root / "identity_locks.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._locks, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


class SceneMemory:
    """场景一致性（Scene Bible）。"""

    def __init__(self, root: str | Path = "storage/consistency"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._scenes: dict[str, dict] = _load_dict(self.root / "scene_bible.json")

    def register_scene(self, *, scene: str, architecture: list, lighting: str, color: str) -> dict:
        data = {"architecture": architecture, "lighting": lighting, "color": color}
        self._scenes[scene] = data
        self._save()
        return data

    def scene_context(self, scene: str) -> dict:
        data = self._scenes.get(scene)
        if not data:
            raise KeyError(f"no scene bible: {scene}")
        return dict(data)

    def check(self, *, scene: str, observed: dict) -> dict:
        """场景漂移检测：关键建筑/灯光/色调必须一致。"""
        bible = self.scene_context(scene)
        issues: list[str] = []
        for key in ("architecture", "lighting", "color"):
            if key in observed and observed[key] != bible.get(key):
                issues.append(f"scene_drift:{key}")
        return {"scene": scene, "passed": not issues, "issues": issues,
                "repair": ["reinject_scene_context"] if issues else []}

    def _save(self) -> None:
        path = self.root / "scene_bible.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._scenes, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


class StyleLock:
    """风格一致性（Style DNA）。"""

    def __init__(self, root: str | Path = "storage/consistency"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._styles: dict[str, dict] = _load_dict(self.root / "style_dna.json")

    def register_style(self, *, project: str, style: dict) -> dict:
        self._styles[project] = style
        self._save()
        return style

    def style_prefix(self, project: str) -> str:
        style = self._styles.get(project)
        if not style:
            return ""
        return f"{style.get('style', '')}, {style.get('color', '')}, {style.get('lighting', '')}, no style drift"

    def _save(self) -> None:
        path = self.root / "style_dna.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._styles, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


class MotionMemory:
    """动作连续性（Motion State Memory）：上一镜状态继承。"""

    def __init__(self, root: str | Path = "storage/consistency"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._motions: dict[str, dict] = _load_dict(self.root / "motion_memory.json")

    def record(self, *, shot_id: str, body: dict) -> None:
        self._motions[shot_id] = body
        self._save()

    def previous(self, shot_id: str) -> dict | None:
        # 取上一镜（按顺序）
        ids = sorted(self._motions.keys())
        if not ids:
            return None
        return dict(self._motions[ids[-1]])

    def check(self, *, current: dict) -> dict:
        """动作连续性：上一镜关键部位状态应继承。"""
        prev = self.previous("")
        if not prev:
            return {"passed": True, "issues": []}
        issues = []
        for key, value in prev.get("body", {}).items():
            if key in current.get("body", {}) and current["body"][key] != value:
                issues.append(f"motion_break:{key}")
        return {"passed": not issues, "issues": issues,
                "repair": ["inherit_previous_motion"] if issues else []}

    def _save(self) -> None:
        path = self.root / "motion_memory.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._motions, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


class RepairEngine:
    """自动修复：失败类型 → 修复策略（GPT Phase 3）。"""

    STRATEGIES = {
        "face_drift": {"action": "IPAdapter strength +15%, face reference"},
        "COSTUME_CHANGED": {"action": "re-lock costume reference"},
        "scene_drift": {"action": "reinject scene_context"},
        "motion_break": {"action": "inherit previous motion, reduce complexity"},
        "motion_weak": {"action": "increase motion strength, longer shot"},
        "blur": {"action": "steps +5, denoise -0.05, upscale"},
        "flicker": {"action": "continuity enable, stable prompt"},
    }

    def __init__(self, root: str | Path = "storage/repair"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._failures: list[dict] = _load_dict(self.root / "failure_log.json").get("items", [])

    def repair(self, *, shot_id: str, issues: list[str]) -> dict:
        strategies = []
        for issue in issues:
            strategy = self.STRATEGIES.get(issue)
            if strategy:
                strategies.append({"issue": issue, **strategy})
        self._failures.append({"shot_id": shot_id, "issues": issues, "strategies": strategies})
        self._save()
        return {"shot_id": shot_id, "repair_plan": strategies,
                "rerun": bool(strategies)}

    def log(self) -> list[dict]:
        return list(self._failures)

    def _save(self) -> None:
        path = self.root / "failure_log.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": self._failures}, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


class CinemaJudge:
    """电影评分（GPT Phase 3/5：Final Score 加权）。"""

    WEIGHTS = {
        "visual_quality": 0.30,
        "character": 0.20,
        "motion": 0.15,
        "cinematic_language": 0.15,
        "emotion": 0.10,
        "continuity": 0.10,
    }

    def score(self, **scores: float) -> dict:
        total = 0.0
        detail = {}
        for key, weight in self.WEIGHTS.items():
            value = scores.get(key, 0.0)
            total += value * weight
            detail[key] = {"value": round(value, 2), "weight": weight}
        total = round(total, 1)
        level = "cinema" if total >= 85 else "commercial" if total >= 70 else "rework"
        return {
            "score": total,
            "level": level,
            "recommendation": "approve" if total >= 85 else "review" if total >= 70 else "rework",
            "detail": detail,
        }
