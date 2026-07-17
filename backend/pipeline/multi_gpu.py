"""
V3.0 Layer 16 — Multi-GPU Scheduler

Distributes pipeline workloads across 4 GPUs:
  GPU 0: FLUX family (character + background generation)
  GPU 1: Video models (Wan2.2, Hunyuan, LTX)
  GPU 2: Restore models (SUPIR, CodeFormer)
  GPU 3: Audio/Lip-sync (MuseTalk, CosyVoice)

Each GPU has its own ComfyUI instance on a dedicated port.
"""

from __future__ import annotations

from typing import Dict, List, Optional


# ── GPU Assignment Table ──────────────────────────────────────

GPU_ASSIGNMENTS: Dict[int, List[str]] = {
    0: ["Flux Kontext", "Flux Dev", "SDXL", "NoobAI XL"],
    1: ["Wan2.2", "Hunyuan", "LTX"],
    2: ["SUPIR", "CodeFormer"],
    3: ["MuseTalk", "CosyVoice"],
}

# ComfyUI ports per GPU
GPU_PORTS: Dict[int, int] = {
    0: 8188,
    1: 8189,
    2: 8190,
    3: 8191,
}

# Model → GPU reverse lookup
_MODEL_TO_GPU: Dict[str, int] = {}
for _gpu_id, _models in GPU_ASSIGNMENTS.items():
    for _m in _models:
        _MODEL_TO_GPU[_m] = _gpu_id


class MultiGPUScheduler:
    """Routes pipeline tasks to the correct GPU.

    Usage:
        sched = MultiGPUScheduler()
        gpu_id = sched.dispatch("Flux Kontext")
        port = sched.get_comfyui_port(gpu_id)
        # Submit workflow to http://127.0.0.1:{port}
    """

    @staticmethod
    def dispatch(task_type: str) -> int:
        """Get the GPU ID for a given task type or model name.

        Args:
            task_type: Model name (e.g., "Flux Kontext")
                       or task category (e.g., "image_gen", "video_gen",
                       "restore", "audio").

        Returns:
            GPU ID (0~3). Falls back to GPU 0 for unknown tasks.
        """
        # Direct model name lookup
        if task_type in _MODEL_TO_GPU:
            return _MODEL_TO_GPU[task_type]

        # Category mapping
        category_map = {
            "image_gen": 0,
            "character": 0,
            "background": 0,
            "video_gen": 1,
            "restore": 2,
            "restoration": 2,
            "face_restore": 2,
            "audio": 3,
            "tts": 3,
            "lipsync": 3,
        }
        if task_type in category_map:
            return category_map[task_type]

        # Default: GPU 0
        return 0

    @staticmethod
    def get_comfyui_port(gpu_id: int) -> int:
        """Get ComfyUI port for a given GPU."""
        return GPU_PORTS.get(gpu_id, 8188)

    @staticmethod
    def get_models_for_gpu(gpu_id: int) -> List[str]:
        """List models assigned to a GPU."""
        return GPU_ASSIGNMENTS.get(gpu_id, [])

    @staticmethod
    def get_all_gpus() -> List[int]:
        """Return all GPU IDs."""
        return list(GPU_ASSIGNMENTS.keys())

    @staticmethod
    def get_load_estimate(gpu_id: int) -> Dict[str, int]:
        """Estimate current GPU load (model count + active tasks).

        Returns:
            {"models": N, "active_tasks": M}
        """
        return {
            "models": len(GPU_ASSIGNMENTS.get(gpu_id, [])),
            "active_tasks": 0,  # Would query ComfyUI queue in production
        }

    @staticmethod
    def get_least_busy_gpu(task_category: str) -> int:
        """Find the least busy GPU for a task category.

        For tasks that can run on multiple GPUs (e.g., image generation
        could use GPU 0 or 1 in some configs), picks the GPU with
        the lowest current load.
        """
        candidates = {
            0: ["image_gen", "character", "background"],
            1: ["video_gen"],
            2: ["restore"],
            3: ["audio", "lipsync"],
        }

        target_gpus = [
            gpu for gpu, cats in candidates.items()
            if task_category in cats
        ]

        if not target_gpus:
            return 0

        # Pick GPU with fewest models (simplified load proxy)
        return min(target_gpus, key=lambda g: len(GPU_ASSIGNMENTS.get(g, [])))


# ── GPU Status ────────────────────────────────────────────────


class GPUStatus:
    """GPU status snapshot."""

    def __init__(self, gpu_id: int):
        self.gpu_id = gpu_id
        self.models: List[str] = GPU_ASSIGNMENTS.get(gpu_id, [])
        self.port: int = GPU_PORTS.get(gpu_id, 0)
        self.temperature: float = 0.0
        self.memory_used: float = 0.0  # GB
        self.memory_total: float = 0.0
        self.utilization: float = 0.0  # 0~100
        self.active_tasks: int = 0
        self.queued_tasks: int = 0
        self.status: str = "idle"  # "idle" / "busy" / "error"

    def to_dict(self) -> dict:
        return {
            "gpu_id": self.gpu_id,
            "models": self.models,
            "port": self.port,
            "temperature": self.temperature,
            "memory_used_gb": self.memory_used,
            "memory_total_gb": self.memory_total,
            "utilization_pct": self.utilization,
            "active_tasks": self.active_tasks,
            "queued_tasks": self.queued_tasks,
            "status": self.status,
        }
