from sqlalchemy import (
    Column,
    String,
    Text,
    Integer
)

from ..storage.database import Base


# ==========================
# Creative Core
# ==========================


class WorldBibleRecord(Base):

    __tablename__="world_bibles"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    title=Column(
        String
    )


    description=Column(
        Text
    )


    rules_json=Column(
        Text
    )



class CharacterBibleRecord(Base):

    __tablename__="character_bibles"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    name=Column(
        String
    )


    identity=Column(
        Text
    )


    personality=Column(
        Text
    )


    locked=Column(
        Integer,
        default=0
    )




class CharacterVersionRecord(Base):

    __tablename__="character_versions"


    id=Column(
        String,
        primary_key=True
    )


    character_id=Column(
        String,
        nullable=False
    )


    version=Column(
        String
    )


    appearance_json=Column(
        Text
    )


    costume_json=Column(
        Text
    )


    voice_json=Column(
        Text
    )


    content_hash=Column(
        String
    )




class LocationVersionRecord(Base):

    __tablename__="location_versions"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    name=Column(
        String
    )


    state_json=Column(
        Text
    )


    content_hash=Column(
        String
    )




class NarrativeMemoryRecord(Base):

    __tablename__="narrative_memory"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    category=Column(
        String
    )


    key=Column(
        String
    )


    value=Column(
        Text
    )


    priority=Column(
        Integer,
        default=0
    )



class StoryElementRecord(Base):

    __tablename__="story_elements"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    element_type=Column(
        String
    )


    name=Column(
        String
    )


    content=Column(
        Text
    )


class ChangeProposalRecord(Base):

    __tablename__="change_proposals"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    target_type=Column(
        String
    )


    target_id=Column(
        String
    )


    operation=Column(
        String
    )


    diff_json=Column(
        Text
    )


    status=Column(
        String,
        default="pending"
    )


    created_by=Column(
        String,
        default="ai"
    )
