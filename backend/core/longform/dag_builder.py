from dataclasses import dataclass,field



@dataclass
class DAGNode:

    id:str

    depends:list[str]=field(
        default_factory=list
    )




class LongformDAGBuilder:



    def build(
        self,
        groups
    ):


        nodes=[]


        previous=None


        for group in groups:


            deps=[]


            if previous:

                deps.append(
                    previous
                )


            node=DAGNode(

                id=group.id,

                depends=deps

            )


            nodes.append(
                node
            )


            previous=group.id



        return nodes
