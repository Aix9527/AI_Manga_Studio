
"""Job repository implementation."""

import json
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.workflows.domain.job import Job, JobStatus, LeaseRecord
from backend.modules.workflows.infrastructure.models import HeartbeatModel, JobModel, LeaseRecordModel
from backend.shared.errors import NotFoundError


class SqlAlchemyJobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, job: Job) -> None:
        model = JobModel(
            id=job.job_id, job_type=job.job_type, status=str(job.status),
            payload_json=json.dumps(job.payload, ensure_ascii=False),
            priority=job.priority, attempt_count=job.attempt_count,
            max_attempts=job.max_attempts, leased_by=job.leased_by,
            lease_expires_at=job.lease_expires_at,
            result_json=job.result_json, error_json=job.error_json,
            idempotency_key=job.idempotency_key,
            created_at=job.created_at, updated_at=job.updated_at,
            completed_at=job.completed_at, revision=job.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def get(self, job_id: str) -> Job:
        async with self._session_factory() as session:
            result = await session.execute(select(JobModel).where(JobModel.id == job_id))
            m = result.scalar_one_or_none()
            if m is None:
                raise NotFoundError("Job", job_id)
            return self._to_job(m)

    async def list_pending(self, limit: int = 10) -> list[Job]:
        now = datetime.utcnow()
        async with self._session_factory() as session:
            result = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status == "pending",
                    JobModel.attempt_count < JobModel.max_attempts,
                )
                .order_by(JobModel.priority.desc(), JobModel.created_at)
                .limit(limit)
            )
            return [self._to_job(m) for m in result.scalars().all()]

    async def lease_job(self, job_id: str, worker_id: str, lease_duration_seconds: int = 30) -> Job | None:
        async with self._session_factory() as session:
            now = datetime.utcnow()
            result = await session.execute(
                select(JobModel)
                .where(JobModel.id == job_id, JobModel.status == "pending")
                .with_for_update()
            )
            model = result.scalar_one_or_none()
            if model is None:
                await session.rollback()
                return None
            model.status = "leased"
            model.leased_by = worker_id
            model.lease_expires_at = datetime.utcfromtimestamp(now.timestamp() + lease_duration_seconds)
            model.attempt_count += 1
            model.updated_at = now
            await session.commit()
            return self._to_job(model)

    async def complete_job(self, job_id: str, result: dict) -> None:
        async with self._session_factory() as session:
            result_obj = await session.execute(select(JobModel).where(JobModel.id == job_id))
            model = result_obj.scalar_one_or_none()
            if model is None:
                raise NotFoundError("Job", job_id)
            model.status = "completed"
            model.result_json = json.dumps(result, ensure_ascii=False)
            model.completed_at = datetime.utcnow()
            model.updated_at = datetime.utcnow()
            await session.commit()

    async def fail_job(self, job_id: str, error_message: str) -> None:
        async with self._session_factory() as session:
            result = await session.execute(select(JobModel).where(JobModel.id == job_id))
            model = result.scalar_one_or_none()
            if model is None:
                raise NotFoundError("Job", job_id)
            if model.attempt_count >= model.max_attempts:
                model.status = "dead_letter"
            else:
                model.status = "pending"
            model.error_json = json.dumps({"message": error_message}, ensure_ascii=False)
            model.leased_by = None
            model.lease_expires_at = None
            model.updated_at = datetime.utcnow()
            await session.commit()

    async def get_expired_leases(self) -> list[Job]:
        now = datetime.utcnow()
        async with self._session_factory() as session:
            result = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status == "leased",
                    JobModel.lease_expires_at < now,
                )
            )
            return [self._to_job(m) for m in result.scalars().all()]

    async def reset_expired_jobs(self, job_ids: list[str]) -> int:
        now = datetime.utcnow()
        async with self._session_factory() as session:
            result = await session.execute(
                update(JobModel)
                .where(JobModel.id.in_(job_ids), JobModel.status == "leased")
                .values(status="pending", leased_by=None, lease_expires_at=None, updated_at=now)
            )
            await session.commit()
            return result.rowcount

    async def add_lease_record(self, record: LeaseRecord) -> None:
        model = LeaseRecordModel(
            id=record.lease_id, job_id=record.job_id, worker_id=record.worker_id,
            lease_duration_seconds=record.lease_duration_seconds,
            acquired_at=record.acquired_at, expires_at=record.expires_at,
            released_at=record.released_at, status=record.status,
            created_at=record.acquired_at, updated_at=record.acquired_at, revision=1,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def heartbeat(self, worker_id: str) -> None:
        now = datetime.utcnow()
        async with self._session_factory() as session:
            result = await session.execute(
                select(HeartbeatModel).where(HeartbeatModel.worker_id == worker_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                session.add(HeartbeatModel(
                    id=f"hb-{worker_id}", worker_id=worker_id,
                    last_heartbeat_at=now, status="alive",
                    created_at=now, updated_at=now, revision=1,
                ))
            else:
                model.last_heartbeat_at = now
                model.status = "alive"
                model.updated_at = now
            await session.commit()

    async def get_dead_workers(self, timeout_seconds: int = 60) -> list[str]:
        now = datetime.utcnow()
        async with self._session_factory() as session:
            threshold = datetime.utcfromtimestamp(now.timestamp() - timeout_seconds)
            result = await session.execute(
                select(HeartbeatModel)
                .where(
                    HeartbeatModel.status == "alive",
                    HeartbeatModel.last_heartbeat_at < threshold,
                )
            )
            return [m.worker_id for m in result.scalars().all()]

    @staticmethod
    def _to_job(m: JobModel) -> Job:
        return Job(
            job_id=m.id, job_type=m.job_type, status=JobStatus(m.status),
            payload=json.loads(m.payload_json) if m.payload_json else {},
            priority=m.priority, attempt_count=m.attempt_count, max_attempts=m.max_attempts,
            leased_by=m.leased_by, lease_expires_at=m.lease_expires_at,
            result_json=m.result_json, error_json=m.error_json,
            idempotency_key=m.idempotency_key,
            created_at=m.created_at, updated_at=m.updated_at,
            completed_at=m.completed_at, revision=m.revision,
        )
