from fastapi import APIRouter

from backend.core.storage.database import SessionLocal

from backend.core.creative.repository import CreativeRepository



router=APIRouter()



@router.post("/world")
def create_world(
    body:dict
):


    db=SessionLocal()


    repo=CreativeRepository(db)


    world=repo.create_world(

        body["project_id"],

        body.get(
            "title",
            ""
        ),

        body.get(
            "description",
            ""
        )

    )


    world_id=world.id

    db.close()


    return {

        "id":world_id

    }





@router.post("/character")
def create_character(
    body:dict
):


    db=SessionLocal()


    repo=CreativeRepository(db)


    c=repo.create_character(

        body["project_id"],

        body["name"],

        body.get(
            "identity",
            ""
        )

    )


    char_id=c.id

    db.close()


    return {

        "id":char_id

    }
