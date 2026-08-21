from fastapi import APIRouter


from backend.core.longform.graph_service import (
    LongformGraphService
)


from backend.core.longform.twin_service import (
    ProductionTwinService
)


from backend.core.longform.cost_predictor import (
    DynamicCostPredictor
)


router = APIRouter()



graph_service = LongformGraphService()



@router.post(
    "/graph/node"
)
def create_node(
    body:dict
):


    return graph_service.add_node(

        body["id"],

        body["type"],

        body["name"],

        body.get(
            "metadata",
            {}
        )

    )




@router.post(
    "/graph/relation"
)
def create_relation(
    body:dict
):


    relation_type = body.get(
        "domain"
    )



    if relation_type == "character":

        return graph_service.add_character_relation(

            body["source"],

            body["relation"],

            body["target"]

        )



    if relation_type == "location":

        return graph_service.add_location_transition(

            body["location"],

            body["source"],

            body["target"]

        )



    if relation_type == "asset":

        return graph_service.add_asset_lineage(

            body["source"],

            body["target"]

        )



    return graph_service.add_edge(

        body["source"],

        body["relation"],

        body["target"]

    )





@router.get(
    "/graph"
)
def graph():

    return graph_service.export()





@router.post(
    "/twin/dashboard"
)
def twin_dashboard(
    body:dict
):


    return ProductionTwinService().snapshot(

        body["project_id"],

        body.get(
            "episodes",
            []
        ),

        body.get(
            "tasks",
            []
        ),

        body.get(
            "gpu",
            {}
        ),

        body.get(
            "storage",
            {}
        ),

        body.get(
            "quality",
            {}
        )

    )





@router.post(
    "/cost/predict"
)
def forecast(
    body:dict
):


    return DynamicCostPredictor().predict(

        body["episodes"],

        body["shots_per_episode"],

        body.get(
            "retry_rate",
            0.1
        ),

        body.get(
            "gpu_hour_price",
            0
        )

    )





@router.post(
    "/season/simulate"
)
def simulate(
    body:dict
):


    episodes = body.get(
        "episodes",
        100
    )


    shots = body.get(
        "shots_per_episode",
        12
    )


    schedule=[]


    for ep in range(
        1,
        episodes + 1
    ):

        schedule.append(

            {

            "episode":
            ep,


            "shots":
            shots,


            "status":
            "planned"

            }

        )


    return {

        "episodes":
        episodes,


        "total_shots":

        episodes * shots,


        "schedule":

        schedule

    }
