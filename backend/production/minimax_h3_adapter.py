# -*- coding: utf-8 -*-
"""MiniMaxH3 VideoProvider 适配器（用户指令：视频模型使用 MiniMax H3）。

把生产链路统一的 ``VideoRequest`` 协议映射到
:class:`backend.video.providers.minimax_h3_provider.MiniMaxH3Provider`
（ComfyUI Native MiniMaxH3Director FL2V 首尾帧工作流）。

关键差异：
  - MiniMax H3 是 FL2V 首尾帧模型：``start_frame`` + 可选 ``end_frame``。
  - 原生支持 15 秒长镜头（直接满足用户"单视频 15 秒"需求）。
  - 不支持 denoise/motion_bucket（由模型内部导演驱动），保留 prompt 语义。
  - 原生音频（audio_vae）。
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.production.comfy_adapter import ComfyUIAdapter, ProductionError, ProductionErrorCode
from backend.production.providers import MediaArtifact, VideoRequest
from backend.production.workflow_templates import WorkflowTemplate
from backend.video.providers.minimax_h3_provider import MiniMaxH3Provider

logger = logging.getLogger(__name__)

WORKFLOW_NAME = "minimax_h3_fl2va_native.json"

# 竖屏成片规格（抖音 AI 漫剧）：1080x1920 太大，MiniMaxH3 竖屏推荐 480x832 生成
DEFAULT_WIDTH = 480
DEFAULT_HEIGHT = 832
DEFAULT_FPS = 24


def _resolve_workflow_path() -> Path:
    return Path("backend/production/workflows") / WORKFLOW_NAME


class MiniMaxH3VideoProvider:
    """VideoRequest 协议适配器 -> MiniMaxH3Provider (ComfyUI Native)."""

    provider_name = "minimax_h3"

    def __init__(
        self,
        adapter: ComfyUIAdapter | None = None,
        template: WorkflowTemplate | None = None,
    ) -> None:
        workflow_path = _resolve_workflow_path()
        if not workflow_path.exists():
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                f"MiniMaxH3 workflow missing: {workflow_path}",
            )
        self.adapter = adapter or ComfyUIAdapter(base_url="http://127.0.0.1:8188")
        self.template = template or WorkflowTemplate.load(workflow_path)
        self._inner = MiniMaxH3Provider(adapter=self.adapter, template=self.template)

    async def generate(self, request: VideoRequest) -> MediaArtifact:
        """Map a VideoRequest to MiniMax H3 FL2V generation."""
        if not request.image_path.is_file():
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Input image does not exist: {request.image_path}",
            )
        end_frame = Path(request.end_frame_path) if request.end_frame_path else Path("")
        duration = max(5.0, min(15.0, request.frames / max(1, request.fps)))
        width = request.width or DEFAULT_WIDTH
        height = request.height or DEFAULT_HEIGHT
        fps = request.fps or DEFAULT_FPS
        return await self._inner.generate(
            start_frame=request.image_path,
            end_frame=end_frame,
            prompt=request.prompt,
            duration=duration,
            fps=fps,
            width=width,
            height=height,
            seed=request.seed,
            output_path=request.output_path,
            metadata={"motion_bucket_id": request.motion_bucket_id},
        )
