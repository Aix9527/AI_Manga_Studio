from ..storage.models import ShotRecord


from ..storage.canvas_models import CanvasNodeRecord


from ..domain.ids import create_id



class CanvasProductionSync:



    def __init__(
        self,
        db
    ):

        self.db=db



    def sync_shots(
        self,
        project_id
    ):


        shots=(

            self.db.query(
                ShotRecord
            )

            .all()

        )


        created=[]


        for shot in shots:


            exists=(

                self.db.query(
                    CanvasNodeRecord
                )

                .filter_by(
                    ref_id=shot.id
                )

                .first()

            )


            if exists:

                continue



            node=CanvasNodeRecord(

                id=create_id(
                    "canvas_node"
                ),

                project_id=project_id,

                node_type="shot",

                ref_id=shot.id,

                title=shot.name,

                position_json='{"x":0,"y":0}',

                data_json='{}'

            )


            self.db.add(
                node
            )


            created.append(
                shot.id
            )


        self.db.commit()


        return created
