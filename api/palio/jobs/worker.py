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

# kind -> callable(session, job). Populated by later phases.
HANDLERS: dict = {}

POLL_SECONDS = 2.0
_shutdown = False


def _handle_signal(signum, frame):  # noqa: ARG001
    global _shutdown
    _shutdown = True


def run_forever() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info("palio_worker_started", handlers=sorted(HANDLERS))
    while not _shutdown:
        worked = run_once()
        if not worked:
            time.sleep(POLL_SECONDS)
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
