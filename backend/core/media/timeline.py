import json

from ..domain.ids import create_id

from ..storage.media_models import (
    TimelineTrackRecord,
    TimelineClipRecord
)



class TimelineService:



    def __init__(
        self,
        db
    ):

        self.db=db



    def create_track(
        self,
        project_id,
        track_type,
        name
    ):


        track=TimelineTrackRecord(

            id=create_id(
                "track"
            ),

            project_id=project_id,

            track_type=track_type,

            name=name

        )


        self.db.add(track)

        self.db.commit()


        return track.id




    def add_clip(
        self,
        track_id,
        asset_id,
        media_type,
        start,
        duration,
        metadata={}
    ):


        clip=TimelineClipRecord(

            id=create_id(
                "clip"
            ),

            track_id=track_id,

            asset_id=asset_id,

            start=start,

            duration=duration,

            media_type=media_type,

            metadata_json=json.dumps(
                metadata,
                ensure_ascii=False
            )

        )


        self.db.add(clip)

        self.db.commit()


        return clip.id
