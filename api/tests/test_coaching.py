"""Phase 4: strategy library, lifecycle, coach routing + suppression."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from palio.coaching import library
from palio.db.models import AgentRole, RiskLevel
from palio.llm import gateway
from palio.main import app

pytestmark = pytest.mark.pg


# ── Library ──────────────────────────────────────────────────────────────────


def test_library_has_ten_bilingual_strategies():
    strategies = library.load_all()
    assert len(strategies) >= 10
    for key, strategy in strategies.items():
        for lang in ("en", "ar"):
            for field in ("title", "summary", "steps", "try_this_week", "adapt_if"):
                assert strategy[lang][field], (key, lang, field)
        assert strategy["requires_clinical_signoff"] is True  # §16 #3


def test_library_content_passes_draft_safety_scan():
    """No strategy text may contain diagnosis/medication/promise patterns."""
    from palio.safety import post_rules

    for key, strategy in library.load_all().items():
        for lang in ("en", "ar"):
            blob = json.dumps(strategy[lang], ensure_ascii=False)
            hits = post_rules.scan_draft(blob)
            assert not hits, (key, lang, [h.id for h in hits])


# ── HTTP lifecycle ───────────────────────────────────────────────────────────


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def headers(client):
    resp = client.post(
        "/auth/guest",
        json={
            "device_guest_id": uuid.uuid4().hex,
            "nickname": "T",
            "locale": "ar",
            "attested_adult": True,
        },
    )
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_assign_try_rate_adapt_lifecycle(client, headers):
    plan = client.get("/coaching/plan", headers=headers).json()
    assert len(plan["library"]) >= 10
    assert plan["strategies"] == []

    assigned = client.post(
        "/coaching/assign", headers=headers, json={"strategy_key": "task_breakdown"}
    ).json()
    assert assigned["status"] == "assigned"
    assert assigned["title"] == "صغّر أول خطوة"  # Arabic locale content

    # Re-assign is idempotent while active.
    again = client.post(
        "/coaching/assign", headers=headers, json={"strategy_key": "task_breakdown"}
    ).json()
    assert again["id"] == assigned["id"]

    rated = client.post(
        f"/coaching/strategies/{assigned['id']}/feedback",
        headers=headers,
        json={"feedback": "partial", "outcome": "بدأت مرتين من ثلاث"},
    ).json()
    assert rated["status"] == "tried"
    assert rated["feedback"] == "partial"

    adapted = client.post(
        f"/coaching/strategies/{assigned['id']}/adapt", headers=headers
    ).json()
    assert adapted["status"] == "adapted"

    dropped = client.post(
        f"/coaching/strategies/{assigned['id']}/drop", headers=headers
    ).json()
    assert dropped["status"] == "dropped"

    plan = client.get("/coaching/plan", headers=headers).json()
    assert plan["strategies"][0]["status"] == "dropped"


def test_unknown_strategy_rejected(client, headers):
    resp = client.post(
        "/coaching/assign", headers=headers, json={"strategy_key": "improvised_technique"}
    )
    assert resp.status_code == 404


def test_message_reaction(client, headers):
    def sentinel_responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": "L0", "rationale": "x"})

    gateway.fake_registry.install("sentinel", sentinel_responder)
    gateway.fake_registry.install("router", lambda s, m: json.dumps({"role": "companion"}))
    gateway.fake_registry.install("companion", lambda s, m: "جرب تبدأ بخمس دقائق فقط.")
    try:
        chat = client.post("/chat/sessions", headers=headers).json()
        client.post(
            f"/chat/sessions/{chat['id']}/messages", headers=headers, json={"content": "مرحبا"}
        )
        history = client.get(f"/chat/sessions/{chat['id']}/messages", headers=headers).json()
        reply_id = history[-1]["id"]
        resp = client.post(
            f"/coaching/messages/{reply_id}/reaction",
            headers=headers,
            json={"feedback": "helped"},
        )
        assert resp.json() == {"ok": True}
    finally:
        gateway.fake_registry.clear()


# ── Coach routing + suppression in the turn loop ─────────────────────────────


@pytest.fixture
def turn_env(session, make_user):
    from palio.db.models import ChatSession, Locale

    user = make_user(locale=Locale.ar)
    chat = ChatSession(user_id=user.id)
    session.add(chat)
    session.flush()

    def sentinel_responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": "L0", "rationale": "x"})

    gateway.fake_registry.install("sentinel", sentinel_responder)
    gateway.fake_registry.install("router", lambda s, m: json.dumps({"role": "coach"}))
    gateway.fake_registry.install(
        "coach", lambda s, m: "خلنا نجرب استراتيجية «صغّر أول خطوة» هذا الأسبوع."
    )
    gateway.fake_registry.install("companion", lambda s, m: "أنا معك، خذ وقتك اليوم.")
    yield user, chat
    gateway.fake_registry.clear()


def test_coach_handles_l0_turn(session, turn_env):
    from palio.orchestrator import turn

    user, chat = turn_env
    result = turn.process_turn(session, user=user, chat=chat, text="أبغى طريقة أبدأ فيها مذاكرتي")
    assert result.agent_role == AgentRole.coach
    assert "استراتيجية" in result.reply


def test_coach_suppressed_at_l2(session, turn_env):
    """A5 charter: no productivity coaching for a user flagged L1–L2."""
    from sqlalchemy import select

    from palio.db.models import SafetyEvent
    from palio.orchestrator import turn

    user, chat = turn_env
    result = turn.process_turn(session, user=user, chat=chat, text="أتمنى أموت وأرتاح")
    assert result.risk_level == RiskLevel.l2
    assert result.agent_role == AgentRole.companion  # coach was suppressed
    events = session.execute(
        select(SafetyEvent).where(
            SafetyEvent.subject_id == user.id, SafetyEvent.event_type == "coach_suppressed"
        )
    ).scalars().all()
    assert events


def test_coach_prompt_includes_only_library(session, turn_env):
    """The coach's system prompt must carry the library and active strategies."""
    from palio.orchestrator import turn

    user, chat = turn_env
    captured = {}

    def capturing_coach(system, messages):
        captured["system"] = system
        return "جرب «الرفيق الصامت»."

    gateway.fake_registry.install("coach", capturing_coach)
    turn.process_turn(session, user=user, chat=chat, text="وش تنصحني للتركيز؟")
    assert "task_breakdown" in captured["system"]
    assert "body_doubling" in captured["system"]
    # A5 kernel language present in substance:
    assert "ONLY from the" in captured["system"] or "approved library" in captured["system"]