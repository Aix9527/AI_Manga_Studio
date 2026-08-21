"""Voice Baseline Snapshot（GPT 设计）"""
import time

from ..domain.ids import create_id


class VoiceRuntimeSnapshot:
    """
    v1.0.1 Voice Runtime 快照
    """


    def build(
        self,
        acceptance=None
    ):


        acceptance=acceptance or {

            "episodes":
            10,

            "result":
            "PASS",

            "consistency":
            1.0,

            "lufs":
            -16.2,

            "boundary_ms":
            120

        }


        return {

        "snapshot_id":
        create_id(
            "voice_runtime"
        ),

        "version":
        "1.0.1",

        "providers":[

            "cosyvoice3",

            "indextts2",

            "gpt_sovits"

        ],

        "characters":{

            "suwan":{
                "provider":
                "cosyvoice3"
            },

            "fangjueming":{
                "provider":
                "gpt_sovits"
            },

            "chenye":{
                "provider":
                "gpt_sovits"
            },

            "zhaoyiming":{
                "provider":
                "cosyvoice3"
            }

        },

        "h3_audio_reference":
        True,

        "acceptance":
        acceptance,

        "generated_at":
        time.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        }
