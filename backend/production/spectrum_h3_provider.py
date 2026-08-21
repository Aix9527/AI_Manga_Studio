# -*- coding: utf-8 -*-
"""Spectrum MiniMax H3 Provider（桌面工作流集成版）。

使用 ComfyUI 桌面工作流（56 号）转换的 API 格式：
  MiniMaxH3ImageToVideo（FL2V 首尾帧）+ SpectrumApplyMiniMaxH3（频谱加速）
  + XB_Sage_BlockSwap（Sage Attention 跳步加速）+ XB_VAEDecode（自带卸载显存）

与原生 MiniMaxH3Director 工作流的差异：
  - 采样链路：MiniMaxH3ImageToVideo 输出 CONDITIONING + LATENT，
    经 BasicGuider / BasicScheduler / KSamplerSelect / RandomNoise →
    SamplerCustomAdvanced → XB_VAEDecode(视频) + VAEDecodeAudio(音频) → VHS_VideoCombine
  - ``length`` = 帧数（124≈5s @24fps；训练范围 124-362）
  - XB_VAEDecode cleanup 参数可自动卸载显存模型（配合 model_lifecycle）

用法：
  provider = SpectrumMiniMaxH3VideoProvider(
      adapter=ComfyUIAdapter(base_url="http://127.0.0.1:8188"))
  artifact = await provider.generate(VideoRequest(...))
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.production.comfy_adapter import ComfyUIAdapter, ProductionError, ProductionErrorCode
from backend.production.providers import MediaArtifact, VideoRequest
from backend.production.workflow_templates import WorkflowTemplate

logger = logging.getLogger(__name__)

WORKFLOW_NAME = "minimax_h3_fl2v_spectrum.json"

DEFAULT_WIDTH = 480
DEFAULT_HEIGHT = 832
DEFAULT_FPS = 24


def _resolve_workflow_path() -> Path:
    return Path("backend/production/workflows") / WORKFLOW_NAME


class SpectrumMiniMaxH3VideoProvider:
    """桌面工作流（MiniMaxH3ImageToVideo + Spectrum 加速）Provider."""

    provider_name = "minimax_h3_spectrum"

    def __init__(
        self,
        adapter: ComfyUIAdapter | None = None,
        template: WorkflowTemplate | None = None,
    ) -> None:
        workflow_path = _resolve_workflow_path()
        if not workflow_path.exists():
            raise ProductionError(
                ProductionErrorCode.COMFY_WORKFLOW_INVALID,
                f"Spectrum MiniMaxH3 workflow missing: {workflow_path}",
            )
        self.adapter = adapter or ComfyUIAdapter(base_url="http://127.0.0.1:8188")
        self.template = template or WorkflowTemplate.load(workflow_path)

    async def generate(self, request: VideoRequest) -> MediaArtifact:
        """Map VideoRequest -> 桌面工作流生成."""
        if not request.image_path.is_file():
            raise ProductionError(
                ProductionErrorCode.MEDIA_VALIDATION_FAILED,
                f"Input image does not exist: {request.image_path}",
            )
        # 首帧上传（必须）
        first_ref = await self.adapter.upload_image(request.image_path)
        # 尾帧可选（FL2V）
        end_frame = Path(request.end_frame_path) if request.end_frame_path else Path("")
        has_end = bool(end_frame) and end_frame.is_file()
        last_ref = await self.adapter.upload_image(end_frame) if has_end else None

        duration = max(3.0, min(15.0, request.frames / max(1, request.fps)))
        width = request.width or DEFAULT_WIDTH
        height = request.height or DEFAULT_HEIGHT
        fps = request.fps or DEFAULT_FPS
        length = max(107, int(round(duration * fps)))  # 124≈5s；107 为网格下限

        # Spectrum 加速比原生快，超时适当放宽
        self.adapter.timeout_seconds = max(self.adapter.timeout_seconds, int(duration * 60) + 600)

        output_path = request.output_path
        if output_path is None:
            output_path = Path(f"outputs/minimax_h3_spectrum/fl2v_{length}f.mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        workflow = self.template.render(
            prompt=request.prompt,
            seed=request.seed,
            width=width,
            height=height,
            length=length,
            frame_rate=fps,
            filename_prefix=f"minimax_h3_spectrum/{output_path.stem}",
            first_frame=first_ref.reference,
            last_frame=last_ref.reference if last_ref else "frame.png",  # 占位（无尾帧时 LoadImage 仍有效）
        )
        if not last_ref:
            # 无尾帧：直接移除 last_frame 输入（LoadImage 177 已由 render 写入，保留占位无害）
            workflow["133"]["inputs"].pop("last_frame", None)

        comfy_artifact = await self.adapter.generate_to_file(workflow, output_path)
        return MediaArtifact(
            path=output_path,
            kind="video",
            metadata={
                "provider": self.provider_name,
                "frames": length,
                "duration_s": round(length / fps, 2),
                "fps": fps,
                "width": width,
                "height": height,
                "seed": request.seed,
                "first_frame": str(request.image_path),
                "last_frame": str(end_frame) if has_end else "",
                "workflow": WORKFLOW_NAME,
                "spectrum_accel": True,
            },
        )
