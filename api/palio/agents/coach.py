"""Skills Coach agent (A5). Teaches only from /content/strategies."""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from palio.coaching import library
from palio.db.models import ChatSession, RiskLevel, StrategyLog, StrategyStatus, User
from palio.llm import gateway, prompts


def _active_strategies(db: Session, user: User) -> list[StrategyLog]:
    return list(
        db.execute(
            select(StrategyLog)
            .where(
                StrategyLog.user_id == user.id,
                StrategyLog.status.in_([StrategyStatus.assigned, StrategyStatus.adapted]),
            )
            .order_by(StrategyLog.created_at.desc())
            .limit(3)
        ).scalars()
    )


def _context_block(db: Session, user: User) -> str:
    locale = user.locale.value
    lines = ["## Strategy library (the ONLY strategies you may teach)"]
    for entry in library.index(locale):
        lines.append(
            f"- {entry['key']} [{entry['category']}]: {entry['title']} — {entry['summary']}"
        )

    active = _active_strategies(db, user)
    if active:
        lines.append("\n## User's active strategies")
        for log_row in active:
            strategy = library.get(log_row.strategy_key)
            title = strategy[locale]["title"] if strategy else log_row.strategy_key
            lines.append(f"- {log_row.strategy_key} ({log_row.status.value}): {title}")
            if strategy:
                lines.append(f"  full: {json.dumps(strategy[locale], ensure_ascii=False)}")
    return "\n".join(lines)


def generate(
    db: Session,
    *,
    user: User,
    chat: ChatSession,
    user_text: str,
    risk_level: RiskLevel,
    dependency_note: bool = False,
) -> str:
    from palio.agents.companion import _history, _state_block  # shared helpers
    from palio.orchestrator import context

    pack = context.build(db, user, current_session_id=chat.id)
    system = (
        prompts.composed("coach")
        + "\n\n"
        + _state_block(user, risk_level, dependency_note)
        + "\n\n"
        + _context_block(db, user)
    )
    if pack.text:
        system += "\n\n" + pack.text
    messages = _history(db, chat) + [{"role": "user", "content": user_text}]
    result = gateway.complete(
        "coach",
        system=system,
        messages=messages,
        max_tokens=700,
        temperature=0.4,
        user_id=user.id,
    )
    return result.text.strip()


def rewrite(draft: str, violations: list[str], *, user_id: uuid.UUID | None = None) -> str:
    from palio.agents import companion

    return companion.rewrite(draft, violations, user_id=user_id)
