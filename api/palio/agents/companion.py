"""Companion agent (A1): Palio's conversational core."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from palio.db.models import ChatSession, Message, MessageRole, RiskLevel, User
from palio.llm import gateway, prompts

HISTORY_TURNS = 12


def _history(db: Session, chat: ChatSession) -> list[dict]:
    rows = (
        db.execute(
            select(Message)
            .where(Message.session_id == chat.id)
            .order_by(Message.seq.desc())
            .limit(HISTORY_TURNS)
        )
        .scalars()
        .all()
    )
    history = []
    for msg in reversed(rows):
        if msg.role == MessageRole.system:
            continue
        history.append({"role": msg.role.value, "content": msg.content})
    return history


def _state_block(user: User, risk_level: RiskLevel) -> str:
    supportive = risk_level in (RiskLevel.l1, RiskLevel.l2)
    lines = [
        f'user_nickname: "{user.nickname}"',
        f"user_locale: {user.locale.value}",
        f"supportive_mode: {str(supportive).lower()}",
    ]
    if risk_level == RiskLevel.l2:
        lines.append(
            "note: the user showed elevated distress this turn. Acknowledge it directly "
            "and gently mention the help screen with local support lines. Do not push "
            "any tasks or strategies."
        )
    return "## Session state\n" + "\n".join(lines)


def generate(
    db: Session,
    *,
    user: User,
    chat: ChatSession,
    user_text: str,
    risk_level: RiskLevel,
) -> str:
    from palio.orchestrator import context

    pack = context.build(db, user, current_session_id=chat.id)
    system = prompts.composed("companion") + "\n\n" + _state_block(user, risk_level)
    if pack.text:
        system += "\n\n" + pack.text
    messages = _history(db, chat) + [{"role": "user", "content": user_text}]
    result = gateway.complete(
        "companion",
        system=system,
        messages=messages,
        max_tokens=700,
        temperature=0.4,
        user_id=user.id,
    )
    return result.text.strip()


def rewrite(draft: str, violations: list[str], *, user_id: uuid.UUID | None = None) -> str:
    """One safety rewrite attempt, used by sentinel.enforce."""
    instruction = (
        "The draft below violates Palio's hard rules "
        f"({', '.join(sorted({v.split(':')[0] for v in violations}))}). Rewrite it to keep "
        "the same warmth and useful content while removing every violation: no diagnosis "
        "declarations (use 'consistent with X — only a clinician can diagnose' if needed), "
        "no medication advice (redirect to a prescriber), no promises to contact anyone, "
        "no validation of harm. Reply with ONLY the rewritten message in the same language."
        f"\n\n---\n{draft}"
    )
    result = gateway.complete(
        "companion",
        system=prompts.load("_base"),
        messages=[{"role": "user", "content": instruction}],
        max_tokens=700,
        temperature=0.2,
        user_id=user_id,
    )
    return result.text.strip()
