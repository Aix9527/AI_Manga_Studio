from __future__ import annotations

from sqlalchemy import (
    String,
    Text,
    Integer
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from .database import Base



class ProjectRecord(Base):

    __tablename__ = "projects"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    name: Mapped[str] = mapped_column(
        String(256)
    )


    content_type: Mapped[str] = mapped_column(
        String(64),
        default="anime"
    )


    created_at: Mapped[str] = mapped_column(
        String(64),
        default=""
    )


    source_path: Mapped[str] = mapped_column(
        Text,
        default=""
    )



class SeasonRecord(Base):

    __tablename__ = "seasons"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    project_id: Mapped[str] = mapped_column(
        String(64)
    )

    name: Mapped[str] = mapped_column(
        String(256)
    )



class EpisodeRecord(Base):

    __tablename__ = "episodes"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    season_id: Mapped[str] = mapped_column(
        String(64)
    )

    title: Mapped[str] = mapped_column(
        String(256)
    )



class SceneRecord(Base):

    __tablename__="scenes"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    episode_id: Mapped[str] = mapped_column(
        String(64)
    )

    location: Mapped[str] = mapped_column(
        String(256),
        default=""
    )



class ShotRecord(Base):

    __tablename__="shots"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    scene_id: Mapped[str] = mapped_column(
        String(64)
    )

    name: Mapped[str] = mapped_column(
        String(256)
    )

    status: Mapped[str] = mapped_column(
        String(64),
        default="draft"
    )



class AssetRecord(Base):

    __tablename__="assets"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    project_id: Mapped[str] = mapped_column(
        String(64)
    )


    asset_type: Mapped[str] = mapped_column(
        String(64)
    )


    name: Mapped[str] = mapped_column(
        String(256)
    )


    relative_path: Mapped[str] = mapped_column(
        Text,
        default=""
    )


    path: Mapped[str] = mapped_column(
        Text,
        default=""
    )


    sha256: Mapped[str] = mapped_column(
        String(128),
        default=""
    )



class AssetVersionRecord(Base):

    __tablename__="asset_versions"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    asset_id: Mapped[str] = mapped_column(
        String(64)
    )


    path: Mapped[str] = mapped_column(
        Text
    )


    sha256: Mapped[str] = mapped_column(
        String(128)
    )



class LineageEdgeRecord(Base):

    __tablename__="lineage_edges"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    parent_id: Mapped[str] = mapped_column(
        String(64)
    )


    child_id: Mapped[str] = mapped_column(
        String(64)
    )


    relation: Mapped[str] = mapped_column(
        String(128)
    )


class MigrationRecord(Base):

    __tablename__="migration_records"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    source_path: Mapped[str] = mapped_column(
        Text,
        unique=True
    )


    target_id: Mapped[str] = mapped_column(
        String(64)
    )


class PromptRecipeRecord(Base):

    __tablename__ = "prompt_recipes"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    shot_id: Mapped[str] = mapped_column(
        String(64)
    )


    prompt_text: Mapped[str] = mapped_column(
        Text,
        default=""
    )


    negative_prompt: Mapped[str] = mapped_column(
        Text,
        default=""
    )



class WorkflowVersionRecord(Base):

    __tablename__ = "workflow_versions"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    shot_id: Mapped[str] = mapped_column(
        String(64)
    )


    workflow_name: Mapped[str] = mapped_column(
        String(256)
    )


    workflow_hash: Mapped[str] = mapped_column(
        String(128),
        default=""
    )



class ModelArtifactRecord(Base):

    __tablename__ = "model_artifacts"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    production_run_id: Mapped[str] = mapped_column(
        String(64)
    )


    model_name: Mapped[str] = mapped_column(
        String(256)
    )


    sha256: Mapped[str] = mapped_column(
        String(128)
    )



class ProductionRunRecord(Base):

    __tablename__ = "production_runs"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    shot_id: Mapped[str] = mapped_column(
        String(64)
    )


    seed: Mapped[str] = mapped_column(
        String(64),
        default=""
    )


    cfg: Mapped[str] = mapped_column(
        String(32),
        default=""
    )


    steps: Mapped[str] = mapped_column(
        String(32),
        default=""
    )


    motion_profile: Mapped[str] = mapped_column(
        String(128),
        default=""
    )



class QualityEvaluationRecord(Base):

    __tablename__ = "quality_evaluations"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    asset_id: Mapped[str] = mapped_column(
        String(64),
        default=""
    )


    shot_id: Mapped[str] = mapped_column(
        String(64)
    )


    gate: Mapped[str] = mapped_column(
        String(32),
        default=""
    )


    score: Mapped[str] = mapped_column(
        String(32),
        default=""
    )


    result: Mapped[str] = mapped_column(
        String(32),
        default=""
    )


    evidence_json: Mapped[str] = mapped_column(
        Text,
        default=""
    )


    created_at: Mapped[str] = mapped_column(
        String(64),
        default=""
    )



class DefectRecord(Base):

    __tablename__="defects"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    shot_id: Mapped[str] = mapped_column(
        String(64)
    )


    category: Mapped[str] = mapped_column(
        String(128)
    )


    severity: Mapped[str] = mapped_column(
        String(32),
        default="medium"
    )


    message: Mapped[str] = mapped_column(
        Text,
        default=""
    )


    description: Mapped[str] = mapped_column(
        Text,
        default=""
    )


    repair_task_id: Mapped[str] = mapped_column(
        String(64),
        default=""
    )


    resolved: Mapped[int] = mapped_column(
        Integer,
        default=0
    )
