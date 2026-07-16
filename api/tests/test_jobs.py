"""Postgres-backed job queue behavior (D8)."""

from datetime import UTC, datetime, timedelta

import pytest

from palio.db.models import JobStatus
from palio.jobs import queue

pytestmark = pytest.mark.pg

KIND = "test_kind"


@pytest.fixture(autouse=True)
def _clean_jobs(session):
    yield
    from sqlalchemy import delete

    from palio.db.models import Job

    session.execute(delete(Job).where(Job.kind == KIND))
    session.flush()


def test_enqueue_claim_complete(session):
    job = queue.enqueue(session, KIND, {"x": 1})
    claimed = queue.claim_next(session, kinds=[KIND])
    assert claimed is not None and claimed.id == job.id
    assert claimed.status == JobStatus.running
    assert claimed.attempts == 1

    queue.complete(session, claimed)
    assert claimed.status == JobStatus.done
    assert queue.claim_next(session, kinds=[KIND]) is None


def test_future_job_not_claimable(session):
    queue.enqueue(session, KIND, {}, run_at=datetime.now(UTC) + timedelta(hours=1))
    assert queue.claim_next(session, kinds=[KIND]) is None


def test_expired_lease_reclaimable(session):
    job = queue.enqueue(session, KIND, {})
    claimed = queue.claim_next(session, kinds=[KIND])
    assert claimed.id == job.id
    # Simulate a worker crash: lease expired while still 'running'.
    claimed.lease_until = datetime.now(UTC) - timedelta(minutes=1)
    session.flush()

    reclaimed = queue.claim_next(session, kinds=[KIND])
    assert reclaimed is not None and reclaimed.id == job.id
    assert reclaimed.attempts == 2


def test_fail_exhausts_attempts(session):
    job = queue.enqueue(session, KIND, {})
    for expected_attempt in (1, 2, 3):
        claimed = queue.claim_next(session, kinds=[KIND])
        assert claimed is not None and claimed.attempts == expected_attempt
        queue.fail(session, claimed, "boom")
    assert job.status == JobStatus.failed
    assert queue.claim_next(session, kinds=[KIND]) is None
