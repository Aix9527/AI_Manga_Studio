from pathlib import Path

from ..storage.repository import ProjectRepository



class ProjectImporter:


    def __init__(
        self,
        session
    ):

        self.repo=ProjectRepository(
            session
        )


    def import_project(
        self,
        path:Path
    ):


        project=self.repo.get_or_create_project(

            path.name,

            str(path)

        )


        shot=self.repo.create_default_tree(
            project
        )


        return {

            "project":project.id,

            "shot":shot.id

        }
