class ProjectService:
    def __init__(self, repository):
        self.repository = repository

    def create(self, command):
        return self.repository.create(command)

    def get(self, project_id, include_archived=False):
        return self.repository.get(project_id, include_archived)

    def list(self, include_archived=False):
        return self.repository.list(include_archived)

    def archive(self, project_id):
        return self.repository.archive(project_id)

    def add_source(self, project_id, command):
        return self.repository.add_source(project_id, command)
