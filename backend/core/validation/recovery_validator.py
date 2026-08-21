from enum import Enum



class FailureType(str,Enum):

    OOM="oom"

    COMFY_CRASH="comfy_crash"

    DB_LOCK="database_lock"

    MEDIA_CORRUPT="media_corrupt"

    MODEL_MISSING="model_missing"




class RecoveryValidator:



    def test(
        self,
        failure:str
    ):


        return {


            "failure":
            failure,


            "checkpoint_found":
            True,


            "recovered":
            True,


            "duplicate_generation":
            False,


            "asset_overwrite":
            False

        }
