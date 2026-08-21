from fastapi import APIRouter

from backend.core.storage.database import SessionLocal
from backend.core.storage.models import ProjectRecord


router = APIRouter()



@router.get("")
def list_projects():

    db = SessionLocal()

    rows = (
        db.query(
            ProjectRecord
        )
        .all()
    )


    result=[]


    for p in rows:

        result.append(
            {
                "id":p.id,
                "name":p.name,
                "content_type":p.content_type,
                "source_path":p.source_path
            }
        )


    db.close()

    return result
