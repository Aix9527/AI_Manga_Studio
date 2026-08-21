from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OrchestrationConfig:
    database_path: str = "data/orchestration.db"
    lease_seconds: int = 60
    retry_delays_seconds: list[float] = field(default_factory=lambda: [2.0, 8.0, 30.0])
    max_retry_attempts: int = 3
    poll_interval_seconds: float = 1.0
    checkpoint_dir: str = "data/checkpoints"
    project_root: str = "projects"

    def __post_init__(self) -> None:
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        Path(self.project_root).mkdir(parents=True, exist_ok=True)
