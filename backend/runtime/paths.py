from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    application_root: Path
    data_root: Path
    database_dir: Path
    orchestration_database: Path
    logs_dir: Path
    projects_dir: Path
    output_dir: Path
    cache_dir: Path
    temp_dir: Path

    @classmethod
    def from_config(cls, config, application_root: str | Path) -> "RuntimePaths":
        app_root = Path(application_root).resolve()
        configured_root = os.environ.get(
            "AI_MANGA_STUDIO_DATA_ROOT", config.runtime.data_root
        )
        data_root = Path(configured_root)
        if not data_root.is_absolute():
            data_root = app_root / data_root
        data_root = data_root.resolve()

        database_path = Path(config.orchestration.database_path)
        if not database_path.is_absolute():
            database_path = data_root / database_path
        database_path = database_path.resolve()

        return cls(
            application_root=app_root,
            data_root=data_root,
            database_dir=database_path.parent,
            orchestration_database=database_path,
            logs_dir=data_root / "logs",
            projects_dir=data_root / "projects",
            output_dir=data_root / "output",
            cache_dir=data_root / "cache",
            temp_dir=data_root / "temp",
        )

    def ensure(self) -> None:
        for directory in (
            self.database_dir,
            self.logs_dir,
            self.projects_dir,
            self.output_dir,
            self.cache_dir,
            self.temp_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
