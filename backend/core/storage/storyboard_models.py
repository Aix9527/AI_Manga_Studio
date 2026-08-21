from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float
)

from ..storage.database import Base



class ShotBoardRecord(Base):

    __tablename__="shot_boards"


    id=Column(
        String,
        primary_key=True
    )


    shot_id=Column(
        String,
        nullable=False
    )


    shot_size=Column(
        String
    )


    camera_move=Column(
        String
    )


    composition_json=Column(
        Text
    )


    action_json=Column(
        Text
    )


    prompt_text=Column(
        Text
    )


    duration=Column(
        Float,
        default=5
    )



class SceneContinuityRecord(Base):

    __tablename__="scene_continuity"


    id=Column(
        String,
        primary_key=True
    )


    scene_id=Column(
        String,
        nullable=False
    )


    time_state=Column(
        String
    )


    location_state=Column(
        String
    )


    weather=Column(
        String
    )


    lighting=Column(
        String
    )


    character_state_json=Column(
        Text
    )



class TimelineClipRecord(Base):

    __tablename__="timeline_clips"


    id=Column(
        String,
        primary_key=True
    )


    shot_id=Column(
        String
    )


    track_type=Column(
        String
    )


    start_time=Column(
        Float
    )


    duration=Column(
        Float
    )


    asset_id=Column(
        String
    )
