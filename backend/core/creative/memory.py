from ..domain.ids import create_id

from ..storage.creative_models import NarrativeMemoryRecord



class NarrativeMemory:


    def __init__(
        self,
        db
    ):

        self.db=db



    def remember(
        self,
        project_id,
        category,
        key,
        value,
        priority=0
    ):


        item=NarrativeMemoryRecord(

            id=create_id(
                "memory"
            ),

            project_id=project_id,

            category=category,

            key=key,

            value=value,

            priority=priority

        )


        self.db.add(item)

        self.db.commit()


        return item
