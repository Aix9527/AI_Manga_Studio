from ..domain.ids import create_id

from ..storage.creative_models import (
    WorldBibleRecord,
    CharacterBibleRecord,
    CharacterVersionRecord
)



class CreativeRepository:



    def __init__(
        self,
        db
    ):

        self.db=db



    def create_world(
        self,
        project_id,
        title,
        description=""
    ):


        obj=WorldBibleRecord(

            id=create_id(
                "world"
            ),

            project_id=project_id,

            title=title,

            description=description,

            rules_json="{}"

        )


        self.db.add(obj)

        self.db.commit()


        return obj




    def create_character(
        self,
        project_id,
        name,
        identity
    ):


        obj=CharacterBibleRecord(

            id=create_id(
                "char"
            ),

            project_id=project_id,

            name=name,

            identity=identity

        )


        self.db.add(obj)

        self.db.commit()


        return obj
