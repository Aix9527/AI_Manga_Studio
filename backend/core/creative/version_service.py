import json


from ..domain.ids import create_id


from ..storage.creative_models import (
    CharacterVersionRecord
)



class CharacterVersionService:



    def __init__(
        self,
        db
    ):

        self.db=db




    def create_version(
        self,
        character_id,
        data
    ):


        latest=(

            self.db.query(
                CharacterVersionRecord
            )

            .filter_by(
                character_id=
                character_id
            )

            .count()

        )


        version=f"v{latest+1}"



        obj=CharacterVersionRecord(

            id=create_id(
                "charver"
            ),

            character_id=
            character_id,

            version=
            version,

            appearance_json=
            json.dumps(
                data,
                ensure_ascii=False
            ),

            costume_json="{}",

            voice_json=""

        )


        self.db.add(
            obj
        )

        self.db.commit()



        return obj.id
