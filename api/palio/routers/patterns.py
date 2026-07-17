"""Patterns map endpoints (spec §8): suggestion queue confirmation, edit,
hard delete, memory pause, and session end (which triggers extraction)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from palio.auth.deps import DbDep, UserDep
from palio.db.models import ChatSession, Pattern, PatternStatus
from palio.jobs import queue

router = APIRouter(prefix="/patterns", tags=["patterns"])


class PatternOut(BaseModel):
    id: str
    type: str
    text: str
    status: str
    confidence: float
    evidence_count: int
    created_at: str


def _to_out(p: Pattern) -> PatternOut:
    return PatternOut(
        id=str(p.id),
        type=p.type.value,
        text=p.text,
        status=p.status.value,
        confidence=p.confidence,
        evidence_count=len(p.evidence_ids or []),
        created_at=p.created_at.isoformat(),
    )


@router.get("")
def list_patterns(user: UserDep, db: DbDep) -> dict:
    rows = list(
        db.execute(
            select(Pattern)
            .where(Pattern.user_id == user.id)
            .order_by(Pattern.created_at.desc())
            .limit(200)
        ).scalars()
    )
    return {
        "proposed": [_to_out(p) for p in rows if p.status == PatternStatus.proposed],
        "confirmed": [_to_out(p) for p in rows if p.status == PatternStatus.confirmed],
    }


def _own_pattern(db, user, pattern_id: str) -> Pattern:
    try:
        pid = uuid.UUID(pattern_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown pattern") from None
    row = db.execute(
        select(Pattern).where(Pattern.id == pid, Pattern.user_id == user.id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown pattern")
    return row


class EditIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.post("/{pattern_id}/confirm", response_model=PatternOut)
def confirm(pattern_id: str, user: UserDep, db: DbDep) -> PatternOut:
    # Only the USER promotes to confirmed — never the extractor (A2/A6 kernel).
    row = _own_pattern(db, user, pattern_id)
    row.status = PatternStatus.confirmed
    db.flush()
    return _to_out(row)


@router.post("/{pattern_id}/reject", response_model=PatternOut)
def reject(pattern_id: str, user: UserDep, db: DbDep) -> PatternOut:
    row = _own_pattern(db, user, pattern_id)
    row.status = PatternStatus.rejected
    db.flush()
    return _to_out(row)


@router.patch("/{pattern_id}", response_model=PatternOut)
def edit(pattern_id: str, body: EditIn, user: UserDep, db: DbDep) -> PatternOut:
    row = _own_pattern(db, user, pattern_id)
    row.text = body.text.strip()
    db.flush()
    return _to_out(row)


@router.delete("/{pattern_id}")
def delete(pattern_id: str, user: UserDep, db: DbDep) -> dict:
    # Hard delete (§8 user controls) — the row is gone, not soft-hidden.
    row = _own_pattern(db, user, pattern_id)
    db.delete(row)
    db.flush()
    return {"deleted": True}


# ── Session-level memory controls ────────────────────────────────────────────

sessions_router = APIRouter(prefix="/chat/sessions", tags=["chat"])


class MemoryIn(BaseModel):
    paused: bool


@sessions_router.patch("/{session_id}/memory")
def set_memory(session_id: str, body: MemoryIn, user: UserDep, db: DbDep) -> dict:
    chat = _own_chat(db, user, session_id)
    chat.memory_paused = body.paused
    db.flush()
    return {"memory_paused": chat.memory_paused}


@sessions_router.post("/{session_id}/end")
def end_session(session_id: str, user: UserDep, db: DbDep) -> dict:
    chat = _own_chat(db, user, session_id)
    if chat.ended_at is None:
        chat.ended_at = datetime.now(UTC)
        db.flush()
        if not chat.memory_paused:
            queue.enqueue(db, "pattern_extraction", {"session_id": str(chat.id)})
    return {"ended": True, "extraction_scheduled": not chat.memory_paused}


def _own_chat(db, user, session_id: str) -> ChatSession:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown session") from None
    chat = db.execute(
        select(ChatSession).where(ChatSession.id == sid, ChatSession.user_id == user.id)
    ).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return chat
