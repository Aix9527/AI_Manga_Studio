"""Phase 15.2-E：Batch C A/B + Director/Prompt/ShotDNA 三维分析 + DT 校准。

输入：ProductionSnapshot v1（统一口径）+ feedback_stats（真实生产反馈）。
输出：E1 导演胜率 / E2 Prompt ROI / E3 ShotDNA 高成功模式 / E4 DT 校准 n=300。
auto_apply=false：只生成分析与候选，不自动修改任何配置。
"""

from __future__ import annotations

from pathlib import Path

try:
    from backend.production_pilot.feedback_stats import ProductionFeedbackCollector
    from backend.production_pilot.snapshot import ProductionSnapshot
    from backend.digital_twin.calibration import Calibrator
except Exception:  # noqa: BLE001
    ProductionFeedbackCollector = None
    ProductionSnapshot = None
    Calibrator = None


class PhaseEAnalyzer:
    """Phase 15.2-E 分析服务。"""

    def __init__(self, root: str | Path = "storage", outputs: str = "outputs/guixu2"):
        self.root = Path(root)
        self.outputs = Path(outputs)
        self._snap = ProductionSnapshot(root=str(self.root), outputs=str(self.outputs)) if ProductionSnapshot else None
        self._feedback = ProductionFeedbackCollector(root=str(self.root)) if ProductionFeedbackCollector else None

    # ------------------------------------------------------------ E1
    def director_analysis(self, feedback: dict) -> list:
        rows = []
        for item in feedback.get("director_router_performance", []):
            key = item.get("key", "unknown")
            quality = item.get("avg_quality")
            rows.append({
                "director": key,
                "usage": item.get("usage", 0),
                "success_rate": item.get("success_rate", 0.0),
                "avg_quality": round(quality, 3) if isinstance(quality, (int, float)) else None,
            })
        # 按质量排序（质量优先，usage 作参考）
        rows.sort(key=lambda r: (r["avg_quality"] or 0), reverse=True)
        return rows

    # ------------------------------------------------------------ E2
    def prompt_roi(self, feedback: dict, shots: list) -> list:
        # 从快照镜头按 prompt_version 聚合真实成本/返工
        cost_by_pv: dict[str, list] = {}
        for s in shots:
            pv = s.get("prompt_version") or "unknown"
            cost_by_pv.setdefault(pv, []).append(s.get("gpu_cost") or 0.0)

        rows = []
        for item in feedback.get("prompt_os_feedback", []):
            key = item.get("key", "unknown")
            costs = cost_by_pv.get(key, [])
            avg_cost = round(sum(costs) / len(costs), 4) if costs else None
            rows.append({
                "prompt_version": key,
                "usage": item.get("usage", 0),
                "success_rate": item.get("success_rate", 0.0),
                "avg_quality": item.get("avg_quality"),
                "avg_gpu_cost": avg_cost,
            })
        rows.sort(key=lambda r: (r["avg_quality"] or 0), reverse=True)
        return rows

    # ------------------------------------------------------------ E3
    def shot_dna_mining(self, feedback: dict, shots: list) -> list:
        rows = []
        for item in feedback.get("shot_dna_feedback", []):
            key = item.get("key", "unknown")
            usage = item.get("usage", 0)
            if usage < 5:
                continue  # 样本不足不推荐
            q = item.get("avg_quality")
            rows.append({
                "shot_dna": key,
                "usage": usage,
                "success_rate": item.get("success_rate", 0.0),
                "avg_quality": q,
                "confidence": {
                    "sample_based": usage >= 30,
                    "quality_variance": round(max(0.0, abs((q or 0.0) - 0.82)), 2),
                },
                "candidate": bool(item.get("success_rate", 0) >= 0.9 and usage >= 20),
                "review_required": True,
            })
        rows.sort(key=lambda r: (r["success_rate"] or 0, r["usage"]), reverse=True)
        return rows

    # ------------------------------------------------------------ E4
    def dt_calibration(self) -> dict:
        if Calibrator is None:
            return {"status": "unavailable"}
        cal = Calibrator(root=str(self.root))
        state = cal.state()
        baseline = state.get("baseline", {})
        return {
            "status": "PASS" if baseline.get("n", 0) >= 300 else "PENDING",
            "n": baseline.get("n", 0),
            "mean_s": baseline.get("mean_s"),
            "stdev_s": baseline.get("stdev_s"),
            "confidence": baseline.get("confidence"),
            "uncertainty_range_s": baseline.get("uncertainty_range_s"),
            "target": "n>=300",
        }

    # ------------------------------------------------------------ 汇总
    def analyze(self) -> dict:
        feedback = self._feedback.report() if self._feedback else {}
        shots = self._snap._shot_details() if self._snap else []
        return {
            "phase": "15.2-E",
            "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
            "governance": {"auto_apply": False, "auto_modify": False, "human_review": True},
            "E1_director_analysis": self.director_analysis(feedback),
            "E2_prompt_roi": self.prompt_roi(feedback, shots),
            "E3_shot_dna_mining": self.shot_dna_mining(feedback, shots),
            "E4_dt_calibration": self.dt_calibration(),
            "recommendation": self._recommend(feedback, shots),
        }

    def _recommend(self, feedback: dict, shots: list) -> dict:
        directors = self.director_analysis(feedback)
        best_director = directors[0] if directors else None
        prompts = self.prompt_roi(feedback, shots)
        best_prompt = prompts[0] if prompts else None
        dnas = self.shot_dna_mining(feedback, shots)
        top_dna = next((d for d in dnas if d.get("candidate")), dnas[0] if dnas else None)
        cal = self.dt_calibration()
        return {
            "best_director": best_director["director"] if best_director else None,
            "best_prompt": best_prompt["prompt_version"] if best_prompt else None,
            "recommended_shot_dna": top_dna["shot_dna"] if top_dna else None,
            "shot_dna_candidates": [d["shot_dna"] for d in dnas if d.get("candidate")],
            "dt_calibration": cal.get("status"),
            "next": "Phase15.2-F 剩余700镜工业排产（以 ProductionSnapshot v1 + 上述分析结论为基础）",
        }


_analyzer = PhaseEAnalyzer()


def get_phase_e() -> dict:
    return _analyzer.analyze()
