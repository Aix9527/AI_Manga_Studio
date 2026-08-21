from enum import Enum



class QualityGate(str,Enum):


    SCRIPT="script"


    CHARACTER="character"


    KEYFRAME="keyframe"


    VIDEO_TEMPORAL="video_temporal"


    DIRECTOR="director"


    AUDIO="audio"


    EXPORT="export"
