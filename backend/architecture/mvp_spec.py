"""
Executable MVP Specification & Domain Contracts (Part 39)

Defines the MVP in concrete, testable terms:
- Domain aggregates and their boundaries
- Database schema generation
- API contracts (OpenAPI)
- User story → acceptance test mapping
- Golden test specifications
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StoryPriority(str, Enum):
    P0_BLOCKER = "P0"
    P1_CRITICAL = "P1"
    P2_IMPORTANT = "P2"
    P3_NICE_TO_HAVE = "P3"


class StoryStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    READY_FOR_TEST = "ready_for_test"
    DONE = "done"


@dataclass
class UserStory:
    """A single user story with acceptance criteria."""
    story_id: str
    title: str
    description: str
    priority: StoryPriority = StoryPriority.P2_IMPORTANT
    status: StoryStatus = StoryStatus.TODO

    acceptance_criteria: list[str] = field(default_factory=list)
    golden_test: str = ""  # Key scenario for regression testing
    related_modules: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


# ── MVP User Stories ──────────────────────────────────────────────────

MVP_USER_STORIES: list[UserStory] = [
    UserStory(
        "US-001",
        "Create New Project",
        "As a creator, I can create a new manga/anime project with a name, description, and target format.",
        StoryPriority.P0_BLOCKER,
        acceptance_criteria=[
            "User can create project via API POST /api/projects",
            "Project has auto-generated UUID",
            "Project status transitions: draft → in_progress → completed → archived",
            "Invalid input returns 422 with clear error messages",
        ],
        golden_test="Create project, verify all fields persisted, check GET returns same data.",
        related_modules=["projects/", "api/", "database/"],
    ),
    UserStory(
        "US-002",
        "Import & Parse Novel",
        "As a creator, I can import a novel text and have it automatically parsed into chapters, scenes, and characters.",
        StoryPriority.P0_BLOCKER,
        acceptance_criteria=[
            "Upload novel via API POST /api/projects/{id}/novel",
            "StoryAgent parses into structured chapters",
            "CharacterAgent extracts character names and attributes",
            "SceneAgent breaks story into individual scenes",
            "Long novels (>50K chars) complete within 60 seconds",
        ],
        golden_test="Upload 'Journey to the West' sample, verify 10+ chapters, 5+ characters extracted.",
        related_modules=["agents/story/", "agents/character/", "agents/scene/"],
    ),
    UserStory(
        "US-003",
        "Design Characters with Visual Identity",
        "As a creator, I can design characters with consistent visual identity (hair color, costume, etc.) that persists across scenes.",
        StoryPriority.P0_BLOCKER,
        acceptance_criteria=[
            "Character DNA stores: name, role, appearance attributes, reference images",
            "CharacterMemory ensures visual consistency across scenes",
            "User can edit DNA attributes and see regenerated preview",
            "Character gallery shows all project characters with thumbnails",
        ],
        golden_test="Create character with specific hair/eyes/clothing, generate 3 scenes, verify visual consistency.",
        related_modules=["agents/character/", "memory/"],
    ),
    UserStory(
        "US-004",
        "Create Storyboard with Shots",
        "As a creator, I can create a storyboard with numbered shots, each with camera angle, duration, and description.",
        StoryPriority.P0_BLOCKER,
        acceptance_criteria=[
            "Storyboard shows all shots from scene breakdown",
            "Each shot has: number, description, camera angle, duration, characters",
            "User can reorder shots via drag-and-drop",
            "Shot detail panel shows full properties editable",
        ],
        golden_test="Create 24-shot storyboard, reorder shots 5-10, verify persisting.",
        related_modules=["agents/scene/", "workflow/"],
    ),
    UserStory(
        "US-005",
        "Generate Keyframe Images",
        "As a creator, I can generate keyframe images for each storyboard shot using AI.",
        StoryPriority.P1_CRITICAL,
        acceptance_criteria=[
            "Select shot → click 'Generate Image'",
            "ImageProvider routes to configured AI backend (OpenAI, ComfyUI, etc.)",
            "Generation progress shown in real-time",
            "Generated image matches shot description and character designs",
            "Failed generation can be retried with a single click",
            "Multiple shots can be queued for parallel generation",
        ],
        golden_test="Generate 5-shots, verify all images match character DNA and shot descriptions.",
        related_modules=["providers/", "orchestration/", "workflow/"],
    ),
    UserStory(
        "US-006",
        "Generate Video Clips from Keyframes",
        "As a creator, I can generate animated video clips from keyframe images.",
        StoryPriority.P1_CRITICAL,
        acceptance_criteria=[
            "Select keyframe → click 'Generate Video'",
            "VideoProvider generates I2V clip with motion planning",
            "Motion type configurable (pan, zoom, tracking)",
            "Duration configurable (1-10 seconds)",
            "Temporal continuity verified between consecutive clips",
        ],
        golden_test="Generate 3-video sequence, verify smooth transitions between clips.",
        related_modules=["agents/video/", "providers/", "workflow/"],
    ),
    UserStory(
        "US-007",
        "Generate Voice & Audio",
        "As a creator, I can generate voice dialogue and background audio for the production.",
        StoryPriority.P1_CRITICAL,
        acceptance_criteria=[
            "Voice profiles matched to character DNA",
            "Dialogue extracted from script and assigned to characters",
            "VoiceProvider generates audio clips for each dialogue line",
            "BGM/SFX matched to scene mood",
            "Audio timeline synced with video timeline",
        ],
        golden_test="Generate dialogue for 3 characters, verify voice matches character profile, BGM matches mood.",
        related_modules=["agents/voice/", "providers/"],
    ),
    UserStory(
        "US-008",
        "Edit Timeline & Export Final Video",
        "As a creator, I can arrange clips on a timeline and export the final video.",
        StoryPriority.P1_CRITICAL,
        acceptance_criteria=[
            "Timeline shows video + audio tracks with clips",
            "Clips can be trimmed, rearranged, and cross-faded",
            "Export with format presets (MP4/H264, MP4/H265, WebM/VP9)",
            "Export progress shown with estimated time",
            "Final video plays correctly with synced audio",
        ],
        golden_test="Export 60-second timeline, verify video/audio sync, file plays in VLC.",
        related_modules=["exporter/", "exporter/timeline_engine.py"],
    ),
    UserStory(
        "US-009",
        "Plugin System",
        "As a developer, I can install third-party plugins that extend the platform.",
        StoryPriority.P2_IMPORTANT,
        acceptance_criteria=[
            "Plugin installation from zip or GitHub",
            "Manifest validation (version, capabilities, permissions)",
            "Plugin lifecycle: install → activate → run → deactivate → uninstall",
            "Fault isolation: plugin crash does not crash the platform",
            "Permissions enforced at runtime",
        ],
        golden_test="Install a mock Agent plugin, verify it registers and can be called.",
        related_modules=["plugins/"],
    ),
    UserStory(
        "US-010",
        "Multi-User Collaboration",
        "As a team, we can collaborate on the same project in real-time.",
        StoryPriority.P2_IMPORTANT,
        acceptance_criteria=[
            "Multiple users can join same project",
            "Presence shows who is online and what they are editing",
            "Changes are broadcast in real-time via WebSocket",
            "Conflicts detected and resolved with last-write-wins",
            "Roles enforced (owner/editor/reviewer/viewer)",
        ],
        golden_test="Two users edit same shot, verify conflict resolution.",
        related_modules=["collaboration/"],
    ),
]


# ── Database Schema ───────────────────────────────────────────────────

@dataclass
class DBColumn:
    """A database column definition."""
    name: str
    type: str
    nullable: bool = False
    primary_key: bool = False
    foreign_key: str = ""
    default: str = ""
    index: bool = False
    unique: bool = False


@dataclass
class DBTable:
    """A database table definition."""
    name: str
    columns: list[DBColumn]
    description: str = ""


# ── MVP Database Schema ───────────────────────────────────────────────

MVP_DATABASE_SCHEMA: list[DBTable] = [
    DBTable("projects", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("name", "VARCHAR(255)", nullable=False),
        DBColumn("description", "TEXT"),
        DBColumn("status", "VARCHAR(50)", nullable=False, default="draft"),
        DBColumn("target_format", "VARCHAR(50)"),
        DBColumn("settings", "JSONB"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", nullable=False, default="1"),
    ], "Project aggregate root"),
    DBTable("stories", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("project_id", "UUID", foreign_key="projects.id", index=True),
        DBColumn("title", "VARCHAR(500)"),
        DBColumn("raw_text", "TEXT"),
        DBColumn("parsed_json", "JSONB"),
        DBColumn("chapter_count", "INTEGER"),
        DBColumn("scene_count", "INTEGER"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", default="1"),
    ], "Parsed story with chapters"),
    DBTable("characters", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("project_id", "UUID", foreign_key="projects.id", index=True),
        DBColumn("name", "VARCHAR(255)", nullable=False),
        DBColumn("role", "VARCHAR(50)"),
        DBColumn("character_dna", "JSONB"),
        DBColumn("reference_images", "JSONB"),
        DBColumn("voice_profile_id", "VARCHAR(255)"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", default="1"),
    ], "Character aggregate with DNA"),
    DBTable("storyboards", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("project_id", "UUID", foreign_key="projects.id", index=True),
        DBColumn("shots", "JSONB"),
        DBColumn("total_duration_seconds", "FLOAT"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", default="1"),
    ], "Storyboard with shot array"),
    DBTable("generation_plans", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("project_id", "UUID", foreign_key="projects.id", index=True),
        DBColumn("plan_json", "JSONB", nullable=False),
        DBColumn("status", "VARCHAR(50)", default="pending"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", default="1"),
    ], "Generation plan (execution truth)"),
    DBTable("jobs", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("project_id", "UUID", foreign_key="projects.id", index=True),
        DBColumn("plan_id", "UUID", foreign_key="generation_plans.id"),
        DBColumn("job_type", "VARCHAR(100)", nullable=False),
        DBColumn("status", "VARCHAR(50)", nullable=False, default="pending"),
        DBColumn("node_id", "VARCHAR(255)"),
        DBColumn("input_data", "JSONB"),
        DBColumn("output_data", "JSONB"),
        DBColumn("error_message", "TEXT"),
        DBColumn("progress", "FLOAT", default="0.0"),
        DBColumn("retry_count", "INTEGER", default="0"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", default="1"),
    ], "Job entity for orchestration"),
    DBTable("asset_versions", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("asset_id", "VARCHAR(255)", nullable=False, index=True),
        DBColumn("project_id", "UUID", foreign_key="projects.id", index=True),
        DBColumn("file_path", "TEXT", nullable=False),
        DBColumn("mime_type", "VARCHAR(100)"),
        DBColumn("file_size_bytes", "BIGINT"),
        DBColumn("width", "INTEGER"),
        DBColumn("height", "INTEGER"),
        DBColumn("duration_seconds", "FLOAT"),
        DBColumn("metadata", "JSONB"),
        DBColumn("version", "INTEGER", nullable=False, default="1"),
        DBColumn("status", "VARCHAR(50)", default="ready"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", default="1"),
    ], "Asset version (media truth)"),
    DBTable("timeline_clips", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("project_id", "UUID", foreign_key="projects.id", index=True),
        DBColumn("asset_version_id", "UUID", foreign_key="asset_versions.id"),
        DBColumn("track_index", "INTEGER", nullable=False),
        DBColumn("is_audio", "BOOLEAN", default="false"),
        DBColumn("start_time_seconds", "FLOAT", nullable=False),
        DBColumn("duration_seconds", "FLOAT", nullable=False),
        DBColumn("in_point_seconds", "FLOAT", default="0.0"),
        DBColumn("volume", "FLOAT", default="1.0"),
        DBColumn("opacity", "FLOAT", default="1.0"),
        DBColumn("transition", "VARCHAR(50)"),
        DBColumn("effects", "JSONB"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", default="1"),
    ], "Timeline clip (references asset_version)"),
    DBTable("exports", [
        DBColumn("id", "UUID", primary_key=True),
        DBColumn("project_id", "UUID", foreign_key="projects.id", index=True),
        DBColumn("output_path", "TEXT"),
        DBColumn("format", "VARCHAR(50)"),
        DBColumn("codec", "VARCHAR(50)"),
        DBColumn("file_size_bytes", "BIGINT"),
        DBColumn("duration_seconds", "FLOAT"),
        DBColumn("status", "VARCHAR(50)", default="pending"),
        DBColumn("created_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("completed_at", "TIMESTAMPTZ"),
        DBColumn("updated_at", "TIMESTAMPTZ", nullable=False),
        DBColumn("revision", "INTEGER", default="1"),
    ], "Export aggregate"),
]


# ── Specification Generator ───────────────────────────────────────────

class MVPSpecGenerator:
    """Generates the complete MVP specification document."""

    @staticmethod
    def generate_stories() -> list[dict[str, Any]]:
        return [
            {
                "id": s.story_id,
                "title": s.title,
                "priority": s.priority.value,
                "acceptance_criteria": s.acceptance_criteria,
                "golden_test": s.golden_test,
            }
            for s in MVP_USER_STORIES
        ]

    @staticmethod
    def generate_schema_sql() -> str:
        """Generate PostgreSQL DDL from schema definitions."""
        lines = ["-- AI_Manga_Studio MVP Database Schema", "-- Generated from Part 39", ""]
        for table in MVP_DATABASE_SCHEMA:
            lines.append(f"-- {table.description}")
            lines.append(f"CREATE TABLE IF NOT EXISTS {table.name} (")
            col_defs = []
            for col in table.columns:
                parts = [f"  {col.name} {col.type}"]
                if col.primary_key:
                    parts.append("PRIMARY KEY")
                if col.nullable is False:
                    parts.append("NOT NULL")
                if col.unique:
                    parts.append("UNIQUE")
                if col.default:
                    parts.append(f"DEFAULT {col.default}")
                if col.foreign_key:
                    parts.append(f"REFERENCES {col.foreign_key}")
                col_defs.append(" ".join(parts))
            lines.append(",\n".join(col_defs))
            lines.append(");\n")
        return "\n".join(lines)

    @staticmethod
    def generate_markdown() -> str:
        report_lines = [
            "# MVP Specification",
            f"Total user stories: {len(MVP_USER_STORIES)}",
            f"Total database tables: {len(MVP_DATABASE_SCHEMA)}",
            "",
            "## User Stories",
        ]
        for s in MVP_USER_STORIES:
            report_lines.append(f"### {s.story_id}: {s.title} [{s.priority.value}]")
            report_lines.append(f"{s.description}")
            report_lines.append("**Acceptance Criteria:**")
            for ac in s.acceptance_criteria:
                report_lines.append(f"- [ ] {ac}")
            report_lines.append(f"**Golden Test:** {s.golden_test}")
            report_lines.append("")

        report_lines.append("## Database Schema")
        for table in MVP_DATABASE_SCHEMA:
            report_lines.append(f"### {table.name}")
            report_lines.append(f"> {table.description}")
            report_lines.append("| Column | Type | Constraints |")
            report_lines.append("|--------|------|-------------|")
            for col in table.columns:
                constraints = []
                if col.primary_key: constraints.append("PK")
                if col.nullable is False: constraints.append("NOT NULL")
                if col.unique: constraints.append("UNIQUE")
                if col.foreign_key: constraints.append(f"FK → {col.foreign_key}")
                if col.index: constraints.append("INDEX")
                report_lines.append(f"| {col.name} | {col.type} | {', '.join(constraints) or '-'} |")
            report_lines.append("")
        return "\n".join(report_lines)
