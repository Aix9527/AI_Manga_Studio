from __future__ import annotations

from backend.orchestration.worker import StepExecutionError


class ProductionStepRunner:
    """Explicit boundary until sub-project 2/3 install real local adapters."""

    def __init__(self, repository):
        self.repository = repository

    def run_next(self, job, cancel_requested):
        if cancel_requested():
            raise StepExecutionError("USER_CANCELLED", "任务已取消")
        raise StepExecutionError(
            "PIPELINE_NOT_READY",
            "本地生产执行器尚未安装；任务已安全停止且未生成占位产物",
        )

    def cancel(self, job_id: str) -> bool:
        return False
