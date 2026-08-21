from fastapi import APIRouter


from backend.core.media.export import (
ExportService
)


from backend.core.media.audio import (
VoiceService
)


from backend.core.media.providers.cosyvoice import (
CosyVoiceProvider
)

from backend.core.media.providers.whisper import (
WhisperProvider
)


from backend.core.media.export_report import (
ExportReportBuilder
)


from backend.core.storage.database import SessionLocal


from backend.core.media.timeline import (
TimelineService
)


from backend.core.storage.media_models import (
    TimelineTrackRecord,
    TimelineClipRecord,
    ExportPackageRecord
)


from backend.core.domain.ids import create_id



router=APIRouter()



@router.get("/tracks")
def tracks():


    db=SessionLocal()


    rows=(
        db.query(
            TimelineTrackRecord
        )
        .all()
    )


    result=[

        {

        "id":t.id,

        "track_type":t.track_type,

        "name":t.name

        }

        for t in rows

    ]


    db.close()


    return result



@router.get("/clips")
def clips():


    db=SessionLocal()


    rows=(
        db.query(
            TimelineClipRecord
        )
        .all()
    )


    result=[

        {

        "id":c.id,

        "track_id":c.track_id,

        "asset_id":c.asset_id,

        "start":c.start,

        "duration":c.duration,

        "media_type":c.media_type

        }

        for c in rows

    ]


    db.close()


    return result



@router.post("/voice/generate")
def voice_generate(
    body:dict
):


    return CosyVoiceProvider().generate(

        body["text"],

        body["voice"],

        body["output"]

    )




@router.post("/subtitle/transcribe")
def subtitle(
    body:dict
):


    return WhisperProvider().transcribe(

        body["audio"]

    )



@router.post("/voice")
def voice(
    body:dict
):


    return VoiceService().synthesize(

        body["text"],

        body["voice"]

    )




@router.post("/export")
def export(
    body:dict
):


    return ExportService().prepare(

        body["project_id"],

        body.get(
            "mode",
            "vertical"
        )

    )




@router.get("/report/{project_id}")
def report(
    project_id:str
):


    db=SessionLocal()


    packages=(

        db.query(
            ExportPackageRecord
        )

        .filter_by(
            project_id=project_id
        )

        .all()

    )


    result={

        "report_id":
        create_id(
            "export_report"
        ),

        "project_id":
        project_id,

        "packages":[

            {

            "id":p.id,

            "format":p.format,

            "resolution":p.resolution,

            "path":p.path,

            "status":p.status

            }

            for p in packages

        ]

    }


    db.close()


    return result
