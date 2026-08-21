from fastapi import APIRouter


from backend.core.storage.database import SessionLocal


from backend.core.storyboard.repository import (
    StoryboardRepository
)


router=APIRouter()



@router.post("/shot/{shot_id}")
def create_board(
    shot_id:str,
    body:dict
):


    db=SessionLocal()


    repo=StoryboardRepository(
        db
    )


    board_id=repo.create_board(
        shot_id,
        body
    )


    db.close()


    return {

        "board_id":
        board_id

    }




@router.get("/shot/{shot_id}")
def get_board(
    shot_id:str
):


    db=SessionLocal()


    board=StoryboardRepository(
        db
    ).get_board(
        shot_id
    )


    result={

        "id":board.id,

        "shot_size":
        board.shot_size,

        "camera_move":
        board.camera_move,

        "prompt":
        board.prompt_text

    } if board else None


    db.close()


    return result
