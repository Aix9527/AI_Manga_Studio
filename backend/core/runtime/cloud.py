from ..domain.ids import create_id

from ..storage.runtime_models import (
    CloudAuthorizationRecord
)



class CloudGuard:



    def __init__(
        self,
        db
    ):

        self.db=db



    def authorize(
        self,
        task_id,
        provider,
        scope
    ):


        obj=CloudAuthorizationRecord(

            id=create_id(
                "cloud_auth"
            ),

            task_id=task_id,

            provider=provider,

            scope_json=str(scope),

            approved=1

        )


        self.db.add(obj)

        self.db.commit()


        return obj.id



    def allowed(
        self,
        task_id
    ):


        return (

            self.db.query(
                CloudAuthorizationRecord
            )

            .filter_by(
                task_id=task_id,
                approved=1
            )

            .first()

            is not None

        )
