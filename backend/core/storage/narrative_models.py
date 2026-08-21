from sqlalchemy import (
    Column,
    String,
    Text,
    Integer
)

from .database import Base


class NarrativeImportRecord(Base):

    __tablename__="narrative_imports"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    filename=Column(
        String
    )


    sha256=Column(
        String
    )


    status=Column(
        String,
        default="imported"
    )



class StoryDraftRecord(Base):

    __tablename__="story_drafts"


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


    summary=Column(
        Text
    )



class EpisodeDraftRecord(Base):

    __tablename__="episode_drafts"


    id=Column(
        String,
        primary_key=True
    )


    story_id=Column(
        String,
        nullable=False
    )


    index=Column(
        Integer
    )


    title=Column(
        String
    )


    summary=Column(
        Text
    )



class SceneDraftRecord(Base):

    __tablename__="scene_drafts"


    id=Column(
        String,
        primary_key=True
    )


    episode_id=Column(
        String,
        nullable=False
    )


    index=Column(
        Integer
    )


    description=Column(
        Text
    )



class ShotDraftRecord(Base):

    __tablename__="shot_drafts"


    id=Column(
        String,
        primary_key=True
    )


    scene_id=Column(
        String,
        nullable=False
    )


    index=Column(
        Integer
    )


    description=Column(
        Text
    )


    camera=Column(
        String
    )


    prompt_hint=Column(
        Text
    )
