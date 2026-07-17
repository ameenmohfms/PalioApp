"""Operator metrics (spec §3): validated-scale trends, screener completion,
report exports, referral taps, graduation-adjacent signals. Deliberately
NOT session length or DAU — we never optimize engagement for its own sake.

Guarded by OPERATOR_TOKEN; refuses entirely when unset."""

import hmac
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import func, select

from palio.auth.deps import DbDep
from palio.config import get_settings
from palio.db.models import (
    AuditLog,
    Pattern,
    PatternStatus,
    ScreenerResult,
    StrategyFeedback,
    StrategyLog,
    User,
)

router = APIRouter(prefix="/operator", tags=["operator"])


def _authorize(token: str | None) -> None:
    expected = get_settings().operator_token
    if not expected:
        raise HTTPException(status_code=404, detail="not found")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/metrics")
def metrics(
    db: DbDep,
    x_operator_token: Annotated[str | None, Header()] = None,
) -> dict:
    _authorize(x_operator_token)
    month_ago = datetime.now(UTC) - timedelta(days=30)

    started = db.execute(select(func.count(ScreenerResult.id))).scalar_one()
    completed = db.execute(
        select(func.count(ScreenerResult.id)).where(ScreenerResult.taken_at.isnot(None))
    ).scalar_one()

    def audit_count(action: str) -> int:
        return db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == action, AuditLog.created_at >= month_ago
            )
        ).scalar_one()

    strategies_helped = db.execute(
        select(func.count(StrategyLog.id)).where(
            StrategyLog.feedback.in_([StrategyFeedback.helped, StrategyFeedback.partial])
        )
    ).scalar_one()
    strategies_rated = db.execute(
        select(func.count(StrategyLog.id)).where(StrategyLog.feedback.isnot(None))
    ).scalar_one()

    return {
        "users_total": db.execute(select(func.count(User.id))).scalar_one(),
        "screeners": {
            "started": started,
            "completed": completed,
            "completion_rate": round(completed / started, 3) if started else None,
        },
        "reports_exported_30d": audit_count("report_exported"),
        "referral_taps_30d": audit_count("referral_tapped"),
        "accounts_deleted_30d": audit_count("account_deleted"),
        "strategies": {
            "rated": strategies_rated,
            "helped_or_partial": strategies_helped,
        },
        "patterns_confirmed": db.execute(
            select(func.count(Pattern.id)).where(Pattern.status == PatternStatus.confirmed)
        ).scalar_one(),
        "case_review_flags_30d": audit_count("case_review_flags"),
    }
