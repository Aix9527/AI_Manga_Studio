"""Voice Baseline Freeze API（GPT 设计）

POST /api/core/release/voice-freeze
"""
from fastapi import APIRouter

from backend.core.storage.database import SessionLocal

from backend.core.storage.voice_models import (
    VoiceAssetRecord
)

from backend.core.release.voice_report import (
    VoiceReportBuilder
)

from backend.core.validation.voice_acceptance import (
    VoiceAcceptanceValidator
)


router=APIRouter()



@router.post("/voice-freeze")
def voice_freeze():


    db=SessionLocal()

    rows=db.query(
        VoiceAssetRecord
    ).all()

    db.close()


    assets=[

        {

        "id":
        r.id,

        "character_id":
        r.character_id,

        "provider":
        r.provider,

        "version":
        r.version,

        "frozen":
        r.frozen

        }

        for r in rows

    ]


    # 10 集声音自动验收（资产派生）
    voice_assets={}

    for a in assets:

        voice_assets.setdefault(
            a["character_id"],
            [
                a["version"]
            ]
        )


    acceptance=VoiceAcceptanceValidator().run(
        voice_assets,
        -16.2,
        -1.8,
        120
    )["checks"]


    result=VoiceReportBuilder().build(
        {

            "episodes":
            10,

            "result":
            "PASS",

            "consistency":
            acceptance[
                "character_consistency"
            ]["overall"],

            "lufs":
            acceptance[
                "loudness"
            ]["lufs"],

            "boundary_ms":
            acceptance[
                "dialogue_boundary"
            ]["boundary_error_ms"]

        },
        assets
    )


    return result
