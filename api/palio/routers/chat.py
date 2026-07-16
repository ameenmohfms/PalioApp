"""Chat endpoints: sessions + the message turn.

Streaming (PLAN C1): the reply is FULLY generated and Sentinel-approved
server-side first; /messages/stream then delivers the approved text as SSE
chunks so the client renders a streaming feel. Safety never trails the
stream.
"""

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from palio.auth.deps import DbDep, UserDep
from palio.db.models import ChatSession, Message
from palio.orchestrator import turn

router = APIRouter(prefix="/chat", tags=["chat"])

CHUNK_CHARS = 40


class SessionOut(BaseModel):
    id: str
    memory_paused: bool


@router.post("/sessions", response_model=SessionOut)
def create_session(user: UserDep, db: DbDep) -> SessionOut:
    chat = ChatSession(user_id=user.id)
    db.add(chat)
    db.flush()
    return SessionOut(id=str(chat.id), memory_paused=chat.memory_paused)


def _own_session(db, user, session_id: str) -> ChatSession:
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


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class TurnOut(BaseModel):
    reply: str
    risk_level: str
    ui_action: str | None = None
    crisis: dict | None = None


@router.post("/sessions/{session_id}/messages", response_model=TurnOut)
def post_message(session_id: str, body: MessageIn, user: UserDep, db: DbDep) -> TurnOut:
    chat = _own_session(db, user, session_id)
    result = turn.process_turn(db, user=user, chat=chat, text=body.content)
    return TurnOut(
        reply=result.reply,
        risk_level=result.risk_level.value,
        ui_action=result.ui_action,
        crisis=result.crisis,
    )


@router.post("/sessions/{session_id}/messages/stream")
def post_message_stream(session_id: str, body: MessageIn, user: UserDep, db: DbDep):
    chat = _own_session(db, user, session_id)
    result = turn.process_turn(db, user=user, chat=chat, text=body.content)

    def sse():
        meta = {
            "risk_level": result.risk_level.value,
            "ui_action": result.ui_action,
            "crisis": result.crisis,
        }
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
        text = result.reply
        for i in range(0, len(text), CHUNK_CHARS):
            chunk = json.dumps({"delta": text[i : i + CHUNK_CHARS]}, ensure_ascii=False)
            yield f"event: delta\ndata: {chunk}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")


class HistoryItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


@router.get("/sessions/{session_id}/messages")
def history(
    session_id: str,
    user: UserDep,
    db: DbDep,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> list[HistoryItem]:
    chat = _own_session(db, user, session_id)
    rows = (
        db.execute(
            select(Message)
            .where(Message.session_id == chat.id)
            .order_by(Message.seq.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        HistoryItem(
            id=str(m.id),
            role=m.role.value,
            content=m.content,
            created_at=m.created_at.isoformat(),
        )
        for m in reversed(rows)
    ]
