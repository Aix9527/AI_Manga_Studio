from fastapi import APIRouter


from backend.core.storage.database import SessionLocal


from backend.core.creative.proposal import (
    ChangeProposalService
)


from backend.core.creative.version_service import (
    CharacterVersionService
)



router=APIRouter()



@router.post("/proposal")
def create_proposal(
    body:dict
):


    db=SessionLocal()


    service=ChangeProposalService(
        db
    )


    proposal_id=service.create(

        body["project_id"],

        body["target_type"],

        body["target_id"],

        body.get(
            "operation",
            "update"
        ),

        body["diff"]

    )


    db.close()


    return {

        "proposal_id":
        proposal_id,

        "status":
        "pending"

    }





@router.post(
"/proposal/{proposal_id}/approve"
)
def approve(
    proposal_id:str
):


    db=SessionLocal()


    service=ChangeProposalService(
        db
    )


    proposal=service.approve(
        proposal_id
    )



    if not proposal:

        db.close()

        return {
            "error":
            "not found"
        }




    # 当前仅支持 Character Version


    if proposal.target_type=="character":


        version_service=CharacterVersionService(
            db
        )


        version_id=version_service.create_version(

            proposal.target_id,

            {

            "change":
            proposal.diff_json

            }

        )


    else:

        version_id=None



    db.close()


    return {

        "status":
        "approved",

        "version_id":
        version_id

    }
