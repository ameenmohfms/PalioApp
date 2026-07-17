"""Worker process: polls the jobs table and dispatches to registered handlers.

Phase 0 ships the loop with no handlers; Pattern Extractor (Phase 5),
Case Review (Phase 7), and report generation (Phase 6) register here.
"""

import signal
import time

import structlog

from palio.db.base import db_session
from palio.jobs import queue

log = structlog.get_logger()

def _pattern_extraction(session, job):
    from palio.patterns import extractor

    extractor.handle_job(session, job)


def _case_review(session, job):
    from palio.agents import case_review

    case_review.handle_job(session, job)


# kind -> callable(session, job).
HANDLERS: dict = {
    "pattern_extraction": _pattern_extraction,
    "case_review": _case_review,
}

POLL_SECONDS = 2.0
_shutdown = False


def _handle_signal(signum, frame):  # noqa: ARG001
    global _shutdown
    _shutdown = True


def _schedule_weekly_case_reviews() -> None:
    """Enqueue a case_review for every user active in the last 14 days (A8:
    weekly cadence). Runs from APScheduler; execution stays in the poll loop."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import distinct, select

    from palio.db.models import Message
    from palio.jobs import queue

    since = datetime.now(UTC) - timedelta(days=14)
    with db_session() as session:
        user_ids = session.execute(
            select(distinct(Message.user_id)).where(Message.created_at >= since)
        ).scalars()
        for user_id in user_ids:
            queue.enqueue(session, "case_review", {"user_id": str(user_id), "trigger": "weekly"})
    log.info("weekly_case_reviews_enqueued")


def _purge_old_jobs() -> None:
    """Retention: done/failed job rows older than 90 days (README policy)."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete

    from palio.db.models import Job, JobStatus

    cutoff = datetime.now(UTC) - timedelta(days=90)
    with db_session() as session:
        session.execute(
            delete(Job).where(
                Job.status.in_([JobStatus.done, JobStatus.failed]), Job.updated_at < cutoff
            )
        )


def run_forever() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_schedule_weekly_case_reviews, "cron", day_of_week="sun", hour=3)
    scheduler.add_job(_purge_old_jobs, "cron", hour=4)
    scheduler.start()

    log.info("palio_worker_started", handlers=sorted(HANDLERS))
    while not _shutdown:
        worked = run_once()
        if not worked:
            time.sleep(POLL_SECONDS)
    scheduler.shutdown(wait=False)
    log.info("palio_worker_stopped")


def run_once() -> bool:
    """Claim and run at most one job. Returns True if a job was processed."""
    with db_session() as session:
        job = queue.claim_next(session, kinds=list(HANDLERS) or None)
        if job is None:
            return False
        handler = HANDLERS.get(job.kind)
        if handler is None:
            queue.fail(session, job, f"no handler registered for kind={job.kind}")
            return True
        try:
            handler(session, job)
            queue.complete(session, job)
        except Exception as exc:  # noqa: BLE001 — worker must survive handler bugs
            log.error("job_failed", job_id=str(job.id), kind=job.kind, error=str(exc))
            queue.fail(session, job, repr(exc))
        return True


if __name__ == "__main__":
    run_forever()
