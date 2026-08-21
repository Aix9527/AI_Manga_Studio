from sqlalchemy import (
    Column,
    String,
    Text,
    Integer
)

from ..storage.database import Base



class ProductionTaskRecord(Base):

    __tablename__="production_tasks"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String
    )


    shot_id=Column(
        String
    )


    stage=Column(
        Integer
    )


    status=Column(
        String,
        default="queued"
    )


    priority=Column(
        Integer,
        default=2
    )


    failure_count=Column(
        Integer,
        default=0
    )



class TaskAttemptRecord(Base):

    __tablename__="task_attempts"


    id=Column(
        String,
        primary_key=True
    )


    task_id=Column(
        String
    )


    status=Column(
        String
    )


    error_category=Column(
        String
    )


    log_json=Column(
        Text
    )



class CheckpointRecord(Base):

    __tablename__="task_checkpoints"


    id=Column(
        String,
        primary_key=True
    )


    task_id=Column(
        String
    )


    stage=Column(
        Integer
    )


    state_json=Column(
        Text
    )


    completed=Column(
        Integer,
        default=0
    )
