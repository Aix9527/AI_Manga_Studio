from __future__ import annotations

import shutil
from pathlib import Path

from backend.migration.scanner import ScannedProject


class ConflictError(Exception):
    def __init__(self, source: str, target: str):
        self.source = source
        self.target = target
        super().__init__(f"Conflict: {source} → {target} already exists")


class AssetImporter:
    def __init__(self, target_root: str):
        self.target_root = Path(target_root)
        self.target_root.mkdir(parents=True, exist_ok=True)

    def import_project(self, project: ScannedProject, force: bool = False) -> str:
        target_dir = self.target_root / project.name
        if target_dir.exists() and any(target_dir.iterdir()):
            if not force:
                raise ConflictError(project.source_path, str(target_dir))
            shutil.rmtree(target_dir)

        target_dir.mkdir(parents=True, exist_ok=True)
        self._copy_tree(Path(project.source_path), target_dir)
        return str(target_dir)

    def import_assets(
        self,
        project: ScannedProject,
        asset_types: list[str] | None = None,
    ) -> list[str]:
        imported: list[str] = []
        source = Path(project.source_path)
        target = self.target_root / project.name / "assets"
        target.mkdir(parents=True, exist_ok=True)

        allow = set(asset_types) if asset_types else {".png", ".jpg", ".jpeg", ".mp4", ".wav", ".mp3"}

        for f in source.rglob("*"):
            if f.is_file() and f.suffix.lower() in allow:
                rel = f.relative_to(source)
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(f, dest)
                    imported.append(str(dest))

        return imported

    def dry_run(self, project: ScannedProject) -> dict:
        conflicts: list[str] = []
        new_files: list[str] = []
        source = Path(project.source_path)

        for f in source.rglob("*"):
            if f.is_file():
                rel = f.relative_to(source)
                dest = self.target_root / project.name / rel
                if dest.exists():
                    conflicts.append(str(dest))
                else:
                    new_files.append(str(dest))

        return {"conflicts": conflicts, "new_files": new_files, "project": project.name}

    def _copy_tree(self, src: Path, dst: Path) -> None:
        for item in src.iterdir():
            d = dst / item.name
            if item.is_dir():
                d.mkdir(exist_ok=True)
                self._copy_tree(item, d)
            else:
                shutil.copy2(item, d)
