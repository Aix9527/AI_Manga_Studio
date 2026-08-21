from fastapi import APIRouter



router=APIRouter()



DEFAULT_STAGES=[

"planning",

"storyboard",

"character_lock",

"keyframe",

"video_generation",

"voice",

"editing",

"quality_gate",

"approved",

"frozen"

]



@router.post("/plan")
def create_plan(
    body:dict
):


    return {

        "mode":"one_click",

        "project_id":
            body.get("project_id"),


        "template":
            body.get(
                "template",
                "anime_serial"
            ),


        "stages":
            DEFAULT_STAGES

    }
