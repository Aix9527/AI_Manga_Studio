# -*- coding: utf-8 -*-
"""Model Lifecycle — 双引擎显存调度（GPT Round-4 批准项）。

背景：MiniMax H3（UNET 20GB / CLIP 15GB / VAE 5GB）在 16GB 显存环境
与 Wan2.2 并存有 OOM 风险（15s FL2V 曾导致 ComfyUI 崩溃重启）。
批量生产必须显式管理引擎切换：

  before_engine(engine)    切换到目标引擎前：卸载另一引擎 + empty_cache
  after_engine(engine)     目标引擎用完后：卸载 + 清理，供下一镜使用

实现：
  - 通过 ComfyUI API 卸载/释放节点缓存不可直接做；退而求其次，
    记录引擎占用状态 + 触发 ComfyUI 的 GC（/free 端点），并在切换时
    等待显存回落（轮询 nvidia-smi 或 ComfyUI system_stats）。
  - 本地 torch 卸载逻辑保留（若直接持有模型句柄）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ENGINES = ("wan22", "minimax_h3", "ltx23")

# 每引擎的 VRAM 占用估算（GB，用于调度决策）
ENGINE_VRAM_GB: dict[str, float] = {
    "wan22": 10.0,        # Wan2.2 5B fp16
    "minimax_h3": 15.5,   # H3 FL2V int8 + CLIP nvfp4 + VAE（逼近 16GB 上限）
    "ltx23": 8.0,
}


@dataclass
class ModelLifecycleManager:
    comfy_url: str = "http://127.0.0.1:8188"
    max_vram_gb: float = 16.0
    _active_engine: str | None = field(default=None, init=False)

    # ------------------------------------------------------------- public

    async def before_engine(self, engine: str) -> str:
        """切换引擎前调用：卸载另一引擎并清理显存。返回建议/警告文本。"""
        engine = engine.lower()
        if engine not in ENGINES:
            logger.warning("Unknown engine %r (expected %s)", engine, ENGINES)
            return f"unknown engine {engine}"

        notes: list[str] = []
        if self._active_engine is not None and self._active_engine != engine:
            notes.append(f"engine switch {self._active_engine} -> {engine}")
            await self._free_models()
            await self._wait_vram_headroom(engine)
        elif self._active_engine is None:
            notes.append(f"cold start engine {engine}")

        # H3 是重引擎：强制清理 + 检查显存余量
        if engine == "minimax_h3":
            await self._free_models()
            await self._wait_vram_headroom(engine, force=True)

        self._active_engine = engine
        msg = "; ".join(notes) if notes else f"{engine} already active"
        logger.info("[model_lifecycle] before_engine(%s): %s", engine, msg)
        return msg

    async def after_engine(self, engine: str) -> str:
        """引擎用完后调用：卸载 + 清缓存，为下一镜释放显存。"""
        engine = engine.lower()
        await self._free_models()
        # 不重置 _active_engine —— 下一镜同引擎可复用，跨引擎才切换
        msg = f"released models of {engine}"
        logger.info("[model_lifecycle] after_engine(%s): %s", engine, msg)
        return msg

    # ------------------------------------------------------------- internals

    async def _free_models(self) -> None:
        """调用 ComfyUI /free 端点释放已加载模型 + 空缓存。"""
        for endpoint in ("/free", "/free?unload_models=true&free_memory=true"):
            try:
                req = urllib.request.Request(
                    self.comfy_url + endpoint, method="POST"
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    if resp.status < 300:
                        logger.info("[model_lifecycle] ComfyUI %s OK", endpoint)
                        return
            except Exception as exc:  # noqa: BLE001
                logger.debug("[model_lifecycle] /free failed (%s): %s", endpoint, exc)
        # 本地 torch 兜底（若进程内持有句柄）
        await asyncio.get_event_loop().run_in_executor(None, _torch_empty_cache)

    async def _wait_vram_headroom(
        self, engine: str, force: bool = False, max_waits: int = 6
    ) -> None:
        """等待显存回落至目标引擎可加载（轮询 system_stats / nvidia-smi）。"""
        target = ENGINE_VRAM_GB.get(engine, 10.0)
        for attempt in range(max_waits):
            used = self._vram_used_gb()
            if used <= 0:  # 无法探测 -> 不阻塞
                return
            if used <= max(1.0, self.max_vram_gb - target) + 0.5 or (not force and used <= self.max_vram_gb * 0.9):
                return
            logger.info(
                "[model_lifecycle] waiting VRAM: used=%.1fGB (engine=%s target=%.1fGB)",
                used, engine, target,
            )
            await asyncio.sleep(5)
        logger.warning(
            "[model_lifecycle] VRAM headroom not reached for %s; proceeding anyway",
            engine,
        )

    def _vram_used_gb(self) -> float:
        """ComfyUI system_stats -> device vram used (GB); 0 = 探测失败。"""
        try:
            with urllib.request.urlopen(
                self.comfy_url + "/system_stats", timeout=10
            ) as resp:
                data = json.loads(resp.read())
            for dev in data.get("devices", []):
                v = dev.get("vram_total") or dev.get("torch_vram_total") or 0
                u = dev.get("vram_used") or dev.get("torch_vram_used") or 0
                if v:
                    return u / (1024 ** 3)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[model_lifecycle] vram probe failed: %s", exc)
        # 兜底：nvidia-smi
        try:
            import subprocess
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                used_mb, _ = out.stdout.strip().split(",")[:2]
                return float(used_mb.strip()) / 1024.0
        except Exception as exc:  # noqa: BLE001
            logger.debug("[model_lifecycle] nvidia-smi probe failed: %s", exc)
        return 0.0


def _torch_empty_cache() -> None:
    """本地 torch 清理（幂等，无 torch 时静默跳过）。"""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass
