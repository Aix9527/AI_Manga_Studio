from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Integer
)

from ..storage.database import Base



class TimelineTrackRecord(Base):

    __tablename__="timeline_tracks"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String
    )


    track_type=Column(
        String
    )


    name=Column(
        String
    )



class TimelineClipRecord(Base):

    __tablename__="timeline_media_clips"


    id=Column(
        String,
        primary_key=True
    )


    track_id=Column(
        String
    )


    asset_id=Column(
        String
    )


    start=Column(
        Float
    )


    duration=Column(
        Float
    )


    media_type=Column(
        String
    )


    metadata_json=Column(
        Text
    )



class SubtitleSegmentRecord(Base):

    __tablename__="subtitle_segments"


    id=Column(
        String,
        primary_key=True
    )


    episode_id=Column(
        String
    )


    start=Column(
        Float
    )


    end=Column(
        Float
    )


    text=Column(
        Text
    )


    source=Column(
        String
    )



class ExportPackageRecord(Base):

    __tablename__="export_packages"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String
    )


    format=Column(
        String
    )


    resolution=Column(
        String
    )


    path=Column(
        String
    )


    status=Column(
        String
    )
