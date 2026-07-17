"""Coaching endpoints: the Plan (spec §10.6) and the strategy lifecycle
assign → try → feedback → adapt/drop (spec §12 Phase 4)."""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from palio.auth.deps import DbDep, UserDep
from palio.coaching import library
from palio.db.models import (
    Message,
    StrategyFeedback,
    StrategyLog,
    StrategyStatus,
    SupportPlan,
)

router = APIRouter(prefix="/coaching", tags=["coaching"])


class StrategyOut(BaseModel):
    id: str
    key: str
    status: str
    feedback: str | None
    outcome: str | None
    title: str
    summary: str
    steps: list[str]
    try_this_week: str
    adapt_if: list[str]


class PlanOut(BaseModel):
    strategies: list[StrategyOut]
    library: list[dict]
    plan_summary: str | None


def _to_out(row: StrategyLog, locale: str) -> StrategyOut:
    strategy = library.get(row.strategy_key)
    lang = locale if locale in ("en", "ar") else "en"
    content = strategy[lang] if strategy else {}
    return StrategyOut(
        id=str(row.id),
        key=row.strategy_key,
        status=row.status.value,
        feedback=row.feedback.value if row.feedback else None,
        outcome=row.outcome,
        title=content.get("title", row.strategy_key),
        summary=content.get("summary", ""),
        steps=content.get("steps", []),
        try_this_week=content.get("try_this_week", ""),
        adapt_if=content.get("adapt_if", []),
    )


@router.get("/plan", response_model=PlanOut)
def plan(user: UserDep, db: DbDep) -> PlanOut:
    rows = list(
        db.execute(
            select(StrategyLog)
            .where(StrategyLog.user_id == user.id)
            .order_by(StrategyLog.created_at.desc())
            .limit(20)
        ).scalars()
    )
    active_plan = db.execute(
        select(SupportPlan).where(SupportPlan.user_id == user.id, SupportPlan.active)
    ).scalar_one_or_none()
    # The internal `hypothesis` is NEVER rendered to the user (§7): only the
    # plain-language summary field leaves the server.
    plan_summary = (active_plan.plan or {}).get("user_summary") if active_plan else None
    return PlanOut(
        strategies=[_to_out(r, user.locale.value) for r in rows],
        library=library.index(user.locale.value),
        plan_summary=plan_summary,
    )


class AssignIn(BaseModel):
    strategy_key: str


@router.post("/assign", response_model=StrategyOut)
def assign(body: AssignIn, user: UserDep, db: DbDep) -> StrategyOut:
    if library.get(body.strategy_key) is None:
        raise HTTPException(status_code=404, detail="unknown strategy")
    existing = db.execute(
        select(StrategyLog).where(
            StrategyLog.user_id == user.id,
            StrategyLog.strategy_key == body.strategy_key,
            StrategyLog.status.in_([StrategyStatus.assigned, StrategyStatus.adapted]),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _to_out(existing, user.locale.value)
    row = StrategyLog(user_id=user.id, strategy_key=body.strategy_key)
    db.add(row)
    db.flush()
    return _to_out(row, user.locale.value)


def _own_row(db, user, strategy_id: str) -> StrategyLog:
    try:
        sid = uuid.UUID(strategy_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown strategy") from None
    row = db.execute(
        select(StrategyLog).where(StrategyLog.id == sid, StrategyLog.user_id == user.id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown strategy")
    return row


class FeedbackIn(BaseModel):
    feedback: StrategyFeedback
    outcome: str | None = None


@router.post("/strategies/{strategy_id}/feedback", response_model=StrategyOut)
def feedback(strategy_id: str, body: FeedbackIn, user: UserDep, db: DbDep) -> StrategyOut:
    row = _own_row(db, user, strategy_id)
    row.feedback = body.feedback
    row.outcome = (body.outcome or "")[:2000] or row.outcome
    row.status = StrategyStatus.tried
    db.flush()
    return _to_out(row, user.locale.value)


@router.post("/strategies/{strategy_id}/adapt", response_model=StrategyOut)
def adapt(strategy_id: str, user: UserDep, db: DbDep) -> StrategyOut:
    row = _own_row(db, user, strategy_id)
    row.status = StrategyStatus.adapted
    db.flush()
    return _to_out(row, user.locale.value)


@router.post("/strategies/{strategy_id}/drop", response_model=StrategyOut)
def drop(strategy_id: str, user: UserDep, db: DbDep) -> StrategyOut:
    row = _own_row(db, user, strategy_id)
    row.status = StrategyStatus.dropped
    db.flush()
    return _to_out(row, user.locale.value)


# ── Message reactions (👍 helped / 👎 didn't — spec §10.3) ───────────────────


class ReactionIn(BaseModel):
    feedback: StrategyFeedback


@router.post("/messages/{message_id}/reaction")
def react(message_id: str, body: ReactionIn, user: UserDep, db: DbDep) -> dict:
    try:
        mid = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown message") from None
    msg = db.execute(
        select(Message).where(Message.id == mid, Message.user_id == user.id)
    ).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail="unknown message")
    msg.feedback = body.feedback
    db.flush()
    return {"ok": True}
