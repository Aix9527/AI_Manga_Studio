"""
AI Manga Studio Pro V1.0 — ComfyUI GPU Manager

Manages multiple ComfyUI instances across GPUs.
Each plugin gets its dedicated ComfyUIClient bound to a specific GPU.

Architecture:
  GPU 0 → Flux (image)  → port 8188
  GPU 1 → Wan  (video)  → port 8189
  GPU 2 → LTX  (video)  → port 8190

Scheduler Integration:
  Image stage  → flux plugin → GPU 0  (auto)
  Video stage  → wan plugin  → GPU 1  (auto)
  Video stage  → ltx plugin  → GPU 2  (auto)

Usage:
  manager = get_gpu_manager()
  client = manager.get_client("flux")  # → ComfyUIClient for GPU 0
  manager.health()                     # → status of all GPUs
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

import requests
from loguru import logger

from backend.comfyui_client import ComfyUIClient


class GPUSlot:
    """One ComfyUI instance bound to a GPU."""

    def __init__(
        self,
        name: str,
        gpu_id: int,
        base_url: str,
        port: int,
    ) -> None:
        self.name = name
        self.gpu_id = gpu_id
        self.base_url = base_url
        self.port = port
        self._client: Optional[ComfyUIClient] = None
        self._lock = threading.Lock()

    @property
    def client(self) -> ComfyUIClient:
        """Lazy-initialize and return the ComfyUIClient."""
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = ComfyUIClient(base_url=self.base_url)
                    logger.info(
                        f"GPUSlot: '{self.name}' → GPU {self.gpu_id} "
                        f"({self.base_url}) initialized"
                    )
        return self._client

    def health(self) -> Dict[str, Any]:
        """Check if this GPU's ComfyUI instance is reachable."""
        try:
            resp = requests.get(f"{self.base_url}/system_stats", timeout=5)
            stats = resp.json() if resp.ok else {}
            return {
                "name": self.name,
                "gpu": self.gpu_id,
                "port": self.port,
                "url": self.base_url,
                "status": "online",
                "vram_used": stats.get("vram_used", "?"),
                "vram_total": stats.get("vram_total", "?"),
            }
        except Exception:
            return {
                "name": self.name,
                "gpu": self.gpu_id,
                "port": self.port,
                "url": self.base_url,
                "status": "offline",
            }

    def __repr__(self) -> str:
        return f"GPUSlot({self.name}, GPU{self.gpu_id}:{self.port})"


class ComfyUIManager:
    """Manages multiple ComfyUI instances across GPUs.

    Plugins request a client by name; the manager routes to the
    correct GPU automatically.
    """

    # Task → GPU mapping (can be extended)
    GPU_MAP: Dict[str, str] = {
        "flux": "flux",
        "wan": "wan",
        "ltx": "ltx",
        # Aliases
        "image": "flux",
        "video": "wan",
        "video2": "ltx",
    }

    def __init__(self) -> None:
        from backend.config import get_config

        cfg = get_config()
        instances = cfg.comfyui.instances
        self._slots: Dict[str, GPUSlot] = {}

        if not instances:
            # Fallback: single-instance mode
            default = GPUSlot(
                name="default",
                gpu_id=0,
                base_url=cfg.comfyui.base_url,
                port=8188,
            )
            self._slots["default"] = default
            self._slots["flux"] = default
            self._slots["wan"] = default
            self._slots["ltx"] = default
            logger.warning("ComfyUIManager: No instances configured, using single-GPU fallback")
        else:
            for name, inst in instances.items():
                self._slots[name] = GPUSlot(
                    name=name,
                    gpu_id=inst.gpu_id,
                    base_url=inst.base_url,
                    port=inst.port,
                )

        logger.info(
            f"ComfyUIManager: {len(set(s.gpu_id for s in self._slots.values()))} GPUs, "
            f"{len(self._slots)} instances registered"
        )

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def get_client(self, task: str = "flux") -> ComfyUIClient:
        """Get ComfyUIClient for a task type.

        Args:
            task: Task name — "flux", "wan", "ltx", "image", "video".

        Returns:
            ComfyUIClient bound to the correct GPU.
        """
        slot_name = self.GPU_MAP.get(task, task)
        slot = self._slots.get(slot_name)

        if slot is None:
            raise ValueError(
                f"No GPU slot for task '{task}' (mapped to '{slot_name}'). "
                f"Available: {list(self._slots.keys())}"
            )

        return slot.client

    def get_gpu_id(self, task: str = "flux") -> int:
        """Get GPU ID for a task type."""
        slot_name = self.GPU_MAP.get(task, task)
        slot = self._slots.get(slot_name)
        if slot is None:
            return -1
        return slot.gpu_id

    def get_gpu_info(self, task: str = "flux") -> Dict[str, Any]:
        """Get GPU info dict for a task type.

        Returns:
            Dict with gpu_id, name, port, base_url fields.
        """
        slot_name = self.GPU_MAP.get(task, task)
        slot = self._slots.get(slot_name)
        if slot is None:
            return {"gpu_id": -1, "name": "", "port": 0, "base_url": ""}
        return {
            "gpu_id": slot.gpu_id,
            "name": slot.name,
            "port": slot.port,
            "base_url": slot.base_url,
        }

    def health(self) -> list[Dict[str, Any]]:
        """Check health status of all GPU slots."""
        return [slot.health() for slot in self._slots.values()]

    def health_summary(self) -> str:
        """Human-readable health summary."""
        lines = ["GPU Health:"]
        for h in self.health():
            status_icon = "OK" if h["status"] == "online" else "DOWN"
            vram = f"VRAM {h.get('vram_used', '?')}/{h.get('vram_total', '?')}" if h["status"] == "online" else ""
            lines.append(f"  GPU {h['gpu']} ({h['name']}): {status_icon}  {vram}")
        return "\n".join(lines)

    def get_client_for_plugin(self, plugin_name: str) -> ComfyUIClient:
        """Get ComfyUIClient for a plugin by name.

        Args:
            plugin_name: Plugin name — "flux", "wan", "ltx".

        Returns:
            ComfyUIClient bound to the plugin's GPU.
        """
        return self.get_client(plugin_name)


# ----------------------------------------------------------
# Singleton
# ----------------------------------------------------------

_manager: Optional[ComfyUIManager] = None
_lock = threading.Lock()


def get_gpu_manager() -> ComfyUIManager:
    """Get or create the global GPU manager singleton."""
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = ComfyUIManager()
    return _manager
