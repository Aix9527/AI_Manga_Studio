from enum import Enum



class FailureType(str,Enum):


    OOM="oom"


    COMFY_CRASH="comfy_crash"


    MODEL_MISSING="model_missing"


    DISK_FULL="disk_full"


    MEDIA_CORRUPT="media_corrupt"




class FailureInjector:



    def inject(
        self,
        failure_type
    ):


        if failure_type==FailureType.OOM:

            raise MemoryError(
                "Injected GPU OOM"
            )


        if failure_type==FailureType.COMFY_CRASH:

            raise RuntimeError(
                "Injected ComfyUI crash"
            )


        if failure_type==FailureType.MODEL_MISSING:

            raise FileNotFoundError(
                "Injected model missing"
            )


        if failure_type==FailureType.DISK_FULL:

            raise OSError(
                "Injected disk full"
            )


        if failure_type==FailureType.MEDIA_CORRUPT:

            raise ValueError(
                "Injected media corrupt"
            )
