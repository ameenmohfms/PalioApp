"""Phase 7: Case Review on seeded fixtures, dependency wiring, metrics."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from palio.agents import case_review
from palio.db.models import (
    Locale,
    Pattern,
    PatternStatus,
    PatternType,
    StrategyFeedback,
    StrategyLog,
    StrategyStatus,
    SupportPlan,
)
from palio.llm import gateway
from palio.main import app

pytestmark = pytest.mark.pg

REVIEW_PAYLOAD = {
    "lenses": {
        "safety_trajectory": "one L2 event, PHQ-9 stable at mild; no escalation trend",
        "assessment_gaps": "GAD-7 never taken; ASRS current",
        "coaching_efficacy": "task_breakdown helped; retire time_blocking",
        "engagement_health": "usage steady; no exclusivity language",
    },
    "hypothesis": "probable inattentive-type presentation",
    "next_focus": "morning starts before deadlines",
    "user_summary": "التركيز الحالي: تسهيل بدايات الصباح خطوة صغيرة كل يوم.",
    "next_checkin_days": 7,
    "operator_flags": ["GAD-7 missing after anxiety mentions — surface screening offer"],
}


@pytest.fixture
def seeded_user(session, make_user):
    user = make_user(locale=Locale.ar)
    session.add_all(
        [
            Pattern(
                user_id=user.id,
                type=PatternType.trigger,
                text="الصباحات قبل المواعيد النهائية",
                status=PatternStatus.confirmed,
            ),
            StrategyLog(
                user_id=user.id,
                strategy_key="task_breakdown",
                status=StrategyStatus.tried,
                feedback=StrategyFeedback.helped,
            ),
            SupportPlan(user_id=user.id, plan={"user_summary": "قديم"}, active=True),
        ]
    )
    session.flush()
    return user


@pytest.fixture(autouse=True)
def _fake_review():
    gateway.fake_registry.install(
        "case_review", lambda s, m: json.dumps(REVIEW_PAYLOAD, ensure_ascii=False)
    )
    yield
    gateway.fake_registry.clear()


def test_case_review_produces_valid_plan_update(session, seeded_user):
    plan = case_review.run_for_user(session, seeded_user.id, trigger="weekly")
    assert plan is not None
    assert set(plan["lenses"]) == {
        "safety_trajectory",
        "assessment_gaps",
        "coaching_efficacy",
        "engagement_health",
    }

    rows = session.execute(
        select(SupportPlan).where(SupportPlan.user_id == seeded_user.id)
    ).scalars().all()
    active = [r for r in rows if r.active]
    assert len(active) == 1  # old plan deactivated, exactly one active
    assert active[0].plan["next_focus"] == "morning starts before deadlines"
    assert active[0].plan["hypothesis"]  # internal only; Plan API exposes user_summary


def test_case_review_flags_reach_operator_ledger(session, seeded_user):
    from palio.db.models import AuditLog

    case_review.run_for_user(session, seeded_user.id, trigger="l2_event")
    flags = session.execute(
        select(AuditLog).where(
            AuditLog.subject_id == seeded_user.id, AuditLog.action == "case_review_flags"
        )
    ).scalars().all()
    assert flags and "GAD-7" in flags[-1].detail["flags"][0]


def test_case_file_never_contains_raw_message_text(session, seeded_user):
    """The case file carries safety-event METADATA, not message content."""
    from palio.db.models import ChatSession, Message, MessageRole

    chat = ChatSession(user_id=seeded_user.id)
    session.add(chat)
    session.flush()
    session.add(
        Message(
            session_id=chat.id,
            user_id=seeded_user.id,
            role=MessageRole.user,
            content="SECRET_RAW_MESSAGE_TEXT",
        )
    )
    session.flush()
    case_file = case_review._case_file(session, seeded_user)
    assert "SECRET_RAW_MESSAGE_TEXT" not in case_file


# ── Dependency wiring in the turn loop ───────────────────────────────────────


def test_dependency_signal_reaches_companion_state(session, make_user):
    from palio.db.models import ChatSession, SafetyEvent
    from palio.orchestrator import turn

    user = make_user(locale=Locale.ar)
    chat = ChatSession(user_id=user.id)
    session.add(chat)
    session.flush()

    captured = {}

    def sentinel_responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": "L0", "rationale": "x"})

    def companion(system, messages):
        captured["system"] = system
        return "أنا سعيد إني معك — وأود أيضاً أن يكون حولك إنسان قريب."

    gateway.fake_registry.install("sentinel", sentinel_responder)
    gateway.fake_registry.install("router", lambda s, m: json.dumps({"role": "companion"}))
    gateway.fake_registry.install("companion", companion)

    turn.process_turn(session, user=user, chat=chat, text="أنت الوحيد اللي أكلمه")
    assert "caring boundary" in captured["system"]

    events = session.execute(
        select(SafetyEvent).where(
            SafetyEvent.subject_id == user.id, SafetyEvent.event_type == "dependency_signal"
        )
    ).scalars().all()
    assert events


# ── Operator metrics ─────────────────────────────────────────────────────────


def test_metrics_endpoint_token_gated(monkeypatch):
    from palio.config import get_settings

    with TestClient(app) as client:
        # unset token => endpoint hidden
        monkeypatch.setattr(get_settings(), "operator_token", "")
        assert client.get("/operator/metrics").status_code == 404

        monkeypatch.setattr(get_settings(), "operator_token", "s3cret")
        assert client.get("/operator/metrics").status_code == 403
        resp = client.get("/operator/metrics", headers={"X-Operator-Token": "s3cret"})
        assert resp.status_code == 200
        data = resp.json()
        assert "screeners" in data and "referral_taps_30d" in data
        # engagement-time metrics are deliberately absent (§3)
        assert "dau" not in json.dumps(data).lower()
