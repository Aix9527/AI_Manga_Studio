from enum import Enum



class FailureCategory(str,Enum):


    INPUT_ERROR="input_error"


    MODEL_ERROR="model_error"


    VRAM_ERROR="vram_error"


    PROVIDER_ERROR="provider_error"


    QUALITY_ERROR="quality_error"


    SYSTEM_ERROR="system_error"
