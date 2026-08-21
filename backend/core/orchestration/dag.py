from dataclasses import dataclass,field


from typing import List



@dataclass
class ProductionNode:


    id:str


    stage:int


    depends:List[str]=field(
        default_factory=list
    )




class ProductionDAG:



    def __init__(self):

        self.nodes={}



    def add(
        self,
        node:ProductionNode
    ):

        self.nodes[node.id]=node



    def ready(
        self,
        completed
    ):


        result=[]


        for node in self.nodes.values():


            if node.id in completed:

                continue


            if all(

                x in completed

                for x in node.depends

            ):

                result.append(node)


        return result
