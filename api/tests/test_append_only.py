"""A6/D9: safety_events and audit_log must reject UPDATE and DELETE at the DB level."""

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

from palio.db.models import AuditLog, RiskLevel, SafetyEvent

pytestmark = pytest.mark.pg


@pytest.fixture
def safety_event(session):
    event = SafetyEvent(event_type="test_event", risk_level=RiskLevel.l1, detail={"t": 1})
    session.add(event)
    session.flush()
    return event


def test_safety_event_update_rejected(session, safety_event):
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(
            update(SafetyEvent).where(SafetyEvent.id == safety_event.id).values(event_type="x")
        )
    session.rollback()


def test_safety_event_delete_rejected(session, safety_event):
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(delete(SafetyEvent).where(SafetyEvent.id == safety_event.id))
    session.rollback()


def test_audit_log_mutation_rejected(session):
    entry = AuditLog(actor="system", action="test", detail={})
    session.add(entry)
    session.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(delete(AuditLog).where(AuditLog.id == entry.id))
    session.rollback()
