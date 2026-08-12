from __future__ import annotations

from backend.orchestration.worker import StepExecutionError

from backend.production.contracts import ProductionExecutionRequest


class UnavailableProductionAdapter:
    """Default production adapter: explicit boundary until a real one is injected."""

    def execute(
        self,
        request: ProductionExecutionRequest,
    ):
        raise StepExecutionError(
            "PIPELINE_NOT_READY",
            "本地生产执行器尚未安装或注入",
        )

    def cancel(self, job_id: str) -> bool:
        return False
