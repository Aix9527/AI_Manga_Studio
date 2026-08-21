import json


from datetime import datetime


from ..domain.ids import create_id


from ..storage.canvas_models import (
    CanvasNodeRecord,
    CanvasEdgeRecord,
    CanvasSnapshotRecord
)



class CanvasRepository:



    def __init__(
        self,
        db
    ):

        self.db=db



    def create_node(
        self,
        project_id,
        node_type,
        title,
        ref_id="",
        position=None,
        data=None
    ):


        node=CanvasNodeRecord(

            id=create_id(
                "canvas_node"
            ),

            project_id=project_id,

            node_type=node_type,

            title=title,

            ref_id=ref_id,

            position_json=json.dumps(

                position or
                {
                    "x":0,
                    "y":0
                }

            ),

            data_json=json.dumps(
                data or {}
            )

        )


        self.db.add(
            node
        )

        self.db.commit()


        return node.id




    def create_edge(
        self,
        project_id,
        source,
        target,
        relation
    ):


        edge=CanvasEdgeRecord(

            id=create_id(
                "canvas_edge"
            ),

            project_id=project_id,

            source_id=source,

            target_id=target,

            relation=relation

        )


        self.db.add(edge)

        self.db.commit()


        return edge.id





    def snapshot(
        self,
        project_id
    ):


        nodes=(

            self.db.query(
                CanvasNodeRecord
            )

            .filter_by(
                project_id=project_id
            )

            .all()

        )


        edges=(

            self.db.query(
                CanvasEdgeRecord
            )

            .filter_by(
                project_id=project_id
            )

            .all()

        )



        snap=CanvasSnapshotRecord(

            id=create_id(
                "canvas_snapshot"
            ),

            project_id=project_id,

            name=
            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S"
            ),

            nodes_json=json.dumps(

                [
                    n.id
                    for n in nodes
                ]

            ),

            edges_json=json.dumps(

                [
                    e.id
                    for e in edges
                ]

            ),

            created_at=
            datetime.now()
            .isoformat()

        )


        self.db.add(
            snap
        )

        self.db.commit()


        return snap.id
