"""Account data rights (spec §14): full JSON export and hard delete."""

from fastapi import APIRouter
from sqlalchemy import select

from palio.audit.events import record_audit
from palio.auth.deps import DbDep, UserDep
from palio.db.models import (
    ChatSession,
    Consent,
    Message,
    Pattern,
    Report,
    ScreenerInstrument,
    ScreenerResult,
    StrategyLog,
    SupportPlan,
)

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/export")
def export(user: UserDep, db: DbDep) -> dict:
    """Full export of everything Palio holds about this user (§14)."""

    def rows(model, order):
        return db.execute(
            select(model).where(model.user_id == user.id).order_by(order)
        ).scalars()

    return {
        "profile": {
            "nickname": user.nickname,
            "locale": user.locale.value,
            "city": user.city,
            "is_guest": user.is_guest,
            "created_at": user.created_at.isoformat(),
        },
        "sessions": [
            {
                "id": str(s.id),
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "memory_paused": s.memory_paused,
                "summary": s.summary,
            }
            for s in rows(ChatSession, ChatSession.started_at)
        ],
        "messages": [
            {
                "id": str(m.id),
                "session_id": str(m.session_id),
                "role": m.role.value,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in rows(Message, Message.seq)
        ],
        "patterns": [
            {
                "id": str(p.id),
                "type": p.type.value,
                "text": p.text,
                "status": p.status.value,
                "confidence": p.confidence,
                "created_at": p.created_at.isoformat(),
            }
            for p in rows(Pattern, Pattern.created_at)
        ],
        "screener_results": [
            {
                "id": str(r.id),
                "instrument": _instrument_key(db, r),
                "answers": r.answers,
                "scores": r.scores,
                "band": r.band,
                "taken_at": r.taken_at.isoformat() if r.taken_at else None,
            }
            for r in rows(ScreenerResult, ScreenerResult.created_at)
        ],
        "strategies": [
            {
                "key": s.strategy_key,
                "status": s.status.value,
                "feedback": s.feedback.value if s.feedback else None,
                "outcome": s.outcome,
                "created_at": s.created_at.isoformat(),
            }
            for s in rows(StrategyLog, StrategyLog.created_at)
        ],
        "support_plans": [
            {"plan": sp.plan, "active": sp.active, "created_at": sp.created_at.isoformat()}
            for sp in rows(SupportPlan, SupportPlan.created_at)
        ],
        "reports": [
            {"id": str(r.id), "language": r.language.value, "created_at": r.created_at.isoformat()}
            for r in rows(Report, Report.created_at)
        ],
        "consents": [
            {
                "key": c.consent_key,
                "version": c.version,
                "granted": c.granted,
                "created_at": c.created_at.isoformat(),
            }
            for c in rows(Consent, Consent.created_at)
        ],
    }


def _instrument_key(db, result) -> str:
    inst = db.get(ScreenerInstrument, result.instrument_id)
    return inst.key if inst else "unknown"


@router.delete("")
def delete_account(user: UserDep, db: DbDep) -> dict:
    """Hard delete (§10.9/§14): the user row goes away and every user-owned
    table cascades. Only the append-only ledgers (opaque subject IDs,
    PII-scrubbed) remain, as documented in the README retention section."""
    subject_id = user.id
    record_audit(actor="user", action="account_deleted", subject_id=subject_id)
    db.delete(user)
    db.flush()
    return {"deleted": True}
