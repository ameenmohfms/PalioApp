"""Orchestrator turn-loop behavior with scripted agents (all pg-backed)."""

import json

import pytest

from palio.db.models import AgentRole, ChatSession, Message, MessageRole, RiskLevel
from palio.llm import gateway
from palio.orchestrator import minors, turn
from palio.safety import crisis

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def _fakes():
    def sentinel_responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": "L0", "rationale": "scripted"})

    def router_responder(system, messages):
        return json.dumps({"role": "companion", "why": "scripted"})

    gateway.fake_registry.install("sentinel", sentinel_responder)
    gateway.fake_registry.install("router", router_responder)
    gateway.fake_registry.install(
        "companion", lambda system, messages: "That sounds heavy. What part weighs most today?"
    )
    yield
    gateway.fake_registry.clear()


@pytest.fixture
def chat(session, make_user):
    user = make_user()
    chat = ChatSession(user_id=user.id)
    session.add(chat)
    session.flush()
    return user, chat


def _messages(session, chat_id):
    from sqlalchemy import select

    return (
        session.execute(
            select(Message).where(Message.session_id == chat_id).order_by(Message.seq)
        )
        .scalars()
        .all()
    )


def test_normal_turn_persists_both_sides(session, chat):
    user, chat_session = chat
    result = turn.process_turn(session, user=user, chat=chat_session, text="اليوم كان يوم طويل")
    assert result.risk_level == RiskLevel.l0
    assert "weighs most" in result.reply

    msgs = _messages(session, chat_session.id)
    assert [m.role for m in msgs] == [MessageRole.user, MessageRole.assistant]
    assert msgs[0].risk_level == RiskLevel.l0
    assert msgs[1].agent_role == AgentRole.companion


def test_l3_triggers_crisis_and_suspends_agents(session, chat):
    user, chat_session = chat
    # Poison the companion: if any agent besides crisis runs, the test fails.
    def explode(system, messages):
        raise AssertionError("companion must be suspended at L3")

    gateway.fake_registry.install("companion", explode)

    result = turn.process_turn(session, user=user, chat=chat_session, text="سأنتحر الليلة")
    assert result.risk_level == RiskLevel.l3
    assert result.ui_action == "crisis_screen"
    assert result.reply == crisis.CRISIS_SCRIPT["ar"]
    assert result.crisis is not None and result.crisis["verified"] is False

    msgs = _messages(session, chat_session.id)
    assert msgs[1].agent_role == AgentRole.crisis


def test_l2_schedules_case_review_and_shows_resources(session, chat):
    from sqlalchemy import select

    from palio.db.models import Job

    user, chat_session = chat
    result = turn.process_turn(
        session, user=user, chat=chat_session, text="sometimes I wish I was dead"
    )
    assert result.risk_level == RiskLevel.l2
    assert result.ui_action == "show_resources"
    jobs = session.execute(select(Job).where(Job.kind == "case_review")).scalars().all()
    assert any(j.payload.get("user_id") == str(user.id) for j in jobs)


def test_minor_gate_redirects_and_restricts(session, chat):
    user, chat_session = chat
    result = turn.process_turn(
        session, user=user, chat=chat_session, text="عمري ١٥ سنة وأحتاج مساعدة في التركيز"
    )
    assert result.reply == minors.MINOR_REDIRECT["ar"]
    assert user.restricted_minor is True

    # Every later message keeps getting the redirect — no normal service.
    result2 = turn.process_turn(session, user=user, chat=chat_session, text="طيب بس ساعدني")
    assert result2.reply == minors.MINOR_REDIRECT["ar"]


def test_post_pass_blocks_bad_companion_draft(session, chat):
    user, chat_session = chat
    gateway.fake_registry.install(
        "companion", lambda system, messages: "Clearly you have ADHD, no doubt about it."
    )
    result = turn.process_turn(session, user=user, chat=chat_session, text="do I have adhd?")
    # rewrite is attempted via companion (same bad responder) => safe fallback
    from palio.safety.sentinel import SAFE_FALLBACK

    assert result.reply == SAFE_FALLBACK["ar"]
    assert any(v.startswith("N1") for v in result.violations)


def test_kill_switch_yields_busy_fallback(session, chat, monkeypatch):
    from palio.config import get_settings

    user, chat_session = chat
    monkeypatch.setattr(get_settings(), "palio_kill_companion", True)
    result = turn.process_turn(session, user=user, chat=chat_session, text="hello")
    assert result.reply == turn.BUSY_FALLBACK["ar"]
