from ..domain.ids import create_id



class SeasonScheduler:



    def build_plan(
        self,
        episodes,
        shots_per_episode
    ):


        result=[]


        for ep in range(
            1,
            episodes+1
        ):


            result.append({

                "episode":
                ep,


                "shots":
                shots_per_episode,


                "priority":
                2,


                "status":
                "planned"

            })


        return result
