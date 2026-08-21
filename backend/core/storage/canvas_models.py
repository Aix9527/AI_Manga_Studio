from sqlalchemy import (
    Column,
    String,
    Text,
    Integer
)

from ..storage.database import Base



class CanvasNodeRecord(Base):

    __tablename__="canvas_nodes"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    node_type=Column(
        String
    )


    ref_id=Column(
        String
    )


    title=Column(
        String
    )


    position_json=Column(
        Text
    )


    data_json=Column(
        Text
    )



class CanvasEdgeRecord(Base):

    __tablename__="canvas_edges"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    source_id=Column(
        String
    )


    target_id=Column(
        String
    )


    relation=Column(
        String
    )



class CanvasSnapshotRecord(Base):

    __tablename__="canvas_snapshots"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String,
        nullable=False
    )


    name=Column(
        String
    )


    nodes_json=Column(
        Text
    )


    edges_json=Column(
        Text
    )


    created_at=Column(
        String
    )



class CanvasChangeProposalRecord(Base):

    __tablename__="canvas_change_proposals"


    id=Column(
        String,
        primary_key=True
    )


    project_id=Column(
        String
    )


    node_id=Column(
        String
    )


    operation=Column(
        String
    )


    diff_json=Column(
        Text
    )


    status=Column(
        String,
        default="pending"
    )
