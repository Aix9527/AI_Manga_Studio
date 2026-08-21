from dataclasses import dataclass



@dataclass
class DAGValidationResult:

    episodes:int

    shots:int

    nodes:int

    edges:int

    valid:bool



class DAGStressValidator:


    def build(
        self,
        episodes:int=100,
        shots_per_episode:int=10
    ):


        nodes=[]

        edges=[]


        previous=None


        index=0


        for ep in range(
            1,
            episodes+1
        ):

            for shot in range(
                1,
                shots_per_episode+1
            ):

                index+=1


                node_id=f"ep{ep}_shot{shot}"


                nodes.append(
                    node_id
                )


                if previous:

                    edges.append(

                        {
                        "from":previous,
                        "to":node_id
                        }

                    )


                previous=node_id



        return DAGValidationResult(

            episodes=episodes,

            shots=index,

            nodes=len(nodes),

            edges=len(edges),

            valid=(
                len(nodes)==index
                and
                len(edges)==index-1
            )

        ).__dict__
