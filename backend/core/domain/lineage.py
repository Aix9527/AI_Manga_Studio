from __future__ import annotations

from dataclasses import dataclass

from .ids import create_id



@dataclass
class LineageEdge:

    id:str

    parent_id:str

    child_id:str

    relation:str



def create_edge(
    parent,
    child,
    relation
):

    return LineageEdge(

        id=create_id(
            "edge"
        ),

        parent_id=parent,

        child_id=child,

        relation=relation
    )
