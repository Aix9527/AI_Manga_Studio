from ..domain.ids import create_id


from ..storage.storyboard_models import (
    TimelineClipRecord
)



class TimelineSync:



    def __init__(
        self,
        db
    ):

        self.db=db



    def generate_from_shots(
        self,
        shots
    ):


        current=0

        result=[]



        for shot in shots:


            duration=5



            clip=TimelineClipRecord(

                id=create_id(
                    "clip"
                ),

                shot_id=shot.id,

                track_type="video",

                start_time=current,

                duration=duration

            )


            self.db.add(
                clip
            )


            current+=duration


            result.append(
                clip.id
            )


        self.db.commit()


        return result
