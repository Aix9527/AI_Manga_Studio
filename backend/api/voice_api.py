"""Voice Production OS · API

POST /api/core/voice/generate   文本 → 语音（自动路由 + fallback）
POST /api/core/voice/clone      参考音频 → 角色声音资产
POST /api/core/voice/route      查询路由决策
GET  /api/core/voice/providers  三引擎健康状态
GET  /api/core/voice/assets     角色声音资产清单
POST /api/core/voice/assets     注册声音资产（冻结）
"""
from fastapi import APIRouter

from backend.core.domain.ids import create_id

from backend.core.storage.database import SessionLocal

from backend.core.storage.voice_models import (
    VoiceAssetRecord
)

from backend.core.media.providers.voice_registry import (
    VOICE_PROVIDERS,
    list_providers
)

from backend.core.media.providers.voice_router import (
    VoiceRouter
)

from backend.core.media.providers.voice_schema import (
    VoiceGenerateRequest,
    VoiceCloneRequest
)

from backend.core.runtime.audio.h3_audio_bridge import (
    H3AudioBridge
)

from backend.core.validation.voice_acceptance import (
    VoiceAcceptanceValidator
)


router=APIRouter()

voice_router=VoiceRouter()


def _resolve_provider(
    provider
):


    return VOICE_PROVIDERS.get(
        provider
    )


@router.post("/generate")
def generate(
    body:VoiceGenerateRequest
):


    route=voice_router.resolve(
        "dialogue"
        if not body.provider
        else "dialogue",
        body.character_id
    )


    provider_name=body.provider or route["provider"]

    provider=_resolve_provider(
        provider_name
    )


    if provider is None:

        return {

        "ok":
        False,

        "error":
        f"unknown provider {provider_name}"

        }


    result=provider.generate(
        body
    )


    return {

    "ok":
    result.get(
        "available",
        True
    ),

    "route":
    route,

    "result":
    result

    }


@router.post("/clone")
def clone(
    body:VoiceCloneRequest
):


    provider=_resolve_provider(
        "gpt_sovits"
    )


    result=provider.clone(
        body
    )


    # 登记资产
    db=SessionLocal()

    asset=VoiceAssetRecord(

        id=create_id(
            "voice_asset"
        ),

        character_id=body.character_id,

        provider="gpt_sovits",

        reference_audio=body.reference_audio,

        version="v1"

    )

    db.add(asset)

    db.commit()

    asset_id=asset.id

    db.close()


    return {

    "ok":
    True,

    "result":
    result,

    "asset_record":
    asset_id

    }


@router.post("/route")
def route(
    body:dict
):


    return voice_router.resolve(
        body.get(
            "scene_type",
            "dialogue"
        ),
        body.get(
            "character_id"
        )
    )


@router.post("/bridge")
def bridge(
    body:dict
):
    """
    H3 Audio Reference Bridge：
    角色声音资产 → H3 REF2VA reference prompt 请求
    """


    return H3AudioBridge().build_reference_request(
        body["shot_id"],
        body.get(
            "characters",
            []
        ),
        body.get(
            "assets",
            {}
        ),
        body.get(
            "shot"
        ),
        body.get(
            "profile",
            "production"
        ),
        body.get(
            "orientation",
            "landscape"
        ),
        body.get(
            "params"
        )
    )


@router.post("/acceptance")
def acceptance(
    body:dict
):
    """
    10 集声音自动验收（Phase 5.1）
    """


    return VoiceAcceptanceValidator().run(
        body.get(
            "voice_assets",
            {}
        ),
        body.get(
            "lufs",
            -16.0
        ),
        body.get(
            "true_peak",
            -2.0
        ),
        body.get(
            "boundary_error_ms",
            120
        )
    )


@router.get("/providers")
def providers():


    return list_providers()


@router.get("/assets")
def assets():


    db=SessionLocal()

    rows=db.query(
        VoiceAssetRecord
    ).all()

    db.close()


    return [

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


@router.post("/assets")
def register_asset(
    body:dict
):


    db=SessionLocal()

    asset=VoiceAssetRecord(

        id=create_id(
            "voice_asset"
        ),

        character_id=body["character_id"],

        provider=body.get(
            "provider",
            "gpt_sovits"
        ),

        reference_audio=body.get(
            "reference_audio",
            ""
        ),

        version=body.get(
            "version",
            "v1"
        ),

        frozen=body.get(
            "frozen",
            False
        )

    )

    db.add(asset)

    db.commit()

    asset_id=asset.id

    db.close()


    return {

    "ok":
    True,

    "asset_id":
    asset_id

    }
