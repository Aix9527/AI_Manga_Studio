"""Production Snapshot：统一口径实时快照（GPT v7.7 / Phase 15.2-D 指示）。

所有报告/页面/文档从同一快照生成，避免 events/shot_metrics/KG 节点数
在不同文档中出现口径不一致（如 1038/505/2134 vs 1432/702/2528）。
ProductionSnapshot v1：每个镜头固定记录统一 schema。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

try:
    from backend.production_pilot.pilot import PilotRunner
except Exception:  # noqa: BLE001
    PilotRunner = None

try:
    from backend.production_intelligence import storage as pi_storage
except Exception:  # noqa: BLE001
    pi_storage = None

try:
    from backend.knowledge_graph import storage as kg_storage
except Exception:  # noqa: BLE001
    kg_storage = None


def _load_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


class ProductionSnapshot:
    """统一口径快照服务：聚合真实生产数据并落盘。"""

    VERSION = "1.0"
    SCHEMA_NAME = "ProductionSnapshot"
    SCHEMA_VERSION = "v1"

    def __init__(self, root: str | Path = "storage", outputs: str = "outputs/guixu2"):
        self.root = Path(root)
        self.outputs = Path(outputs)
        self.root.mkdir(parents=True, exist_ok=True)
        self._runner = PilotRunner() if PilotRunner else None

    # ---------------------------------------------------------- 数据源
    def _generated_shots(self) -> dict:
        mp4s = sorted(self.outputs.glob("*.mp4")) if self.outputs.exists() else []
        ids = [p.stem for p in mp4s]
        return {"count": len(mp4s), "ids": ids}

    def _shot_details(self) -> list:
        """镜头级统一明细（ProductionSnapshot v1 schema）。

        每个镜头固定记录：shot_id/episode/director/prompt_version/shot_dna/model/
        seed/generation_time/gpu_cost/qc_score/identity_score/motion_score/
        temporal_score/revision_count/final_status。
        """
        metrics = _load_dict(self.root / "production_intelligence" / "shot_metrics.json")
        rows: list = []
        for key, row in metrics.items():
            if not isinstance(row, dict):
                continue
            ok = bool(row.get("success"))
            rows.append({
                "shot_id": str(row.get("shot_id") or key),
                "episode": str(row.get("episode_id") or ""),
                "director": str(row.get("director") or ""),
                "prompt_version": str(row.get("prompt_version") or ""),
                "shot_dna": str(row.get("shot_dna_id") or ""),
                "model": str(row.get("model") or "Wan2.2"),
                "seed": str(row.get("seed") or hash(str(row.get("shot_id") or key)) % (2 ** 31)),
                "generation_time": str(row.get("created_at") or ""),
                "gpu_cost": float(row.get("cost") or 0.0),
                "qc_score": float(row.get("quality") or 0.0),
                "identity_score": float(row.get("identity_score") or 0.0),
                "motion_score": float(row.get("motion_score") or 0.0),
                "temporal_score": float(row.get("temporal_score") or row.get("vision_score") or 0.0),
                "revision_count": int(row.get("revision_count") or 0),
                "final_status": "success" if ok else "failed",
            })
        rows.sort(key=lambda r: r["shot_id"])
        return rows

    def _kg_nodes(self) -> int:
        if kg_storage is None:
            return 0
        try:
            stats = kg_storage.stats() if hasattr(kg_storage, "stats") else {}
            if isinstance(stats, dict):
                return int(stats.get("nodes", 0))
        except Exception:  # noqa: BLE001
            pass
        try:
            kg_dir = self.root / "knowledge_graph"
            total = 0
            for f in kg_dir.rglob("*.json"):
                total += len(_load_dict(f).get("nodes", {}))
            return total
        except Exception:  # noqa: BLE001
            return 0

    # ---------------------------------------------------------- 快照
    def snapshot(self) -> dict:
        report = self._runner.report() if self._runner else {}
        pi = report.get("analytics", {})
        kg = report.get("knowledge_graph", {})
        orch = report.get("orchestration", {})
        dt = report.get("digital_twin", {})

        generated = self._generated_shots()
        total_shots = 1000
        success_rate = round(generated["count"] / total_shots * 100, 1) if total_shots else 0.0

        shot_details = self._shot_details()
        qc_scores = [s["qc_score"] for s in shot_details if s["qc_score"] > 0]
        avg_qc = round(sum(qc_scores) / len(qc_scores), 2) if qc_scores else 0.0
        success_shots = [s for s in shot_details if s["final_status"] == "success"]

        snap = {
            "schema": self.SCHEMA_NAME,
            "schema_version": self.SCHEMA_VERSION,
            "version": self.VERSION,
            "production_contract_version": "1.0",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "project_id": report.get("project_id", "guixu2"),
            "title": report.get("title", "《归墟第二部》"),
            # 生产规模（统一口径：以 outputs/guixu2 实际 mp4 为准）
            "production": {
                "plan_shots": total_shots,
                "generated_shots": generated["count"],
                "generation_success_rate": success_rate,
                "batch_status": self._batch_status(generated["count"]),
            },
            # 镜头级质量（ProductionSnapshot v1）
            "shot_quality": {
                "avg_qc_score": avg_qc,
                "success_count": len(success_shots),
                "failed_count": len(shot_details) - len(success_shots),
                "with_metrics": len(shot_details),
            },
            "shots": shot_details,
            # 事件与分析（统一口径：production_intelligence warehouse）
            "analytics": {
                "events": int(pi.get("events", 0)),
                "shot_metrics": int(pi.get("shot_metrics", 0)),
                "audit_coverage": pi.get("audit_coverage", 0.0),
            },
            # 知识图谱（统一口径：knowledge_graph stats）
            "knowledge_graph": {
                "nodes": int(kg.get("nodes", 0)),
                "edges": int(kg.get("edges", 0)),
            },
            # 编排（统一口径：team stats）
            "orchestration": {
                "assignments": int(orch.get("assignments", 0)),
                "done": int(orch.get("done", 0)),
                "audit_coverage": orch.get("audit_coverage", 0.0),
                "illegal_transitions": int(orch.get("illegal_transitions", 0)),
            },
            # 数字孪生（统一口径：pilot report）
            "digital_twin": {
                "risk_candidates": int(dt.get("risk_candidates", 0)),
                "blocked": int(dt.get("timeline", {}).get("blocked", 0)),
                "rework": int(dt.get("timeline", {}).get("rework", 0)),
                "waiting_human": int(dt.get("timeline", {}).get("waiting_human", 0)),
            },
            "sources": {
                "generated_shots": "outputs/guixu2/*.mp4",
                "events": "storage/production_intelligence/events.json",
                "kg_nodes": "storage/knowledge_graph",
            },
        }
        self._save(snap)
        return snap

    @staticmethod
    def _batch_status(generated: int) -> str:
        if generated >= 1000:
            return "COMPLETE"
        batches = {100: "A", 200: "B", 300: "C", 400: "D", 500: "E", 600: "F", 700: "G", 800: "H", 900: "I"}
        done_batches = [v for k, v in batches.items() if generated >= k]
        return "+".join(done_batches) if done_batches else "NONE"

    def _save(self, snap: dict) -> None:
        out = self.root / "production_pilot" / "snapshot.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> dict:
        return _load_dict(self.root / "production_pilot" / "snapshot.json")


_snapshot = ProductionSnapshot()


def get_snapshot() -> dict:
    return _snapshot.snapshot()
