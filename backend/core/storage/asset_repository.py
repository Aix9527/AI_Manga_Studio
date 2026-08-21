from __future__ import annotations

from sqlalchemy.orm import Session

from ..domain.ids import create_id

from .models import (
    AssetVersionRecord,
    LineageEdgeRecord
)


class AssetRepository:


    def __init__(
        self,
        db:Session
    ):
        self.db=db



    def create_asset_version(
        self,
        asset_id,
        path,
        sha256
    ):


        exists = (
            self.db
            .query(
                AssetVersionRecord
            )
            .filter_by(
                asset_id=asset_id,
                path=path,
                sha256=sha256
            )
            .first()
        )


        if exists:
            return exists



        obj=AssetVersionRecord(

            id=create_id(
                "assetver"
            ),

            asset_id=asset_id,

            path=path,

            sha256=sha256

        )


        self.db.add(obj)

        self.db.commit()


        return obj




    def create_lineage(
        self,
        parent,
        child,
        relation
    ):


        exists=(
            self.db
            .query(
                LineageEdgeRecord
            )
            .filter_by(
                parent_id=parent,
                child_id=child,
                relation=relation
            )
            .first()
        )


        if exists:

            return exists



        edge=LineageEdgeRecord(

            id=create_id(
                "edge"
            ),

            parent_id=parent,

            child_id=child,

            relation=relation
        )


        self.db.add(edge)

        self.db.commit()


        return edge
