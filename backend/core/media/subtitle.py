from ..domain.ids import create_id

from ..storage.media_models import (
SubtitleSegmentRecord
)



class SubtitleService:



    def __init__(
        self,
        db
    ):

        self.db=db



    def create_segment(
        self,
        episode_id,
        start,
        end,
        text
    ):


        item=SubtitleSegmentRecord(

            id=create_id(
                "subtitle"
            ),

            episode_id=episode_id,

            start=start,

            end=end,

            text=text,

            source="whisper"

        )


        self.db.add(item)

        self.db.commit()


        return item.id
