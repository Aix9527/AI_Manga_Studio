"""
AI Manga Studio Pro V2.0 — Resource Manager

Tracks GPU VRAM usage and enforces the "heavy/light separation" strategy.
Ensures peak VRAM does not exceed RESOURCE_CONFIG.target_vram_gb (default 12 GB).

Key rules:
- Flux + PuLID: cannot co-reside (serial: Flux generate → unload → PuLID process)
- Wan2.2 + HunyuanVideo: cannot co-reside (serial queuing by shot type)
- SDXL + FLUX: can alternate (different VRAM footprints, not simultaneous peak)
- FFmpeg: CPU-only, zero GPU impact
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from loguru import logger

from backend.config import RESOURCE_CONFIG


# ---------------------------------------------------------------------------
# ResourceError
# ---------------------------------------------------------------------------

class ResourceError(Exception):
    """Raised when a resource constraint cannot be satisfied."""


class VRAMBudgetExceeded(ResourceError):
    """Not enough free VRAM to load the requested model."""


# ---------------------------------------------------------------------------
# Model descriptors
# ---------------------------------------------------------------------------

@dataclass
class _ModelSlot:
    """Internal tracking for a loaded model."""
    name: str
    vram_est_gb: float
    loaded_at: float  # timestamp (time.time())


# ---------------------------------------------------------------------------
# ResourceManager
# ---------------------------------------------------------------------------

class ResourceManager:
    """Singleton VRAM tracker and gatekeeper.

    Usage:
        mgr = ResourceManager()
        mgr.acquire("flux")      # blocks until VRAM available
        # ... do work ...
        mgr.release("flux")
    """

    _instance: Optional["ResourceManager"] = None

    def __new__(cls) -> "ResourceManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = threading.Lock()
            cls._instance._loaded: Dict[str, _ModelSlot] = {}
            cls._instance._target_gb: float = RESOURCE_CONFIG["target_vram_gb"]
            cls._instance._cooldown: float = RESOURCE_CONFIG["cooldown_seconds"]
            cls._instance._lazy: bool = RESOURCE_CONFIG["lazy_unload"]
            cls._instance._heavy_set: Set[str] = set(RESOURCE_CONFIG["heavy_models"])
            cls._instance._light_set: Set[str] = set(RESOURCE_CONFIG["light_models"])
            cls._instance._cpu_set: Set[str] = set(RESOURCE_CONFIG["cpu_only"])
            # VRAM estimates in GB
            cls._instance._vram_est: Dict[str, float] = {
                "flux": 8.0,
                "pulid": 4.0,
                "wan2.2": 9.0,
                "hunyuan": 10.0,
                "sdxl": 3.5,
                "ltx": 3.0,
                "musetalk": 2.5,
                "supir": 5.0,
                "codeformer": 2.0,
                "noobai": 3.5,
                "kolors": 4.0,
            }
        return cls._instance

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def acquire(self, model_name: str) -> None:
        """Acquire the right to load *model_name*.

        Blocks until VRAM budget is available, preemptively unloading
        conflicting models if needed.

        Args:
            model_name: Model identifier (e.g. 'flux', 'pulid').

        Raises:
            VRAMBudgetExceeded: If the model cannot fit even after eviction.
        """
        with self._lock:
            est = self._vram_est.get(model_name, 2.0)

            # CPU-only models are always allowed
            if model_name in self._cpu_set:
                logger.debug(f"ResourceManager: {model_name} is CPU-only, skip VRAM check")
                self._loaded[model_name] = _ModelSlot(
                    name=model_name, vram_est_gb=0.0, loaded_at=time.time(),
                )
                return

            # Check if already loaded
            if model_name in self._loaded:
                logger.debug(f"ResourceManager: {model_name} already loaded")
                return

            # Enforce serialisation for heavy models
            self._evict_if_conflicting(model_name)

            # Check remaining budget
            used = self._used_vram()
            if used + est > self._target_gb:
                if self._lazy:
                    self._evict_unused(needed_gb=est)
                    used = self._used_vram()

            if used + est > self._target_gb:
                raise VRAMBudgetExceeded(
                    f"Cannot load '{model_name}' (~{est:.1f} GB): "
                    f"current usage {used:.1f} GB / {self._target_gb:.1f} GB budget"
                )

            self._loaded[model_name] = _ModelSlot(
                name=model_name, vram_est_gb=est, loaded_at=time.time(),
            )
            logger.info(
                f"ResourceManager: acquired '{model_name}' (~{est:.1f} GB), "
                f"total {used + est:.1f} / {self._target_gb:.1f} GB"
            )

    def release(self, model_name: str) -> None:
        """Release a model, freeing its VRAM budget."""
        with self._lock:
            if model_name in self._loaded:
                slot = self._loaded.pop(model_name)
                logger.info(
                    f"ResourceManager: released '{model_name}' "
                    f"(freed ~{slot.vram_est_gb:.1f} GB)"
                )

    def release_all(self) -> None:
        """Release all loaded models."""
        with self._lock:
            names = list(self._loaded.keys())
            self._loaded.clear()
            logger.info(f"ResourceManager: released all ({', '.join(names)})")

    def current_usage(self) -> float:
        """Current estimated VRAM usage in GB."""
        with self._lock:
            return self._used_vram()

    def is_loaded(self, model_name: str) -> bool:
        """Check if a model is currently considered loaded."""
        with self._lock:
            return model_name in self._loaded

    # ----------------------------------------------------------
    # VRAM probing (GPU-Z / nvidia-smi)
    # ----------------------------------------------------------

    @staticmethod
    def probe_real_vram_gb() -> Optional[float]:
        """Query actual free VRAM via nvidia-smi (returns free GB or None)."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            free_mib = float(result.stdout.strip().split("\n")[0])
            return free_mib / 1024.0
        except Exception:
            return None

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _used_vram(self) -> float:
        """Total estimated VRAM used by loaded models."""
        return sum(s.vram_est_gb for s in self._loaded.values())

    def _evict_if_conflicting(self, new_model: str) -> None:
        """Enforce heavy/light separation rules.

        - A heavy model cannot co-reside with any other heavy model.
        - Flux + PuLID cannot co-reside.
        """
        if new_model not in self._heavy_set:
            return  # light model: no eviction needed unless budget exceeded later

        # Evict all *other* heavy models (only one heavy can be loaded)
        to_evict: List[str] = []
        for name in self._loaded:
            if name == new_model:
                continue
            if name in self._heavy_set:
                to_evict.append(name)

        # Special case: PuLID + Flux conflict (both heavy)
        flux_pulid = {"flux", "pulid"}
        if new_model in flux_pulid:
            for name in self._loaded:
                if name in flux_pulid and name != new_model:
                    if name not in to_evict:
                        to_evict.append(name)

        for name in to_evict:
            logger.info(f"ResourceManager: evicting '{name}' to make room for '{new_model}'")
            self._loaded.pop(name)

    def _evict_unused(self, needed_gb: float) -> None:
        """LRU eviction of light models until needed VRAM is freed.

        Only evicts light models; heavy models are managed by _evict_if_conflicting.
        """
        # Sort by load time, oldest first
        light_slots = [
            (name, slot)
            for name, slot in self._loaded.items()
            if name in self._light_set or name in self._heavy_set
        ]
        light_slots.sort(key=lambda x: x[1].loaded_at)

        freed = 0.0
        for name, slot in light_slots:
            if name in {"flux", "pulid", "wan2.2", "hunyuan"}:
                continue  # don't touch heavy models here
            freed += slot.vram_est_gb
            self._loaded.pop(name)
            logger.info(f"ResourceManager: evicted '{name}' (~{slot.vram_est_gb:.1f} GB)")
            if freed >= needed_gb:
                break

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None
