from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScannedProject:
    name: str
    source_path: str
    safe_hash: str
    file_count: int
    total_size: int
    has_settings: bool = False
    has_outputs: bool = False
    last_modified: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ProjectScanner:
    def __init__(self, source_root: str):
        self.source_root = Path(source_root)

    def scan(self) -> list[ScannedProject]:
        if not self.source_root.is_dir():
            return []
        results: list[ScannedProject] = []
        for entry in sorted(self.source_root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                proj = self._scan_project(entry)
                if proj:
                    results.append(proj)
        return results

    def _scan_project(self, path: Path) -> ScannedProject | None:
        files = list(path.rglob("*"))
        if not files:
            return None

        total_size = sum(f.stat().st_size for f in files if f.is_file())
        file_count = sum(1 for f in files if f.is_file())
        has_settings = any(f.name in ("settings.json", "project.json") for f in files)
        has_outputs = any(f.suffix in (".mp4", ".png", ".jpg", ".wav") for f in files)

        hash_input = f"{path.name}:{file_count}:{total_size}"
        safe_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        mtimes = [f.stat().st_mtime for f in files if f.is_file()]
        last_modified = max(mtimes) if mtimes else 0

        from datetime import datetime
        lm_str = datetime.fromtimestamp(last_modified).isoformat() if last_modified else ""

        return ScannedProject(
            name=path.name,
            source_path=str(path),
            safe_hash=safe_hash,
            file_count=file_count,
            total_size=total_size,
            has_settings=has_settings,
            has_outputs=has_outputs,
            last_modified=lm_str,
        )
