"""AI_Manga_Studio v1.0 Phase 5：自进化生产系统（导演/提示词进化 + 经验/失败记忆）. """

from __future__ import annotations

import json
import statistics
from pathlib import Path


def _load_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _save_list(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class ExperienceMemory:
    """影视经验记忆（AI 导演大脑）：成功镜头模式。"""

    def __init__(self, root: str | Path = "storage/evolution"):
        self.root = Path(root)
        self._patterns: list[dict] = _load_list(self.root / "experience.json")

    def record(self, *, pattern_type: str, solution: dict, score: float) -> dict:
        entry = {"type": pattern_type, "solution": solution, "score": score}
        self._patterns.append(entry)
        _save_list(self.root / "experience.json", self._patterns)
        return entry

    def best(self, pattern_type: str) -> dict | None:
        rows = [p for p in self._patterns if p.get("type") == pattern_type]
        return max(rows, key=lambda p: p.get("score", 0)) if rows else None

    def stats(self) -> dict:
        return {"patterns": len(self._patterns),
                "best_score": max((p.get("score", 0) for p in self._patterns), default=0)}


class PromptEvolution:
    """提示词自进化：Prompt → 评分 → 优化版本 → 保存最佳。"""

    def __init__(self, root: str | Path = "storage/evolution"):
        self.root = Path(root)
        self._versions: list[dict] = _load_list(self.root / "prompt_versions.json")

    def evolve(self, *, key: str, prompt: str, score: float, improved: str) -> dict:
        entry = {"key": key, "prompt": prompt, "score": score, "improved": improved}
        self._versions.append(entry)
        _save_list(self.root / "prompt_versions.json", self._versions)
        return entry

    def best(self, key: str) -> str | None:
        rows = [v for v in self._versions if v.get("key") == key]
        best = max(rows, key=lambda v: v.get("score", 0)) if rows else None
        return best.get("improved") or best.get("prompt") if best else None


class FailurePattern:
    """失败经验库（GPT：工业系统必须保存失败）。"""

    def __init__(self, root: str | Path = "storage/evolution"):
        self.root = Path(root)
        self._failures: list[dict] = _load_list(self.root / "failure_patterns.json")

    def record(self, *, failure_type: str, cause: str, fix: str) -> dict:
        entry = {"type": failure_type, "cause": cause, "fix": fix, "count": 1}
        existing = next((f for f in self._failures if f.get("type") == failure_type), None)
        if existing:
            existing["count"] += 1
        else:
            self._failures.append(entry)
        _save_list(self.root / "failure_patterns.json", self._failures)
        return entry

    def fix_for(self, failure_type: str) -> str | None:
        row = next((f for f in self._failures if f.get("type") == failure_type), None)
        return row.get("fix") if row else None


class DirectorEvolution:
    """导演进化引擎：类型 → 最佳方案（结合经验 + Prompt 进化）。"""

    def __init__(self, root: str | Path = "storage/evolution"):
        self.memory = ExperienceMemory(root)
        self.prompts = PromptEvolution(root)
        self.failures = FailurePattern(root)

    def learn(self, *, pattern_type: str, solution: dict, score: float) -> dict:
        return self.memory.record(pattern_type=pattern_type, solution=solution, score=score)

    def direct(self, pattern_type: str) -> dict:
        best = self.memory.best(pattern_type)
        prompt = self.prompts.best(pattern_type)
        return {
            "pattern": pattern_type,
            "solution": best.get("solution", {}) if best else {},
            "best_score": best.get("score", 0) if best else 0,
            "prompt": prompt or "",
        }
