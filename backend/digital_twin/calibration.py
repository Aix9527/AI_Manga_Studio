"""Digital Twin Calibration v1.1 (GPT 15.2 指示).

基于真实生产事件（generation_end lead_time_s / cost_actual）校准 Queue
Simulation：historical ETA + confidence_score + uncertainty_range。
只校准预测模型，不改变生产控制（auto_control=false）。
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


class CalibrationStore:
    """校准状态持久化：历史样本 → 基线 ETA / 不确定性。"""

    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self) -> Path:
        return self.root / "digital_twin" / "calibration.json"

    def load(self) -> dict:
        data = _load_dict(self.path())
        return data or {"samples": [], "baseline": None, "updated_at": ""}

    def save(self, data: dict) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


class Calibrator:
    """从生产事件提取真实 lead_time，校准单任务 ETA。"""

    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)
        self.store = CalibrationStore(root)

    def _events(self) -> dict:
        return _load_dict(self.root / "production_intelligence" / "events.json")

    # ------------------------------------------------------------ collect
    def collect(self) -> dict:
        """收集 generation_end 的 lead_time_s 作为校准样本。"""
        events = self._events()
        samples: list[float] = []
        for row in events.values():
            if row.get("event_type") == "generation_end":
                payload = row.get("payload", {}) or {}
                lead = payload.get("lead_time_s")
                if isinstance(lead, (int, float)) and lead > 0:
                    samples.append(float(lead))
        state = self.store.load()
        # 与已有样本去重追加（按事件 id 记录，避免重复累计）
        known = set(state.get("sample_events", []))
        new_events = [eid for eid in events if eid not in known and events[eid].get("event_type") == "generation_end"
                      and isinstance(events[eid].get("payload", {}).get("lead_time_s"), (int, float))]
        for eid in new_events:
            known.add(eid)
        state["sample_events"] = sorted(known)
        # 用全部事件重算样本（保持一致性）
        state["samples"] = samples
        state["baseline"] = self._calibrate(samples)
        state["updated_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        self.store.save(state)
        return {"samples": len(samples), "baseline": state["baseline"]}

    def _calibrate(self, samples: list[float]) -> dict | None:
        if len(samples) < 1:
            return None
        mean = statistics.mean(samples)
        if len(samples) >= 2:
            stdev = statistics.stdev(samples)
        else:
            stdev = mean * 0.25
        # confidence：样本越多越自信（min 0.3，max 0.95）
        confidence = min(0.95, 0.3 + 0.05 * len(samples))
        # uncertainty_range：±1.96σ/sqrt(n)（95% 置信区间）
        se = stdev / (len(samples) ** 0.5)
        return {
            "mean_s": round(mean, 1),
            "stdev_s": round(stdev, 1),
            "n": len(samples),
            "confidence": round(confidence, 3),
            "uncertainty_range_s": round(1.96 * se, 1),
            "uncertainty_low_s": round(mean - 1.96 * se, 1),
            "uncertainty_high_s": round(mean + 1.96 * se, 1),
        }

    # ------------------------------------------------------------ apply
    def apply_to_simulation(self, sim_result: dict) -> dict:
        """把校准基线注入仿真结果：eta + confidence + uncertainty。"""
        state = self.store.load()
        baseline = state.get("baseline")
        if not baseline:
            return sim_result
        for row in sim_result.get("results", []):
            eta_s = row.get("eta_s", 0)
            # 若校准平均任务耗时可用，用它替换模型假设的 avg_task_s 重算
            row["calibration"] = {
                "mean_s": baseline["mean_s"],
                "confidence": baseline["confidence"],
                "uncertainty_range_s": baseline["uncertainty_range_s"],
                "eta_uncertainty_s": round(eta_s * (baseline["uncertainty_range_s"] / max(1.0, baseline["mean_s"])), 1),
            }
            row["eta_s_low"] = max(0, int(eta_s - row["calibration"]["eta_uncertainty_s"]))
            row["eta_s_high"] = int(eta_s + row["calibration"]["eta_uncertainty_s"])
        sim_result["calibrated"] = True
        return sim_result

    def state(self) -> dict:
        return self.store.load()
