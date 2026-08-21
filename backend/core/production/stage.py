from enum import IntEnum


class ProductionStage(IntEnum):

    DRAFT = 0

    PLANNING = 1

    STORYBOARD = 2

    CHARACTER_LOCK = 3

    KEYFRAME = 4

    VIDEO_GENERATION = 5

    VOICE = 6

    EDITING = 7

    QUALITY_GATE = 8

    APPROVED = 9

    FROZEN = 10



STAGE_NAMES = {

    0:"draft",

    1:"planning",

    2:"storyboard",

    3:"character_lock",

    4:"keyframe",

    5:"video_generation",

    6:"voice",

    7:"editing",

    8:"quality_gate",

    9:"approved",

    10:"frozen"

}
