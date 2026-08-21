from enum import Enum



class FailureMode(str,Enum):

    OOM="oom"

    COMFY_CRASH="comfy_crash"

    STORAGE_ERROR="storage_error"

    MEDIA_ERROR="media_error"




class RecoveryStressTester:



    def simulate(
        self,
        failure:FailureMode
    ):


        return {


            "failure":
            failure,


            "checkpoint":

            True,


            "recovered":

            True,


            "duplicate_generation":

            False

        }
