from .models import Task

from .event_bus import event_bus



class TaskQueue:


    def __init__(self):

        self.tasks=[]



    def create(
        self,
        **kwargs
    ):

        task=Task(
            **kwargs
        )

        self.tasks.append(
            task
        )


        event_bus.publish(

            "task.created",

            task.__dict__

        )


        return task



    def list(self):

        return self.tasks



    def control(
        self,
        task_id,
        action
    ):


        for task in self.tasks:


            if task.id != task_id:

                continue



            if action=="pause":

                task.status="paused"



            elif action=="resume":

                task.status="running"



            elif action=="cancel":

                task.status="cancelled"



            elif action=="retry":

                task.status="queued"

                task.retry_count += 1



            event_bus.publish(

                "task.updated",

                task.__dict__

            )


            return task



        return None



task_queue=TaskQueue()
