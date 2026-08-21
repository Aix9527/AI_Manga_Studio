"""Phase 15.2：真实生产反馈采集（Director Router / Prompt OS / ShotDNA）.

从 Production Intelligence generation_end 事件统计真实生产表现：
按 director / prompt_version / shot_dna_id 汇总 usage / success / quality，
并写回 ShotDNA 统计与独立反馈报告。只读统计 + 记录，不自动修改生成配置。
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path


def _load_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


class ProductionFeedbackCollector:
    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)

    def _events(self) -> dict:
        return _load_dict(self.root / "production_intelligence" / "events.json")

    def _shot_dna_library(self) -> dict:
        return _load_dict(self.root / "shot_dna" / "library.json")

    # ------------------------------------------------------------ collect
    def collect(self) -> dict:
        events = self._events()
        # 关联：generation_start 提供 director/prompt/dna，generation_end 提供质量/耗时
        start_meta: dict[str, dict] = {}
        for row in events.values():
            if row.get("event_type") != "generation_start":
                continue
            payload = row.get("payload", {}) or {}
            start_meta[row.get("shot_id", "")] = {
                "director": payload.get("director", "unknown"),
                "prompt": payload.get("prompt_version", "unknown"),
                "dna": payload.get("shot_dna_id", "unknown"),
            }
        director_stats: dict[str, dict] = {}
        prompt_stats: dict[str, dict] = {}
        dna_stats: dict[str, dict] = {}
        for row in events.values():
            if row.get("event_type") != "generation_end":
                continue
            payload = row.get("payload", {}) or {}
            quality = payload.get("quality")
            meta = start_meta.get(row.get("shot_id", ""), {})
            director = meta.get("director", payload.get("director", "unknown"))
            prompt = meta.get("prompt", payload.get("prompt_version", "unknown"))
            dna = meta.get("dna", payload.get("shot_dna_id", "unknown"))
            ok = bool(quality and quality >= 0.7)
            for bucket, key in ((director_stats, director), (prompt_stats, prompt), (dna_stats, dna)):
                entry = bucket.setdefault(key, {"usage": 0, "success": 0, "quality_sum": 0.0, "quality_samples": 0})
                entry["usage"] += 1
                if ok:
                    entry["success"] += 1
                if isinstance(quality, (int, float)):
                    entry["quality_sum"] += float(quality)
                    entry["quality_samples"] += 1
        def finalize(bucket: dict) -> list[dict]:
            rows = []
            for key, entry in bucket.items():
                rows.append({
                    "key": key,
                    "usage": entry["usage"],
                    "success_rate": round(entry["success"] / entry["usage"], 3),
                    "avg_quality": round(entry["quality_sum"] / entry["quality_samples"], 3) if entry["quality_samples"] else None,
                })
            return sorted(rows, key=lambda r: r["usage"], reverse=True)
        return {
            "directors": finalize(director_stats),
            "prompt_versions": finalize(prompt_stats),
            "shot_dna": finalize(dna_stats),
        }

    # ------------------------------------------------------------ write back
    def apply_shot_dna_stats(self) -> dict:
        """把真实 shot_dna 表现写回 ShotDNA 库（直接 dict 格式：{id: dna}）。"""
        stats = self.collect()
        library = self._shot_dna_library()
        entries = library if isinstance(library, dict) else {}
        applied = 0
        for row in stats["shot_dna"]:
            key = row["key"]
            if key in entries:
                entries[key]["usage_count"] = row["usage"]
                entries[key]["success_rate"] = row["success_rate"]
                applied += 1
        out_path = self.root / "shot_dna" / "library.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out_path)
        return {"applied": applied, "dna_entries": len(entries)}

    # ------------------------------------------------------------ report
    def report(self) -> dict:
        stats = self.collect()
        return {
            "director_router_performance": stats["directors"],
            "prompt_os_feedback": stats["prompt_versions"],
            "shot_dna_feedback": stats["shot_dna"],
            "note": "真实生产反馈：仅统计与记录，不自动修改 Director Router / Prompt / ShotDNA 配置（auto_apply=false）",
        }
