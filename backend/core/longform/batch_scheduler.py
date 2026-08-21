from .shot_chunker import ShotChunker

from .priority_queue import LongformQueue

from .dag_builder import LongformDAGBuilder



class SceneBatchScheduler:



    def __init__(self):

        self.chunker=ShotChunker()

        self.queue=LongformQueue()

        self.dag=LongformDAGBuilder()




    def schedule_episode(
        self,
        episode,
        scenes
    ):


        groups=self.chunker.split_episode(

            episode,

            scenes

        )


        tasks=[

            self.queue.create_task(
                g
            )

            for g in groups

        ]


        dag=self.dag.build(
            groups
        )


        return {


            "episode":
            episode,


            "groups":

            [

            g.__dict__

            for g in groups

            ],


            "tasks":
            tasks,


            "dag":

            [

            {

            "id":n.id,

            "depends":n.depends

            }

            for n in dag

            ]

        }
