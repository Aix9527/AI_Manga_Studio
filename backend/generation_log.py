"""
AI Manga Studio Pro V1.0 — Generation Log

Records every generation's full parameter set for reproducibility.
Any shot can be re-generated with identical settings.

Logs are written to: logs/generations/{shot_id}_{timestamp}.json

Fields logged:
  - Prompt (positive + negative)
  - Seed
  - CFG Scale
  - Sampler / Scheduler
  - Steps
  - Model / Checkpoint
  - LoRA (if any)
  - Resolution
  - GPU ID
  - Duration (seconds)
  - Output path
  - Cache status (hit/miss)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


@dataclass
class GenerationLog:
    """Complete parameter set for one generation."""

    # Identity
    shot_id: str = ""
    project_id: str = ""
    chapter: int = 0
    scene_num: int = 0
    shot_num: int = 0
    category: str = "image"  # image / video / character / scene

    # Prompt
    positive_prompt: str = ""
    negative_prompt: str = ""

    # Generation params
    seed: int = -1
    cfg_scale: float = 7.0
    sampler: str = "euler_ancestral"
    scheduler: str = "normal"
    steps: int = 30
    model: str = ""
    checkpoint: str = ""
    lora: List[str] = field(default_factory=list)

    # Resolution
    width: int = 1920
    height: int = 1080

    # GPU
    gpu_id: int = 0
    gpu_name: str = ""

    # Timing
    started_at: float = 0.0
    duration_seconds: float = 0.0

    # Output
    output_path: str = ""
    file_size_bytes: int = 0

    # Cache
    cache_hit: bool = False

    # Extra metadata
    workflow_hash: str = ""
    weather: str = ""
    time_of_day: str = ""
    camera: str = ""
    emotion: str = ""
    character_names: List[str] = field(default_factory=list)

    # ----------------------------------------------------------
    # I/O
    # ----------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GenerationLog":
        return cls(**d)

    def save(self, log_dir: str = "") -> str:
        """Save log to JSON file.

        Returns:
            Path to saved log file.
        """
        if not log_dir:
            log_dir = self._default_log_dir()

        os.makedirs(log_dir, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_id = self.shot_id.replace("/", "_").replace("\\", "_")
        # Truncate safe_id to avoid path length issues
        safe_id = safe_id[:60] if len(safe_id) > 60 else safe_id
        filename = f"{safe_id}_{timestamp}.json"
        path = os.path.join(log_dir, filename)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        logger.debug(f"GenerationLog: Saved → {path}")
        return path

    @classmethod
    def load(cls, path: str) -> "GenerationLog":
        """Load log from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def load_all_for_shot(cls, shot_id: str, log_dir: str = "") -> List["GenerationLog"]:
        """Load all generation logs for a specific shot.

        Returns:
            List of logs sorted by time (newest first).
        """
        if not log_dir:
            log_dir = cls._default_log_dir()

        safe_id = shot_id.replace("/", "_").replace("\\", "_")
        safe_id = safe_id[:60] if len(safe_id) > 60 else safe_id
        logs: List[GenerationLog] = []

        if not os.path.isdir(log_dir):
            return logs

        for fname in sorted(os.listdir(log_dir), reverse=True):
            if fname.startswith(safe_id) and fname.endswith(".json"):
                try:
                    logs.append(cls.load(os.path.join(log_dir, fname)))
                except Exception:
                    continue

        return logs

    @staticmethod
    def _default_log_dir() -> str:
        import os as _os
        from backend.config import get_config

        cfg = get_config()
        return _os.path.join(cfg.paths.logs, "generations")

    # ----------------------------------------------------------
    # Summary
    # ----------------------------------------------------------

    def summary(self) -> str:
        """Human-readable one-line summary."""
        parts = [
            f"[{self.category}] {self.shot_id or 'unknown'}",
            f"seed={self.seed}",
            f"CFG={self.cfg_scale}",
            f"{self.sampler}",
            f"{self.steps}steps",
            f"GPU{self.gpu_id}",
        ]
        if self.model:
            parts.append(self.model)
        if self.lora:
            parts.append(f"LoRA={','.join(self.lora)}")
        parts.append(f"{self.duration_seconds:.1f}s")
        if self.cache_hit:
            parts.append("CACHE")
        parts.append(self.output_path or "N/A")
        return " | ".join(parts)

    def reproducibility_check(self) -> Dict[str, Any]:
        """Check if this log contains enough info to reproduce the generation.

        Returns:
            Dict with 'can_reproduce' boolean and missing fields.
        """
        missing = []
        if self.seed == -1:
            missing.append("seed")
        if not self.positive_prompt:
            missing.append("positive_prompt")
        if not self.model:
            missing.append("model")
        if self.steps <= 0:
            missing.append("steps")

        return {
            "can_reproduce": len(missing) == 0,
            "missing_fields": missing,
            "log_path": "",
            "shot_id": self.shot_id,
        }
