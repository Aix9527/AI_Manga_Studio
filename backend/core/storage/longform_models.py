from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    JSON
)

from .database import Base



class SeriesRecord(Base):

    __tablename__="series"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        index=True
    )


    title=Column(
        String
    )


    genre=Column(
        String
    )


    episode_count=Column(
        Integer,
        default=0
    )


    status=Column(
        String,
        default="draft"
    )


    created_at=Column(
        String,
        default=lambda:
        datetime.utcnow().isoformat()
    )




class SeasonPlanRecord(Base):

    __tablename__="season_plans"


    id=Column(
        String,
        primary_key=True
    )


    series_id=Column(
        String,
        index=True
    )


    season_no=Column(
        Integer
    )


    episode_start=Column(
        Integer
    )


    episode_end=Column(
        Integer
    )


    resource_plan=Column(
        JSON
    )




class EpisodeScheduleRecord(Base):

    __tablename__="episode_schedule"


    id=Column(
        String,
        primary_key=True
    )


    episode_id=Column(
        String,
        index=True
    )


    priority=Column(
        Integer,
        default=2
    )


    estimated_hours=Column(
        Float
    )


    gpu_hours=Column(
        Float
    )


    status=Column(
        String,
        default="planned"
    )




class ResourceForecastRecord(Base):

    __tablename__="resource_forecast"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String
    )


    gpu_hours=Column(
        Float
    )


    storage_gb=Column(
        Float
    )


    estimated_days=Column(
        Float
    )


    detail=Column(
        JSON
    )




class KnowledgeGraphRecord(Base):

    __tablename__="knowledge_graph"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String
    )


    node_type=Column(
        String
    )


    node_id=Column(
        String
    )


    relation=Column(
        String
    )


    target_id=Column(
        String
    )


    metadata_json=Column(
        JSON
    )




class DigitalTwinRecord(Base):

    __tablename__="digital_twins"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String
    )


    state=Column(
        JSON
    )




class StressTestRecord(Base):

    __tablename__="stress_tests"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String
    )


    episodes=Column(
        Integer
    )


    shots=Column(
        Integer
    )


    duration_hours=Column(
        Float
    )


    result=Column(
        String
    )
