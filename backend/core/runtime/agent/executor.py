import json


from ...domain.ids import create_id


from ...storage.runtime_models import (
    AgentRunRecord,
    FailureRecord
)



from .failure import FailureCategory



class AgentExecutor:



    def __init__(
        self,
        db
    ):

        self.db=db




    def execute(
        self,
        skill_id,
        task_id,
        input_data,
        runtime_result
    ):


        run=AgentRunRecord(

            id=create_id(
                "agent_run"
            ),

            skill_id=skill_id,

            task_id=task_id,

            input_json=json.dumps(
                input_data,
                ensure_ascii=False
            ),

            output_json=json.dumps(
                runtime_result,
                ensure_ascii=False
            ),

            model_id=
            runtime_result.get(
                "model",
                ""
            ),

            workflow_id=
            runtime_result.get(
                "workflow",
                ""
            ),

            status="completed"

        )


        self.db.add(run)

        self.db.commit()


        return run.id




    def fail(
        self,
        run_id,
        category,
        message
    ):


        item=FailureRecord(

            id=create_id(
                "failure"
            ),

            run_id=run_id,

            category=category,

            message=message

        )


        self.db.add(item)

        self.db.commit()
