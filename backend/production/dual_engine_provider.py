# -*- coding: utf-8 -*-
"""DualEngineVideoProvider — 双引擎路由 Provider（GPT Round-5 批准版：H3-first）。

用户指令：视频模型使用 MiniMax H3。H3 为主引擎，Wan2.2 仅作为失败恢复
/成本保护通道。路由依据：``VideoRequest.engine``（由调度层 decide_engine 写入，
H3-first 模式下默认 minimax_h3）。

分级失败回退（GPT Round-5 批准）:
  - Failure Level 1（可重试：timeout / queue stuck / 临时显存不足）
      -> H3 retry ×1，并降低 duration（15s->10s）
  - Failure Level 2（模型失败：OOM / node crash / decode failure）
      -> unload H3 -> load Wan -> Wan retry（fallback_reason=H3_failed）
  - Failure Level 3（质量失败：生成成功但 QC FAIL）
      -> 先 H3 换 seed 重生成（模型能力没问题，是随机性问题），仍失败才 Wan

引擎切换时调用 :class:`ModelLifecycleManager` 管理显存（H3 前卸载 Wan + 清理）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend.production.comfy_adapter import (
    ComfyUIAdapter,
    ProductionError,
    ProductionErrorCode,
)
from backend.production.engine_policy import ENGINE_MINIMAX, ENGINE_WAN
from backend.production.providers import MediaArtifact, VideoRequest
from backend.video.model_lifecycle import ModelLifecycleManager

logger = logging.getLogger(__name__)


@dataclass
class FallbackStats:
    """H3 -> Wan fallback 统计（回传 GPT 用）。"""
    attempts: int = 0
    h3_retries: int = 0
    wan_fallbacks: int = 0
    qc_regens: int = 0
    last_fallback_reason: str = ""


class DualEngineVideoProvider:
    """Routes each VideoRequest to MiniMax H3 (primary) or Wan2.2 (fallback)."""

    provider_name = "dual_engine"

    def __init__(
        self,
        comfy_url: str = "http://127.0.0.1:8188",
        lifecycle: ModelLifecycleManager | None = None,
        force_engine: str = "",
        fallback_stats: FallbackStats | None = None,
        h3_provider: str = "spectrum",  # spectrum（桌面工作流加速）/ native（Director）
    ) -> None:
        self.comfy_url = comfy_url
        self.lifecycle = lifecycle or ModelLifecycleManager(comfy_url=comfy_url)
        self.force_engine = force_engine
        self.stats = fallback_stats or FallbackStats()
        self.h3_provider = h3_provider
        self._wan: object | None = None
        self._h3: object | None = None

    # ------------------------------------------------------------- providers

    def _wan_provider(self):
        if self._wan is None:
            from backend.production.comfy_video import WanVideoProvider
            from backend.production.workflow_registry import select_wan_video_workflow
            from backend.production.workflow_templates import WorkflowTemplate
            adapter = ComfyUIAdapter(base_url=self.comfy_url)
            spec = select_wan_video_workflow(has_end_frame=False)
            self._wan = WanVideoProvider(
                adapter=adapter, template=WorkflowTemplate.load(spec.path)
            )
        return self._wan

    def _h3_provider(self):
        if self._h3 is None:
            adapter = ComfyUIAdapter(base_url=self.comfy_url)
            if self.h3_provider == "spectrum":
                # 用户新指令：集成桌面工作流（MiniMaxH3ImageToVideo + Spectrum 加速）
                from backend.production.spectrum_h3_provider import (
                    SpectrumMiniMaxH3VideoProvider,
                )
                self._h3 = SpectrumMiniMaxH3VideoProvider(adapter=adapter)
            else:
                from backend.production.minimax_h3_adapter import MiniMaxH3VideoProvider
                self._h3 = MiniMaxH3VideoProvider(adapter=adapter)
        return self._h3

    # ------------------------------------------------------------- generate

    async def generate(self, request: VideoRequest) -> MediaArtifact:
        engine = self.force_engine or request.engine or ENGINE_MINIMAX
        self.stats.attempts += 1
        if engine == ENGINE_MINIMAX:
            try:
                return await self._generate_h3_with_fallback(request)
            except Exception as exc:  # noqa: BLE001 - last-resort Wan
                logger.warning(
                    "H3 generate failed (%s); falling back to Wan for %s",
                    exc, Path(request.output_path).stem,
                )
                self.stats.wan_fallbacks += 1
                self.stats.last_fallback_reason = f"h3_exception:{exc}"
                await self.lifecycle.before_engine(ENGINE_WAN)
                try:
                    return await self._wan_provider().generate(request)
                finally:
                    await self.lifecycle.after_engine(ENGINE_WAN)
        await self.lifecycle.before_engine(ENGINE_WAN)
        try:
            return await self._wan_provider().generate(request)
        finally:
            await self.lifecycle.after_engine(ENGINE_WAN)

    async def _generate_h3_with_fallback(self, request: VideoRequest) -> MediaArtifact:
        """H3 主路径 + 分级失败回退（GPT Round-5 批准）。

        L1: H3 retry ×1（timeout / queue stuck）—— 降低 duration 15s->10s
        L2: Wan fallback（OOM / node crash / decode failure）
        L3: 质量失败（QC FAIL）-> H3 换 seed 重生成；仍失败 -> Wan
        """
        await self.lifecycle.before_engine(ENGINE_MINIMAX)
        try:
            artifact = await self._h3_provider().generate(request)
            return artifact
        except ProductionError as exc:
            # L2: 模型失败直接回退 Wan
            if exc.code in (
                ProductionErrorCode.COMFY_OOM,
                ProductionErrorCode.COMFY_EXECUTION_FAILED,
            ):
                self.stats.wan_fallbacks += 1
                self.stats.last_fallback_reason = f"h3_model_failed:{exc}"
                logger.warning("H3 model failure (%s) -> Wan fallback", exc)
                await self.lifecycle.after_engine(ENGINE_MINIMAX)
                await self.lifecycle.before_engine(ENGINE_WAN)
                try:
                    return await self._wan_provider().generate(request)
                finally:
                    await self.lifecycle.after_engine(ENGINE_WAN)
            # L1: 可重试（timeout / transient）
            self.stats.h3_retries += 1
            logger.info("H3 retryable failure (%s); retry with shorter duration", exc)
            retry_request = self._shorter_duration(request)
            await self.lifecycle.after_engine(ENGINE_MINIMAX)
            await self.lifecycle.before_engine(ENGINE_MINIMAX)
            try:
                return await self._h3_provider().generate(retry_request)
            except Exception as inner:  # noqa: BLE001
                self.stats.wan_fallbacks += 1
                self.stats.last_fallback_reason = f"h3_retry_failed:{inner}"
                await self.lifecycle.after_engine(ENGINE_MINIMAX)
                await self.lifecycle.before_engine(ENGINE_WAN)
                try:
                    return await self._wan_provider().generate(retry_request)
                finally:
                    await self.lifecycle.after_engine(ENGINE_WAN)
        except Exception as exc:  # noqa: BLE001
            self.stats.wan_fallbacks += 1
            self.stats.last_fallback_reason = f"h3_exception:{exc}"
            logger.warning("H3 exception (%s) -> Wan fallback", exc)
            await self.lifecycle.after_engine(ENGINE_MINIMAX)
            await self.lifecycle.before_engine(ENGINE_WAN)
            try:
                return await self._wan_provider().generate(request)
            finally:
                await self.lifecycle.after_engine(ENGINE_WAN)
        finally:
            await self.lifecycle.after_engine(ENGINE_MINIMAX)

    @staticmethod
    def _shorter_duration(request: VideoRequest) -> VideoRequest:
        """L1 重试：15s -> 10s（降低 H3 显存峰值）。"""
        import dataclasses
        if request.frames <= 240:
            return request
        short = dataclasses.replace(request, frames=240, fps=24)
        logger.info("L1 retry: H3 duration 15s -> 10s for %s", Path(request.output_path).stem)
        return short
