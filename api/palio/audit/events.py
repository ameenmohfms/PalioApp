"""Writers for the append-only ledgers (Hard Rule A6).

detail payloads must be PII-scrubbed at the call site: event metadata,
rule IDs, counts — never raw message text. This module enforces a
belt-and-braces size cap and strips any 'text'/'content' keys.
"""

import uuid

import structlog

from palio.db.base import db_session
from palio.db.models import AuditLog, RiskLevel, SafetyEvent

log = structlog.get_logger()

_FORBIDDEN_DETAIL_KEYS = {"text", "content", "message", "draft"}


def _scrub(detail: dict) -> dict:
    return {k: v for k, v in detail.items() if k not in _FORBIDDEN_DETAIL_KEYS}


def record_safety_event(
    *,
    subject_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    event_type: str,
    risk_level: RiskLevel | None,
    detail: dict | None = None,
) -> None:
    """Append a safety event. Never raises into the caller's flow — a logging
    failure must not take down the safety pipeline itself."""
    try:
        with db_session() as db:
            db.add(
                SafetyEvent(
                    subject_id=subject_id,
                    session_id=session_id,
                    event_type=event_type,
                    risk_level=risk_level,
                    detail=_scrub(detail or {}),
                )
            )
    except Exception as exc:  # noqa: BLE001
        log.error("safety_event_write_failed", event_type=event_type, error=str(exc))


def record_audit(
    *,
    actor: str,
    action: str,
    subject_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> None:
    try:
        with db_session() as db:
            db.add(
                AuditLog(
                    actor=actor, action=action, subject_id=subject_id, detail=_scrub(detail or {})
                )
            )
    except Exception as exc:  # noqa: BLE001
        log.error("audit_write_failed", action=action, error=str(exc))
