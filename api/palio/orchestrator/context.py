"""Context-pack builder (spec §8).

Per-turn retrieval pack: user profile + CONFIRMED patterns only (Hard Rule
A2 — the query filters on status=confirmed and tests assert nothing else
can enter) + active support plan + last session summary + screener trends.
Hard token cap with composition logging.
"""

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from palio.db.models import (
    ChatSession,
    Pattern,
    PatternStatus,
    ScreenerInstrument,
    ScreenerResult,
    SupportPlan,
    User,
)

log = structlog.get_logger()

# ~4 chars/token EN, ~2.5 AR; 3 is a safe planning constant.
CHARS_PER_TOKEN = 3
TOKEN_CAP = 1200
MAX_PATTERNS = 12


@dataclass
class ContextPack:
    text: str
    composition: dict = field(default_factory=dict)


def _confirmed_patterns(db: Session, user_id: uuid.UUID) -> list[Pattern]:
    """The ONLY pattern query agents ever see: confirmed, nothing else (A2)."""
    return list(
        db.execute(
            select(Pattern)
            .where(Pattern.user_id == user_id, Pattern.status == PatternStatus.confirmed)
            .order_by(Pattern.updated_at.desc())
            .limit(MAX_PATTERNS)
        ).scalars()
    )


def _last_session_summary(db: Session, user_id: uuid.UUID, exclude: uuid.UUID | None) -> str | None:
    stmt = (
        select(ChatSession.summary)
        .where(ChatSession.user_id == user_id, ChatSession.summary.isnot(None))
        .order_by(ChatSession.started_at.desc())
        .limit(1)
    )
    if exclude is not None:
        stmt = stmt.where(ChatSession.id != exclude)
    return db.execute(stmt).scalar_one_or_none()


def _screener_trends(db: Session, user_id: uuid.UUID) -> list[str]:
    rows = db.execute(
        select(ScreenerResult, ScreenerInstrument.key)
        .join(ScreenerInstrument, ScreenerResult.instrument_id == ScreenerInstrument.id)
        .where(ScreenerResult.user_id == user_id, ScreenerResult.taken_at.isnot(None))
        .order_by(ScreenerResult.taken_at.desc())
        .limit(6)
    ).all()
    lines = []
    for result, key in rows:
        score = result.scores.get("total", result.scores.get("part_a_shaded"))
        lines.append(f"{key}: {score} ({result.band}) on {result.taken_at.date().isoformat()}")
    return lines


def build(db: Session, user: User, current_session_id: uuid.UUID | None = None) -> ContextPack:
    sections: list[str] = []
    composition: dict = {}

    patterns = _confirmed_patterns(db, user.id)
    if patterns:
        # Wins and strengths first — progress framing, not a pathology wall (§8).
        ordered = sorted(patterns, key=lambda p: p.type.value not in ("win", "strength"))
        sections.append(
            "## Confirmed patterns (user-approved observations)\n"
            + "\n".join(f"- [{p.type.value}] {p.text}" for p in ordered)
        )
        composition["patterns"] = len(patterns)

    plan_row = db.execute(
        select(SupportPlan).where(SupportPlan.user_id == user.id, SupportPlan.active)
    ).scalar_one_or_none()
    if plan_row and plan_row.plan:
        # `hypothesis` is internal routing context — agents may see it but the
        # base prompt forbids surfacing it as a conclusion (§7).
        focus = plan_row.plan.get("next_focus", "")
        hypothesis = plan_row.plan.get("hypothesis", "")
        plan_lines = [line for line in (f"focus: {focus}" if focus else "",
                                        f"internal_hypothesis (never state to user): {hypothesis}"
                                        if hypothesis else "") if line]
        if plan_lines:
            sections.append("## Support plan\n" + "\n".join(plan_lines))
            composition["plan"] = True

    summary = _last_session_summary(db, user.id, current_session_id)
    if summary:
        sections.append(f"## Last session summary\n{summary}")
        composition["last_summary"] = True

    trends = _screener_trends(db, user.id)
    if trends:
        sections.append("## Screener trends\n" + "\n".join(trends))
        composition["screeners"] = len(trends)

    text = "\n\n".join(sections)
    cap_chars = TOKEN_CAP * CHARS_PER_TOKEN
    if len(text) > cap_chars:
        text = text[:cap_chars]
        composition["truncated"] = True

    composition["approx_tokens"] = len(text) // CHARS_PER_TOKEN
    log.info("context_pack_built", user_id=str(user.id), **composition)
    return ContextPack(text=text, composition=composition)
