from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .comfy_media import H3ComfyMediaAdapter
from .staging import stage_h3_unified_request
from .ui_state import H3UnifiedRequest
from backend.video.providers.minimax_h3_unified_provider import H3UnifiedProvider


class H3UnifiedUnavailableError(RuntimeError):
    def __init__(self, message: str, *, alternate_route: str) -> None:
        self.alternate_route = alternate_route
        # Backward-compatible informational alias.  This does NOT mean the
        # current Unified request may be submitted to that route unchanged.
        self.fallback = alternate_route
        self.requires_recompile = True
        super().__init__(message)


@dataclass(frozen=True)
class H3UnifiedExecutionResult:
    prompt_id: str
    outputs: dict[str, Any]
    runtime: str
    resumed: bool = False


@dataclass
class H3UnifiedExecutionService:
    adapter: Any = field(default_factory=H3ComfyMediaAdapter)
    provider: H3UnifiedProvider = field(default_factory=H3UnifiedProvider)

    async def execute(
        self,
        request: H3UnifiedRequest,
        *,
        subfolder: str | None = None,
        on_submitted=None,
        resume_prompt_id: str = "",
    ) -> H3UnifiedExecutionResult:
        """Stage, submit, and wait for one external H3 unified workflow.

        If ``resume_prompt_id`` is supplied, no media is uploaded and no new
        prompt is submitted. The exact accepted ComfyUI prompt is reconciled
        through history instead, preserving the durable crash-recovery rule.

        Traditional H3 reference/FL2V routes are deliberately not transparent
        fallbacks: their input contracts differ from a Unified request.  If the
        external control desk is missing we fail before upload/submission and
        report the alternate route that an upper layer may recompile for.
        """

        if resume_prompt_id:
            outputs = await self.adapter.wait_for_completion(resume_prompt_id)
            return H3UnifiedExecutionResult(
                prompt_id=resume_prompt_id,
                outputs=outputs,
                runtime="external_unified",
                resumed=True,
            )

        object_info = await self.adapter.get_object_info()
        preflight = self.provider.preflight(object_info)
        if not preflight["external_unified_available"]:
            raise H3UnifiedUnavailableError(
                "External H3 unified control node is unavailable; alternate H3 routes require request recompilation",
                alternate_route=str(preflight["alternate_route"]),
            )

        staged = await stage_h3_unified_request(
            request,
            self.adapter,
            subfolder=subfolder or _default_subfolder(request),
        )
        workflow = self.provider.build_external_workflow(staged)
        completed = await self.adapter.submit_and_wait(
            workflow,
            on_submitted=on_submitted,
        )
        return H3UnifiedExecutionResult(
            prompt_id=completed.prompt_id,
            outputs=completed.outputs,
            runtime="external_unified",
            resumed=False,
        )


def _default_subfolder(request: H3UnifiedRequest) -> str:
    return (
        "h3_unified/"
        f"ep{int(request.shot_episode):04d}_"
        f"scene{int(request.shot_scene):04d}_"
        f"shot{int(request.shot_number):04d}_"
        f"take{int(request.shot_take):04d}"
    )
