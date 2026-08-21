from dataclasses import dataclass



@dataclass
class ShotGroup:

    id:str

    episode:int

    scene:int

    shots:list[int]

    estimated_minutes:float




class ShotChunker:



    def split_episode(
        self,
        episode:int,
        scenes:list[dict],
        max_shots:int=12
    ):


        groups=[]


        index=1


        for scene in scenes:


            shots=scene.get(
                "shots",
                []
            )


            for i in range(
                0,
                len(shots),
                max_shots
            ):


                chunk=shots[
                    i:i+max_shots
                ]


                groups.append(

                    ShotGroup(

                        id=f"sg_{episode}_{index}",

                        episode=episode,

                        scene=scene["id"],

                        shots=chunk,

                        estimated_minutes=
                        len(chunk)*0.08

                    )

                )


                index+=1


        return groups
