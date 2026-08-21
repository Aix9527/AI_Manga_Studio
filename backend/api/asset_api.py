from fastapi import APIRouter

from backend.core.storage.database import SessionLocal
from backend.core.storage.models import (
    AssetRecord,
    AssetVersionRecord,
    LineageEdgeRecord
)


router=APIRouter()



@router.get("")
def list_assets():

    db=SessionLocal()


    assets=(
        db.query(
            AssetRecord
        )
        .all()
    )


    result=[]


    for a in assets:


        versions=(

            db.query(
                AssetVersionRecord
            )

            .filter_by(
                asset_id=a.id
            )

            .all()

        )


        result.append(

            {
                "id":a.id,

                "name":a.name,

                "relative_path":
                    a.relative_path,

                "versions":[

                    {
                        "path":v.path,
                        "sha256":v.sha256
                    }

                    for v in versions

                ]
            }

        )


    db.close()


    return result


@router.get("/{asset_id}")
def asset_detail(
    asset_id:str
):

    db=SessionLocal()


    asset=(

        db.query(
            AssetRecord
        )

        .filter_by(
            id=asset_id
        )

        .first()

    )


    if not asset:

        db.close()

        return {
            "error":
            "asset not found"
        }



    versions=(

        db.query(
            AssetVersionRecord
        )

        .filter_by(
            asset_id=asset.id
        )

        .all()

    )


    result={

        "asset":{

            "id":asset.id,

            "name":asset.name,

            "type":
                asset.asset_type,

            "relative_path":
                asset.relative_path

        },


        "versions":[

            {

            "id":v.id,

            "path":v.path,

            "sha256":v.sha256

            }

            for v in versions

        ]

    }


    db.close()


    return result





@router.get("/{asset_id}/lineage")
def asset_lineage(
    asset_id:str
):


    db=SessionLocal()



    edges=(

        db.query(
            LineageEdgeRecord
        )

        .filter(

            (
            LineageEdgeRecord.parent_id
            ==
            asset_id
            )

            |

            (
            LineageEdgeRecord.child_id
            ==
            asset_id
            )

        )

        .all()

    )


    result=[

        {

        "parent":
            e.parent_id,

        "child":
            e.child_id,

        "relation":
            e.relation

        }

        for e in edges

    ]


    db.close()


    return {

        "edges":result

    }
