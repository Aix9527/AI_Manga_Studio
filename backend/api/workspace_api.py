from fastapi import APIRouter

from backend.core.storage.database import SessionLocal

from backend.core.storage.models import ShotRecord


router=APIRouter()



@router.get("/{project_id}")

def workspace(
    project_id:str
):


    db=SessionLocal()


    shots=(

        db.query(
            ShotRecord
        )
        .all()

    )


    result=[]


    for s in shots:


        result.append(

            {

            "id":s.id,

            "name":s.name,

            "status":s.status

            }

        )


    db.close()


    return {

        "mode":"professional",

        "project_id":
            project_id,

        "shots":
            result

    }
