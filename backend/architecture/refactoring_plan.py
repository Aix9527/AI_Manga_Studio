"""
Repository Refactoring Plan & Codebase Migration Map (Part 38)

Maps the vision architecture to concrete repository structure
and defines the migration path from current codebase to target.

Refactoring Principles:
    1. Visual Reference (Part 1-36) → Preserved in docs/vision/
    2. Target Architecture (Part 8-36) → Implemented in backend/ + frontend/
    3. Implementation Blueprint (Part 37-38) → Guides migration
    4. MVP Spec (Part 39-40) → First 10,000 lines blueprint
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MigrationType(str, Enum):
    CREATE = "create"  # New file, not present in current codebase
    REFACTOR = "refactor"  # Existing file, needs restructuring
    MIGRATE = "migrate"  # Move from old location to new
    DELETE = "delete"  # Remove obsolete file
    KEEP = "keep"  # Keep as-is (already matches target)


@dataclass
class MigrationEntry:
    """A single file migration instruction."""
    source_path: str = ""
    target_path: str = ""
    migration_type: MigrationType = MigrationType.CREATE
    description: str = ""
    estimated_lines: int = 0
    priority: int = 0  # 0=blocker, 1=high, 2=medium, 3=low
    dependencies: list[str] = field(default_factory=list)


@dataclass
class MigrationMap:
    """Complete migration map for a bounded context."""
    context_name: str
    entries: list[MigrationEntry] = field(default_factory=list)
    total_estimated_lines: int = 0

    def add(self, entry: MigrationEntry) -> None:
        self.entries.append(entry)
        self.total_estimated_lines += entry.estimated_lines


# ── Migration Maps for Each Context ───────────────────────────────────

MIGRATION_MAPS: dict[str, MigrationMap] = {
    "ProjectContext": MigrationMap(
        "ProjectContext",
        entries=[
            MigrationEntry("", "backend/projects/__init__.py", MigrationType.KEEP, "Already matches target", 150),
            MigrationEntry("", "backend/database.py", MigrationType.KEEP, "ORM models complete", 600),
            MigrationEntry("", "backend/database/models/__init__.py", MigrationType.KEEP, "Aggregate models", 500),
            MigrationEntry("", "backend/database/__init__.py", MigrationType.KEEP, "DatabaseManager", 100),
        ],
    ),
    "StoryContext": MigrationMap(
        "StoryContext",
        entries=[
            MigrationEntry("", "backend/agents/story/__init__.py", MigrationType.REFACTOR, "Add narrative intelligence engine from Part 29", 800),
            MigrationEntry("", "backend/memory/__init__.py", MigrationType.REFACTOR, "Add long-story context memory", 200),
        ],
    ),
    "CharacterContext": MigrationMap(
        "CharacterContext",
        entries=[
            MigrationEntry("", "backend/agents/character/__init__.py", MigrationType.REFACTOR, "Add Character DNA, visual identity engine from Part 30", 900),
        ],
    ),
    "StoryboardContext": MigrationMap(
        "StoryboardContext",
        entries=[
            MigrationEntry("", "backend/agents/scene/__init__.py", MigrationType.REFACTOR, "Add storyboard DSL and cinematic language from Part 31", 700),
            MigrationEntry("", "backend/workflow/graph.py", MigrationType.KEEP, "DAG structure complete", 200),
            MigrationEntry("", "backend/workflow/nodes.py", MigrationType.KEEP, "12 node types complete", 500),
        ],
    ),
    "GenerationContext": MigrationMap(
        "GenerationContext",
        entries=[
            MigrationEntry("", "backend/orchestration/job_manager.py", MigrationType.KEEP, "Job lifecycle complete", 400),
            MigrationEntry("", "backend/orchestration/worker.py", MigrationType.KEEP, "Worker pool complete", 300),
            MigrationEntry("", "backend/providers/__init__.py", MigrationType.KEEP, "Provider system complete", 500),
            MigrationEntry("", "backend/agents/prompt/generation_planner.py", MigrationType.KEEP, "Generation planning & prompt compilation", 300),
            MigrationEntry("", "backend/agents/video/motion_planner.py", MigrationType.KEEP, "Motion planning", 200),
            MigrationEntry("", "backend/agents/voice/audio_director.py", MigrationType.KEEP, "Audio direction", 250),
        ],
    ),
    "MediaContext": MigrationMap(
        "MediaContext",
        entries=[
            MigrationEntry("", "backend/assets/__init__.py", MigrationType.KEEP, "Asset pipeline complete", 450),
        ],
    ),
    "ExportContext": MigrationMap(
        "ExportContext",
        entries=[
            MigrationEntry("", "backend/exporter/__init__.py", MigrationType.KEEP, "Export engine complete", 450),
            MigrationEntry("", "backend/exporter/timeline_engine.py", MigrationType.KEEP, "Timeline compositing", 250),
        ],
    ),
    "CollaborationContext": MigrationMap(
        "CollaborationContext",
        entries=[
            MigrationEntry("", "backend/collaboration/__init__.py", MigrationType.KEEP, "Collaboration system", 500),
        ],
    ),
}


# ── Migration Report Generator ────────────────────────────────────────

class MigrationReport:
    """Generates migration status report."""

    @staticmethod
    def generate() -> dict[str, Any]:
        total_lines = 0
        by_type: dict[str, int] = {t.value: 0 for t in MigrationType}

        for ctx_map in MIGRATION_MAPS.values():
            total_lines += ctx_map.total_estimated_lines
            for entry in ctx_map.entries:
                by_type[entry.migration_type.value] += 1

        return {
            "total_contexts": len(MIGRATION_MAPS),
            "total_estimated_lines": total_lines,
            "entries_by_type": by_type,
            "contexts": {
                name: {
                    "entries": len(ctx_map.entries),
                    "lines": ctx_map.total_estimated_lines,
                }
                for name, ctx_map in MIGRATION_MAPS.items()
            },
        }

    @staticmethod
    def generate_markdown() -> str:
        report = MigrationReport.generate()
        lines = [
            "# Repository Refactoring Plan",
            f"Total estimated lines: {report['total_estimated_lines']}",
            f"Total contexts: {report['total_contexts']}",
            "",
            "## Entries by Type",
        ]
        for t, count in report["entries_by_type"].items():
            lines.append(f"- **{t}**: {count} files")
        lines.append("")
        lines.append("## Per-Context Summary")
        for name, info in report["contexts"].items():
            lines.append(f"- **{name}**: {info['entries']} files, ~{info['lines']} lines")
        return "\n".join(lines)
