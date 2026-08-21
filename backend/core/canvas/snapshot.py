from .repository import CanvasRepository



class CanvasSnapshotService:



    def __init__(
        self,
        db
    ):

        self.repo=CanvasRepository(
            db
        )



    def create(
        self,
        project_id
    ):

        return self.repo.snapshot(
            project_id
        )
