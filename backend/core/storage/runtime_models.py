from sqlalchemy import (
    Column,
    String,
    Text,
    Integer
)

from ..storage.database import Base



class ModelArtifactRecord(Base):

    __tablename__="runtime_models"


    id=Column(
        String,
        primary_key=True
    )


    name=Column(
        String
    )


    model_type=Column(
        String
    )


    provider=Column(
        String
    )


    sha256=Column(
        String
    )


    path=Column(
        String
    )


    status=Column(
        String,
        default="available"
    )



class WorkflowVersionRecord(Base):

    __tablename__="runtime_workflows"


    id=Column(
        String,
        primary_key=True
    )


    name=Column(
        String
    )


    version=Column(
        String
    )


    provider=Column(
        String
    )


    config_json=Column(
        Text
    )



class ProviderRouteRecord(Base):

    __tablename__="provider_routes"


    id=Column(
        String,
        primary_key=True
    )


    stage=Column(
        String
    )


    content_type=Column(
        String
    )


    provider=Column(
        String
    )


    model_id=Column(
        String
    )


    priority=Column(
        Integer,
        default=0
    )



class AgentSkillRecord(Base):

    __tablename__="agent_skills"


    id=Column(
        String,
        primary_key=True
    )


    name=Column(
        String
    )


    role=Column(
        String
    )


    input_schema=Column(
        Text
    )


    output_schema=Column(
        Text
    )


    read_domains=Column(
        Text
    )


    write_domains=Column(
        Text
    )


    allow_cloud=Column(
        Integer,
        default=0
    )



class CloudAuthorizationRecord(Base):

    __tablename__="cloud_authorizations"


    id=Column(
        String,
        primary_key=True
    )


    task_id=Column(
        String
    )


    provider=Column(
        String
    )


    scope_json=Column(
        Text
    )


    approved=Column(
        Integer,
        default=0
    )


class AgentRunRecord(Base):

    __tablename__="agent_runs"


    id=Column(
        String,
        primary_key=True
    )


    skill_id=Column(
        String
    )


    task_id=Column(
        String
    )


    input_json=Column(
        Text
    )


    output_json=Column(
        Text
    )


    model_id=Column(
        String
    )


    workflow_id=Column(
        String
    )


    status=Column(
        String,
        default="running"
    )



class ProductionEvidenceRecord(Base):

    __tablename__="production_evidence"


    id=Column(
        String,
        primary_key=True
    )


    run_id=Column(
        String
    )


    evidence_type=Column(
        String
    )


    content_json=Column(
        Text
    )



class FailureRecord(Base):

    __tablename__="runtime_failures"


    id=Column(
        String,
        primary_key=True
    )


    run_id=Column(
        String
    )


    category=Column(
        String
    )


    message=Column(
        Text
    )
