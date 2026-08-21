class RecoveryManager:



    def restore(
        self,
        checkpoint
    ):


        if not checkpoint:

            return {

            "stage":0,

            "state":{}

            }



        import json


        return {

        "stage":
        checkpoint.stage,


        "state":
        json.loads(
            checkpoint.state_json
        )

        }
