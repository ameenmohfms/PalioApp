"""Phase 5: extractor, confirmation queue, context-pack A2 guarantee."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from palio.db.models import (
    ChatSession,
    Message,
    MessageRole,
    Pattern,
    PatternStatus,
    PatternType,
)
from palio.llm import gateway
from palio.main import app
from palio.orchestrator import context
from palio.patterns import extractor

pytestmark = pytest.mark.pg


@pytest.fixture
def chat_with_messages(session, make_user):
    user = make_user()
    chat = ChatSession(user_id=user.id)
    session.add(chat)
    session.flush()
    msgs = []
    for role, text in [
        (MessageRole.user, "كل مرة عندي دوام صباحي أتأخر وأتوتر"),
        (MessageRole.assistant, "يبدو أن الصباحات صعبة عليك"),
        (MessageRole.user, "بس لما رتبت أغراضي من الليل الأمور مشت أفضل"),
    ]:
        msg = Message(session_id=chat.id, user_id=user.id, role=role, content=text)
        session.add(msg)
        session.flush()
        msgs.append(msg)
    return user, chat, msgs


def _install_extractor(observations, summary="جلسة عن صعوبة الصباحات."):
    gateway.fake_registry.install(
        "pattern_extractor",
        lambda s, m: json.dumps(
            {"observations": observations, "session_summary": summary}, ensure_ascii=False
        ),
    )


@pytest.fixture(autouse=True)
def _clear_fakes():
    yield
    gateway.fake_registry.clear()


# ── Extractor ────────────────────────────────────────────────────────────────


def test_extractor_creates_proposed_patterns_with_evidence(session, chat_with_messages):
    user, chat, msgs = chat_with_messages
    _install_extractor(
        [
            {
                "text": "الصباحات قبل الدوام وقت توتر متكرر",
                "type": "trigger",
                "evidence_ids": [str(msgs[0].id)],
                "confidence": 0.9,
            },
            {
                "text": "الترتيب من الليل يسهّل الصباح",
                "type": "strength",
                "evidence_ids": [str(msgs[2].id)],
                "confidence": 0.8,
            },
        ]
    )
    created = extractor.extract_for_session(session, chat.id)
    assert created == 2
    rows = session.execute(select(Pattern).where(Pattern.user_id == user.id)).scalars().all()
    assert all(r.status == PatternStatus.proposed for r in rows)
    assert all(r.evidence_ids for r in rows)
    session.refresh(chat)
    assert chat.summary


def test_extractor_drops_observations_without_valid_evidence(session, chat_with_messages):
    user, chat, msgs = chat_with_messages
    _install_extractor(
        [
            {"text": "بدون دليل", "type": "trigger", "evidence_ids": [], "confidence": 0.9},
            {
                "text": "دليل مزور من جلسة ثانية",
                "type": "trigger",
                "evidence_ids": [str(uuid.uuid4())],
                "confidence": 0.9,
            },
        ]
    )
    assert extractor.extract_for_session(session, chat.id) == 0


def test_extractor_skips_memory_paused_session(session, chat_with_messages):
    user, chat, msgs = chat_with_messages
    chat.memory_paused = True
    session.flush()

    def explode(s, m):
        raise AssertionError("extractor must not run on a memory-paused session")

    gateway.fake_registry.install("pattern_extractor", explode)
    assert extractor.extract_for_session(session, chat.id) == 0


def test_extractor_never_confirms(session, chat_with_messages):
    """Even if the model claims 'confirmed', rows start proposed."""
    user, chat, msgs = chat_with_messages
    _install_extractor(
        [
            {
                "text": "نمط",
                "type": "trigger",
                "evidence_ids": [str(msgs[0].id)],
                "confidence": 1.0,
                "status": "confirmed",
            }
        ]
    )
    extractor.extract_for_session(session, chat.id)
    row = session.execute(select(Pattern).where(Pattern.user_id == user.id)).scalar_one()
    assert row.status == PatternStatus.proposed


# ── Context pack (Phase 5 gate: only confirmed patterns, ever) ───────────────


def test_context_pack_contains_only_confirmed(session, make_user):
    user = make_user()
    session.add_all(
        [
            Pattern(
                user_id=user.id,
                type=PatternType.trigger,
                text="PROPOSED_MUST_NOT_APPEAR",
                status=PatternStatus.proposed,
            ),
            Pattern(
                user_id=user.id,
                type=PatternType.trigger,
                text="REJECTED_MUST_NOT_APPEAR",
                status=PatternStatus.rejected,
            ),
            Pattern(
                user_id=user.id,
                type=PatternType.win,
                text="CONFIRMED_WIN_APPEARS",
                status=PatternStatus.confirmed,
            ),
        ]
    )
    session.flush()
    pack = context.build(session, user)
    assert "CONFIRMED_WIN_APPEARS" in pack.text
    assert "PROPOSED_MUST_NOT_APPEAR" not in pack.text
    assert "REJECTED_MUST_NOT_APPEAR" not in pack.text
    assert pack.composition["approx_tokens"] <= context.TOKEN_CAP


def test_context_pack_puts_wins_and_strengths_first(session, make_user):
    user = make_user()
    session.add_all(
        [
            Pattern(
                user_id=user.id,
                type=PatternType.trigger,
                text="a trigger",
                status=PatternStatus.confirmed,
            ),
            Pattern(
                user_id=user.id,
                type=PatternType.win,
                text="a win",
                status=PatternStatus.confirmed,
            ),
        ]
    )
    session.flush()
    pack = context.build(session, user)
    assert pack.text.index("a win") < pack.text.index("a trigger")


def test_context_pack_token_cap(session, make_user):
    user = make_user()
    for i in range(12):
        session.add(
            Pattern(
                user_id=user.id,
                type=PatternType.context,
                text=f"pattern {i} " + "x" * 480,
                status=PatternStatus.confirmed,
            )
        )
    session.flush()
    pack = context.build(session, user)
    assert len(pack.text) <= context.TOKEN_CAP * context.CHARS_PER_TOKEN
    assert pack.composition.get("truncated") is True


# ── HTTP: confirmation queue + memory controls ───────────────────────────────


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def http_env(client):
    def sentinel_responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": "L0", "rationale": "x"})

    gateway.fake_registry.install("sentinel", sentinel_responder)
    resp = client.post(
        "/auth/guest",
        json={
            "device_guest_id": uuid.uuid4().hex,
            "nickname": "P",
            "locale": "ar",
            "attested_adult": True,
        },
    ).json()
    return client, {"Authorization": f"Bearer {resp['token']}"}, resp["user_id"]


def test_confirm_edit_reject_delete_flow(http_env, session):
    client, headers, user_id = http_env
    proposals = [(PatternStatus.proposed, "اقتراح أ"), (PatternStatus.proposed, "اقتراح ب")]
    for status, text in proposals:
        session.add(
            Pattern(
                user_id=uuid.UUID(user_id), type=PatternType.trigger, text=text, status=status
            )
        )
    session.commit()

    listing = client.get("/patterns", headers=headers).json()
    assert len(listing["proposed"]) == 2

    first, second = listing["proposed"]
    confirmed = client.post(f"/patterns/{first['id']}/confirm", headers=headers).json()
    assert confirmed["status"] == "confirmed"

    edited = client.patch(
        f"/patterns/{first['id']}", headers=headers, json={"text": "نص معدل من المستخدم"}
    ).json()
    assert edited["text"] == "نص معدل من المستخدم"

    rejected = client.post(f"/patterns/{second['id']}/reject", headers=headers).json()
    assert rejected["status"] == "rejected"

    deleted = client.delete(f"/patterns/{first['id']}", headers=headers).json()
    assert deleted == {"deleted": True}
    listing = client.get("/patterns", headers=headers).json()
    assert listing["confirmed"] == [] and listing["proposed"] == []


def test_patterns_are_user_scoped(http_env, session, make_user):
    client, headers, _ = http_env
    other = make_user()
    session.add(
        Pattern(
            user_id=other.id, type=PatternType.trigger, text="غيري", status=PatternStatus.proposed
        )
    )
    session.commit()
    pid = session.execute(select(Pattern.id).where(Pattern.user_id == other.id)).scalar_one()
    resp = client.post(f"/patterns/{pid}/confirm", headers=headers)
    assert resp.status_code == 404


def test_session_end_schedules_extraction_unless_paused(http_env, session):
    from palio.db.models import Job

    client, headers, _ = http_env
    chat = client.post("/chat/sessions", headers=headers).json()
    client.patch(
        f"/chat/sessions/{chat['id']}/memory", headers=headers, json={"paused": True}
    )
    ended = client.post(f"/chat/sessions/{chat['id']}/end", headers=headers).json()
    assert ended["extraction_scheduled"] is False

    chat2 = client.post("/chat/sessions", headers=headers).json()
    ended2 = client.post(f"/chat/sessions/{chat2['id']}/end", headers=headers).json()
    assert ended2["extraction_scheduled"] is True
    jobs = session.execute(
        select(Job).where(Job.kind == "pattern_extraction")
    ).scalars().all()
    assert any(j.payload.get("session_id") == chat2["id"] for j in jobs)