
"""Generation repository implementation."""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.generation.domain.generation import (
    GenerationAttempt, GenerationCandidate, GenerationPlan, GenerationRequest, GenerationStatus,
)
from backend.modules.generation.infrastructure.models import (
    GenerationAttemptModel, GenerationCandidateModel, GenerationPlanModel, GenerationRequestModel,
)
from backend.shared.errors import NotFoundError


class SqlAlchemyGenerationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # --- Requests ---
    async def add_request(self, request: GenerationRequest) -> None:
        model = GenerationRequestModel(
            id=request.request_id, project_id=request.project_id, shot_id=request.shot_id,
            purpose=request.purpose, status=str(request.status),
            compiled_prompt=request.compiled_prompt, parameters_json=request.parameters_json,
            snapshot_hash=request.snapshot_hash,
            created_at=request.created_at, updated_at=request.updated_at, revision=request.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def get_request(self, request_id: str) -> GenerationRequest:
        async with self._session_factory() as session:
            result = await session.execute(select(GenerationRequestModel).where(GenerationRequestModel.id == request_id))
            m = result.scalar_one_or_none()
            if m is None:
                raise NotFoundError("GenerationRequest", request_id)
            return self._to_request(m)

    async def list_requests_by_project(self, project_id: str) -> list[GenerationRequest]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(GenerationRequestModel).where(GenerationRequestModel.project_id == project_id)
                .order_by(GenerationRequestModel.created_at.desc())
            )
            return [self._to_request(m) for m in result.scalars().all()]

    async def update_request_status(self, request_id: str, status: GenerationStatus) -> None:
        async with self._session_factory() as session:
            result = await session.execute(select(GenerationRequestModel).where(GenerationRequestModel.id == request_id))
            model = result.scalar_one_or_none()
            if model is None:
                raise NotFoundError("GenerationRequest", request_id)
            model.status = str(status)
            await session.commit()

    # --- Plans ---
    async def add_plan(self, plan: GenerationPlan) -> None:
        model = GenerationPlanModel(
            id=plan.plan_id, request_id=plan.request_id, provider_id=plan.provider_id,
            compiled_prompt=plan.compiled_prompt, parameters_json=plan.parameters_json,
            snapshot_hash=plan.snapshot_hash,
            created_at=plan.created_at, updated_at=plan.created_at, revision=1,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    # --- Attempts ---
    async def add_attempt(self, attempt: GenerationAttempt) -> None:
        model = GenerationAttemptModel(
            id=attempt.attempt_id, plan_id=attempt.plan_id, request_id=attempt.request_id,
            attempt_number=attempt.attempt_number, provider_id=attempt.provider_id,
            status=attempt.status, remote_task_id=attempt.remote_task_id,
            output_asset_id=attempt.output_asset_id,
            started_at=attempt.started_at, completed_at=attempt.completed_at,
            error_message=attempt.error_message,
            created_at=attempt.created_at, updated_at=attempt.created_at, revision=1,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def get_next_attempt_number(self, request_id: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.max(GenerationAttemptModel.attempt_number))
                .where(GenerationAttemptModel.request_id == request_id)
            )
            max_num = result.scalar() or 0
            return max_num + 1

    async def get_attempt(self, attempt_id: str) -> GenerationAttempt:
        async with self._session_factory() as session:
            result = await session.execute(select(GenerationAttemptModel).where(GenerationAttemptModel.id == attempt_id))
            m = result.scalar_one_or_none()
            if m is None:
                raise NotFoundError("GenerationAttempt", attempt_id)
            return self._to_attempt(m)

    async def update_attempt(self, attempt: GenerationAttempt) -> None:
        async with self._session_factory() as session:
            result = await session.execute(select(GenerationAttemptModel).where(GenerationAttemptModel.id == attempt.attempt_id))
            model = result.scalar_one_or_none()
            if model is None:
                raise NotFoundError("GenerationAttempt", attempt.attempt_id)
            model.status = attempt.status
            model.remote_task_id = attempt.remote_task_id
            model.output_asset_id = attempt.output_asset_id
            model.started_at = attempt.started_at
            model.completed_at = attempt.completed_at
            model.error_message = attempt.error_message
            await session.commit()

    # --- Candidates ---
    async def add_candidate(self, candidate: GenerationCandidate) -> None:
        model = GenerationCandidateModel(
            id=candidate.candidate_id, attempt_id=candidate.attempt_id, request_id=candidate.request_id,
            asset_version_id=candidate.asset_version_id, is_selected=candidate.is_selected,
            review_status=candidate.review_status,
            created_at=candidate.created_at, updated_at=candidate.created_at, revision=1,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    # --- Mappers ---
    @staticmethod
    def _to_request(m: GenerationRequestModel) -> GenerationRequest:
        return GenerationRequest(
            request_id=m.id, project_id=m.project_id, shot_id=m.shot_id,
            purpose=m.purpose, status=GenerationStatus(m.status),
            compiled_prompt=m.compiled_prompt, parameters_json=m.parameters_json,
            snapshot_hash=m.snapshot_hash,
            created_at=m.created_at, updated_at=m.updated_at, revision=m.revision,
        )

    @staticmethod
    def _to_attempt(m: GenerationAttemptModel) -> GenerationAttempt:
        return GenerationAttempt(
            attempt_id=m.id, plan_id=m.plan_id, request_id=m.request_id,
            attempt_number=m.attempt_number, provider_id=m.provider_id,
            status=m.status, remote_task_id=m.remote_task_id,
            output_asset_id=m.output_asset_id,
            started_at=m.started_at, completed_at=m.completed_at,
            error_message=m.error_message, created_at=m.created_at,
        )
