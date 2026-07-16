"""Postgres-backed job queue (D8). No Redis in v1 (spec §11).

Claiming uses FOR UPDATE SKIP LOCKED + a lease so a crashed worker's jobs
become claimable again after the lease expires. Handlers must be idempotent.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from palio.db.models import Job, JobStatus

LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 3


def enqueue(session: Session, kind: str, payload: dict, run_at: datetime | None = None) -> Job:
    job = Job(kind=kind, payload=payload, run_at=run_at or datetime.now(UTC))
    session.add(job)
    session.flush()
    return job


def claim_next(session: Session, kinds: list[str] | None = None) -> Job | None:
    now = datetime.now(UTC)
    stmt = (
        select(Job)
        .where(
            Job.run_at <= now,
            or_(
                Job.status == JobStatus.pending,
                # Expired lease on a running job => worker died mid-run.
                (Job.status == JobStatus.running) & (Job.lease_until < now),
            ),
            Job.attempts < MAX_ATTEMPTS,
        )
        .order_by(Job.run_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if kinds:
        stmt = stmt.where(Job.kind.in_(kinds))
    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        return None
    job.status = JobStatus.running
    job.lease_until = now + LEASE
    job.attempts += 1
    session.flush()
    return job


def complete(session: Session, job: Job) -> None:
    job.status = JobStatus.done
    job.lease_until = None
    session.flush()


def fail(session: Session, job: Job, error: str) -> None:
    job.status = JobStatus.failed if job.attempts >= MAX_ATTEMPTS else JobStatus.pending
    job.last_error = error[:2000]
    job.lease_until = None
    session.flush()
