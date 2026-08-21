"""Production Digital Twin service (Phase 14.2, GPT spec).

mode=simulation_and_visibility_only / auto_control=false：
Runtime Mirror + Timeline + Heatmap + Queue Simulation + Risk Prediction。
"""

from __future__ import annotations

from backend.digital_twin.calibration import Calibrator
from backend.digital_twin.risk import RiskPredictor
from backend.digital_twin.runtime import HeatmapBuilder, RuntimeMirror, TimelineBuilder
from backend.digital_twin.simulation import SCENARIOS, QueueSimulator


class DigitalTwinService:
    def __init__(self, root: str = "storage"):
        self.mirror = RuntimeMirror(root)
        self.timeline_builder = TimelineBuilder(root)
        self.heatmap_builder = HeatmapBuilder(root)
        self.simulator = QueueSimulator(root)
        self.risk = RiskPredictor(root)
        self.calibrator = Calibrator(root)

    def current_state(self, project_id: str | None = None) -> dict:
        return self.mirror.current_state(project_id=project_id)

    def timeline(self, project_id: str | None = None) -> dict:
        return self.timeline_builder.timeline(project_id=project_id)

    def heatmap(self, project_id: str | None = None) -> dict:
        return self.heatmap_builder.heatmap(project_id=project_id)

    def simulate(self, scenario_keys: list[str] | None = None) -> dict:
        result = self.simulator.simulate(scenario_keys=scenario_keys)
        self.calibrator.collect()
        return self.calibrator.apply_to_simulation(result)

    def calibration(self) -> dict:
        return self.calibrator.collect()

    def calibration_state(self) -> dict:
        return self.calibrator.state()

    def scenarios(self) -> dict:
        return SCENARIOS

    def predict(self, project_id: str | None = None) -> dict:
        candidates = self.risk.predict(project_id=project_id)
        return {"candidates": candidates, "count": len(candidates), "auto_control": False}

    def risk_candidates(self, status: str | None = None) -> dict:
        return {"candidates": self.risk.list_candidates(status=status)}

    def dismiss_risk(self, candidate_id: str) -> dict:
        return self.risk.dismiss(candidate_id)

    def overview(self) -> dict:
        return {
            "mode": "simulation_and_visibility_only",
            "auto_control": False,
            "state": self.mirror.current_state(),
            "timeline_summary": {
                "blocked_total": self.timeline_builder.timeline()["blocked_total"],
                "rework_total": self.timeline_builder.timeline()["rework_total"],
                "waiting_human_total": self.timeline_builder.timeline()["waiting_human_total"],
            },
        }
