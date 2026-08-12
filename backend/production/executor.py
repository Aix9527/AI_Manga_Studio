from __future__ import annotations

from backend.orchestration.worker import StepExecutionError

from backend.production.contracts import (
    ProductionExecutionPort,
    ProductionExecutionRequest,
)


class ProductionStepRunner:
    """Durable binding consumer: routes a job step to the injected execution port.

    The runner never performs provider routing itself. It reads the durable
    provider binding persisted by JobRepository and forwards it unchanged to
    the ProductionExecutionPort. Without a binding the step fails explicitly
    with PROVIDER_BINDING_REQUIRED (no fallback).
    """

    def __init__(self, repository, execution_port=None):
        self.repository = repository
        self.execution_port = execution_port

    def run_next(self, job, cancel_requested):
        if cancel_requested():
            raise StepExecutionError("USER_CANCELLED", "任务已取消")

        binding = self.repository.get_provider_binding(job["id"])

        if binding is None:
            raise StepExecutionError(
                "PROVIDER_BINDING_REQUIRED",
                "job has no durable provider binding; refusing to execute",
            )

        if self.execution_port is None:
            raise StepExecutionError(
                "PIPELINE_NOT_READY",
                "本地生产执行器尚未安装或注入",
            )

        request = ProductionExecutionRequest(
            job_id=job["id"],
            project_id=job.get("project_id", ""),
            stage_key=job.get("current_stage", "") or "input_parse",
            provider_binding=binding,
            settings=job.get("settings", {}) or {},
        )

        result = self.execution_port.execute(request)

        return result

    def cancel(self, job_id: str) -> bool:
        if self.execution_port is not None:
            try:
                return bool(self.execution_port.cancel(job_id))
            except Exception:
                return False
        return False
