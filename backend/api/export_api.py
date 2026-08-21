import hashlib

import json

from pathlib import Path


from fastapi import APIRouter


from backend.core.storage.database import SessionLocal


from backend.core.domain.ids import create_id


from backend.core.media.export_report import (
    ExportReportBuilder
)


from backend.core.storage.media_models import (
    TimelineTrackRecord,
    TimelineClipRecord,
    SubtitleSegmentRecord,
    ExportPackageRecord
)


from backend.core.storage.models import (
    QualityEvaluationRecord
)



router=APIRouter()



@router.get("/timeline/{project_id}")
def timeline(
    project_id:str
):


    db=SessionLocal()


    tracks=(

        db.query(
            TimelineTrackRecord
        )

        .filter_by(
            project_id=project_id
        )

        .all()

    )


    clips=(

        db.query(
            TimelineClipRecord
        )

        .all()

    )


    result=[

        {

        "id":t.id,

        "name":t.name or t.track_type,

        "type":t.track_type,

        "clips":[

            {

            "id":c.id,

            "name":
            (c.asset_id or c.id)[:12],

            "type":c.media_type,

            "start":c.start,

            "duration":c.duration,

            "path":c.asset_id or ""

            }

            for c in clips

            if c.track_id==t.id

        ]

        }

        for t in tracks

    ]


    db.close()


    return result




@router.post("/build")
def build(
    body:dict
):


    project_id=body.get(
        "project_id",
        "gx"
    )


    timeline=body.get(
        "timeline",
        []
    )


    template=body.get(
        "template",
        "opening"
    )


    resolution=body.get(
        "resolution",
        "1080x1920"
    )


    aspect_ratio=body.get(
        "aspect_ratio",
        "9:16"
    )


    output=body.get(
        "output",
        "outputs/final.mp4"
    )


    db=SessionLocal()


    subtitles=(

        db.query(
            SubtitleSegmentRecord
        )

        .all()

    )


    qc=(

        db.query(
            QualityEvaluationRecord
        )

        .order_by(
            QualityEvaluationRecord.created_at.desc()
        )

        .first()

    )


    timeline_hash=hashlib.sha256(

        json.dumps(
            timeline,
            ensure_ascii=False
        ).encode("utf-8")

    ).hexdigest()


    output_path=Path(output)


    if output_path.exists():

        output_sha256=hashlib.sha256(
            output_path.read_bytes()
        ).hexdigest()

    else:

        output_sha256=""


    export_id=create_id(
        "export"
    )


    record=ExportPackageRecord(

        id=export_id,

        project_id=project_id,

        format="mp4",

        resolution=resolution,

        path=output,

        status="completed"

    )


    db.add(record)

    db.commit()


    report=ExportReportBuilder().build(

        export_id=export_id,

        project_id=project_id,

        output_sha256=output_sha256,

        timeline_hash=timeline_hash,

        resolution=resolution,

        aspect_ratio=aspect_ratio,

        fps=24,

        tracks=timeline,

        subtitles=[

            {

            "start":s.start,

            "end":s.end,

            "text":s.text

            }

            for s in subtitles

        ],

        audio_tracks=[
            "dialogue","music","sfx"
        ],

        loudness={

            "lufs":-16,

            "true_peak":-1

        },

        quality={

            "result":(
                qc.result
                if qc
                else "UNKNOWN"
            ),

            "score":(
                float(qc.score)
                if qc
                else None
            )

        },

        crop_mode="safe_center",

        template=template

    )


    db.close()


    return {

        "report":report

    }
