
"""Generation module public API."""

from dataclasses import dataclass

from backend.modules.generation.domain.generation import GenerationRequest, GenerationStatus
from backend.modules.generation.infrastructure.provider_registry import InMemoryProviderRegistry
from backend.modules.generation.infrastructure.repository import SqlAlchemyGenerationRepository
from backend.modules.workflows.infrastructure.repository import SqlAlchemyJobRepository
from backend.shared.ids import IdGenerator
from backend.shared.time import Clock


@dataclass(slots=True)
class GenerationModuleApi:
    generation_repo: SqlAlchemyGenerationRepository
    job_repo: SqlAlchemyJobRepository
    provider_registry: InMemoryProviderRegistry
    id_generator: IdGenerator
    clock: Clock

    @property
    def _generation_repo(self) -> SqlAlchemyGenerationRepository:
        return self.generation_repo

    async def submit(
        self,
        project_id: str,
        shot_id: str,
        purpose: str,
        prompt: str,
        parameters: dict,
    ) -> GenerationRequest:
        now = self.clock.now()
        gen_req = GenerationRequest(
            request_id=self.id_generator.new("genreq"),
            project_id=project_id,
            shot_id=shot_id,
            purpose=purpose,
            status=GenerationStatus.PENDING,
            compiled_prompt=prompt,
            created_at=now,
            updated_at=now,
        )
        await self.generation_repo.add_request(gen_req)

        # Create a job to execute generation asynchronously
        from backend.modules.workflows.domain.job import Job, JobStatus
        import json

        job = Job(
            job_id=self.id_generator.new("job"),
            job_type="image_generation",
            status=JobStatus.PENDING,
            payload={
                "request_id": gen_req.request_id,
                "purpose": purpose,
                "prompt": prompt,
                "parameters": parameters,
            },
            priority=0,
            attempt_count=0,
            max_attempts=3,
            leased_by=None,
            lease_expires_at=None,
            idempotency_key=gen_req.request_id,
            revision=1,
        )
        await self.job_repo.add(job)
        return gen_req
