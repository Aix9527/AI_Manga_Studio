from fastapi import APIRouter


from backend.core.storage.database import SessionLocal


from backend.core.canvas.repository import (
    CanvasRepository
)


from backend.core.canvas.sync import (
    CanvasProductionSync
)



router=APIRouter()



@router.post("/node")
def create_node(
    body:dict
):


    db=SessionLocal()


    repo=CanvasRepository(
        db
    )


    node_id=repo.create_node(

        body["project_id"],

        body["node_type"],

        body["title"],

        body.get(
            "ref_id",
            ""
        ),

        body.get(
            "position"
        ),

        body.get(
            "data"
        )

    )


    db.close()


    return {

        "node_id":
        node_id

    }





@router.get("/{project_id}")
def get_canvas(
    project_id:str
):


    db=SessionLocal()


    from backend.core.storage.canvas_models import CanvasNodeRecord


    nodes=(

        db.query(
            CanvasNodeRecord
        )

        .filter_by(
            project_id=project_id
        )

        .all()

    )


    db.close()


    return [

        {

        "id":n.id,

        "type":n.node_type,

        "title":n.title,

        "ref_id":n.ref_id

        }

        for n in nodes

    ]





@router.post("/sync/{project_id}")
def sync(
    project_id:str
):


    db=SessionLocal()


    result=CanvasProductionSync(
        db
    ).sync_shots(
        project_id
    )


    db.close()


    return {

        "created":
        result

    }
