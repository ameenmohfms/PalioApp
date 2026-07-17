"""Case Review job (A8): weekly, post-intake, and after any L2 event.

Builds the case file from structured data, runs the four-lens review,
upserts the support plan, and raises operator flags into the audit ledger.
Writes for the system and operator — never to the user (only user_summary
is user-visible, rendered on the Plan screen)."""

import json
import re
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from palio.audit.events import record_audit
from palio.db.models import (
    Message,
    MessageRole,
    Pattern,
    PatternStatus,
    SafetyEvent,
    ScreenerInstrument,
    ScreenerResult,
    StrategyLog,
    SupportPlan,
    User,
)
from palio.llm import gateway, prompts
from palio.safety import dependency

log = structlog.get_logger()

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _case_file(db: Session, user: User) -> str:
    patterns = db.execute(
        select(Pattern)
        .where(Pattern.user_id == user.id, Pattern.status == PatternStatus.confirmed)
        .order_by(Pattern.created_at.desc())
        .limit(20)
    ).scalars()
    pattern_lines = [f"- [{p.type.value}] {p.text}" for p in patterns]

    screeners = db.execute(
        select(ScreenerResult, ScreenerInstrument.key)
        .join(ScreenerInstrument, ScreenerResult.instrument_id == ScreenerInstrument.id)
        .where(ScreenerResult.user_id == user.id, ScreenerResult.taken_at.isnot(None))
        .order_by(ScreenerResult.taken_at)
    ).all()
    screener_lines = [
        f"- {key}: {res.scores} band={res.band} on {res.taken_at.date().isoformat()}"
        for res, key in screeners
    ]

    strategies = db.execute(
        select(StrategyLog).where(StrategyLog.user_id == user.id).order_by(StrategyLog.created_at)
    ).scalars()
    strategy_lines = [
        f"- {s.strategy_key}: status={s.status.value}"
        + (f" feedback={s.feedback.value}" if s.feedback else "")
        + (f" outcome={s.outcome}" if s.outcome else "")
        for s in strategies
    ]

    since = datetime.now(UTC) - timedelta(days=30)
    events = db.execute(
        select(SafetyEvent.event_type, SafetyEvent.risk_level, func.count())
        .where(SafetyEvent.subject_id == user.id, SafetyEvent.created_at >= since)
        .group_by(SafetyEvent.event_type, SafetyEvent.risk_level)
    ).all()
    event_lines = [
        f"- {etype} (level={level.value if level else '-'}) x{count}"
        for etype, level, count in events
    ]

    week_count = db.execute(
        select(func.count(Message.id)).where(
            Message.user_id == user.id,
            Message.role == MessageRole.user,
            Message.created_at >= datetime.now(UTC) - timedelta(days=7),
        )
    ).scalar_one()
    spike = dependency.usage_spike(db, user.id)

    sections = [
        "## Confirmed patterns\n" + ("\n".join(pattern_lines) or "none"),
        "## Screener history (cadence: ASRS 56d, PHQ-9/GAD-7 14d)\n"
        + ("\n".join(screener_lines) or "none"),
        "## Strategies\n" + ("\n".join(strategy_lines) or "none"),
        "## Safety events, last 30 days (metadata only)\n" + ("\n".join(event_lines) or "none"),
        f"## Usage\nuser messages last 7d: {week_count}\nusage_spike: {spike}",
    ]
    return "\n\n".join(sections)


def run_for_user(db: Session, user_id: uuid.UUID, trigger: str) -> dict | None:
    user = db.get(User, user_id)
    if user is None:
        log.warning("case_review_missing_user", user_id=str(user_id))
        return None

    result = gateway.complete(
        "case_review",
        system=prompts.load("case_review"),
        messages=[{"role": "user", "content": f"trigger: {trigger}\n\n{_case_file(db, user)}"}],
        max_tokens=1200,
        temperature=0.0,
        user_id=user.id,
        enforce_budget=False,
    )
    match = _JSON_RE.search(result.text)
    if not match:
        raise ValueError(f"case review produced no JSON: {result.text[:200]!r}")
    payload = json.loads(match.group(0))

    plan = {
        "lenses": payload.get("lenses", {}),
        "hypothesis": str(payload.get("hypothesis", ""))[:500],
        "next_focus": str(payload.get("next_focus", ""))[:500],
        "user_summary": str(payload.get("user_summary", ""))[:500],
        "next_checkin_days": int(payload.get("next_checkin_days", 7) or 7),
        "trigger": trigger,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }

    for row in db.execute(
        select(SupportPlan).where(SupportPlan.user_id == user.id, SupportPlan.active)
    ).scalars():
        row.active = False
    db.add(SupportPlan(user_id=user.id, plan=plan, active=True))
    db.flush()

    flags = [str(f)[:300] for f in payload.get("operator_flags", []) if str(f).strip()]
    if flags:
        record_audit(
            actor="system",
            action="case_review_flags",
            subject_id=user.id,
            detail={"flags": flags, "trigger": trigger},
        )
    log.info("case_review_done", user_id=str(user.id), trigger=trigger, flags=len(flags))
    return plan


def handle_job(session: Session, job) -> None:
    """Worker entry point (kind: case_review)."""
    run_for_user(session, uuid.UUID(job.payload["user_id"]), job.payload.get("trigger", "manual"))
