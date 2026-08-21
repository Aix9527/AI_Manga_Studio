from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List


@dataclass
class GraphNode:
    id: str
    node_type: str
    name: str
    metadata: dict


@dataclass
class GraphEdge:
    source: str
    relation: str
    target: str
    metadata: dict



class LongformGraphService:
    """
    长剧知识图谱服务

    支持：

    Character Relationship Graph
        character -> relation -> character

    Location Continuity Graph
        location_state -> transition -> location_state

    Asset Lineage Graph
        derived_asset -> generated_from -> source_asset

    """

    def __init__(self):

        self.nodes: Dict[str, GraphNode] = {}

        self.edges: List[GraphEdge] = []



    def add_node(
        self,
        node_id: str,
        node_type: str,
        name: str,
        metadata: dict | None = None
    ):


        node = GraphNode(

            id=node_id,

            node_type=node_type,

            name=name,

            metadata=metadata or {}

        )


        self.nodes[node_id] = node


        return asdict(node)




    def add_edge(
        self,
        source: str,
        relation: str,
        target: str,
        metadata: dict | None = None
    ):


        edge = GraphEdge(

            source=source,

            relation=relation,

            target=target,

            metadata=metadata or {}

        )


        self.edges.append(edge)


        return asdict(edge)




    def add_character_relation(
        self,
        character_a: str,
        relation: str,
        character_b: str
    ):


        return self.add_edge(

            character_a,

            relation,

            character_b,

            {
                "domain":
                "character_relationship"
            }

        )




    def add_location_transition(
        self,
        location: str,
        from_state: str,
        to_state: str
    ):


        return self.add_edge(

            from_state,

            "location_transition",

            to_state,

            {

                "location":
                location,

                "domain":
                "continuity"

            }

        )




    def add_asset_lineage(
        self,
        source_asset: str,
        derived_asset: str
    ):


        return self.add_edge(

            derived_asset,

            "generated_from",

            source_asset,

            {

                "domain":
                "asset_lineage"

            }

        )




    def search_nodes(
        self,
        node_type: str
    ):


        return [

            asdict(node)

            for node in self.nodes.values()

            if node.node_type == node_type

        ]




    def export(self):


        return {

            "nodes":

            [

                asdict(node)

                for node in self.nodes.values()

            ],


            "edges":

            [

                asdict(edge)

                for edge in self.edges

            ],


            "generated_at":

            datetime.utcnow()
            .isoformat()

        }
