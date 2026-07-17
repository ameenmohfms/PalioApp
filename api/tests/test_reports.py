"""Phase 6: report contents (confirmed-only), referrals, export, hard delete."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from palio.db.models import (
    Pattern,
    PatternStatus,
    PatternType,
    ReferralEntry,
    StrategyFeedback,
    StrategyLog,
    StrategyStatus,
    SupportPlan,
)
from palio.llm import gateway
from palio.main import app
from palio.reports import generator

pytestmark = pytest.mark.pg


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def env(client, session):
    def sentinel_responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": "L0", "rationale": "x"})

    gateway.fake_registry.install("sentinel", sentinel_responder)
    resp = client.post(
        "/auth/guest",
        json={
            "device_guest_id": uuid.uuid4().hex,
            "nickname": "نور",
            "locale": "ar",
            "attested_adult": True,
        },
    ).json()
    user_id = uuid.UUID(resp["user_id"])
    headers = {"Authorization": f"Bearer {resp['token']}"}

    session.add_all(
        [
            Pattern(
                user_id=user_id,
                type=PatternType.trigger,
                text="CONFIRMED_TRIGGER_IN_REPORT",
                status=PatternStatus.confirmed,
            ),
            Pattern(
                user_id=user_id,
                type=PatternType.win,
                text="CONFIRMED_WIN_IN_REPORT",
                status=PatternStatus.confirmed,
            ),
            Pattern(
                user_id=user_id,
                type=PatternType.trigger,
                text="PROPOSED_NEVER_IN_REPORT",
                status=PatternStatus.proposed,
            ),
            SupportPlan(
                user_id=user_id,
                plan={"hypothesis": "HYPOTHESIS_NEVER_IN_REPORT", "user_summary": "خطة"},
                active=True,
            ),
            StrategyLog(
                user_id=user_id,
                strategy_key="task_breakdown",
                status=StrategyStatus.tried,
                feedback=StrategyFeedback.helped,
                outcome="بدأت ثلاث مرات هذا الأسبوع",
            ),
        ]
    )
    session.commit()
    yield client, headers, user_id
    gateway.fake_registry.clear()


def test_report_html_contains_only_confirmed_data(env, session):
    from palio.db.models import User

    client, headers, user_id = env
    user = session.get(User, user_id)
    html = generator.build_html(session, user, language="ar")
    assert "CONFIRMED_TRIGGER_IN_REPORT" in html
    assert "CONFIRMED_WIN_IN_REPORT" in html
    assert "PROPOSED_NEVER_IN_REPORT" not in html
    assert "HYPOTHESIS_NEVER_IN_REPORT" not in html
    # A4 disclaimer header, Arabic
    assert "ليس طبيباً وليس أداة تشخيص" in html
    assert 'dir="rtl"' in html
    # strategy + outcome present
    assert "ساعدت" in html and "بدأت ثلاث مرات" in html


def test_report_meds_only_when_explicitly_typed(env, session):
    from palio.db.models import User

    client, headers, user_id = env
    user = session.get(User, user_id)
    without = generator.build_html(session, user, language="en")
    assert "user-reported" not in without.lower() or "Medications" not in without

    with_meds = generator.build_html(
        session, user, language="en", user_medications="Concerta 36mg (self-reported)"
    )
    assert "Concerta 36mg" in with_meds
    assert "user-reported" in with_meds


def test_report_generation_pdf_and_consent(env, session):
    client, headers, user_id = env
    resp = client.post(
        "/reports",
        headers=headers,
        json={"language": "ar", "consent_share": True},
    )
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]

    download = client.get(f"/reports/{report_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content[:5] == b"%PDF-"

    from palio.db.models import Consent

    consents = session.execute(
        select(Consent).where(Consent.user_id == user_id, Consent.consent_key == "report_share")
    ).scalars().all()
    assert consents

    # consent gate
    refused = client.post("/reports", headers=headers, json={"consent_share": False})
    assert refused.status_code == 400


def test_referrals_filtered_and_tap_logged(env, session):
    client, headers, user_id = env
    session.add_all(
        [
            ReferralEntry(
                name="عيادة الرياض",
                type="clinic",
                city="Riyadh",
                languages=["ar", "en"],
                contact="011-000-0000",
                telehealth=False,
                verified_by="Operator, 2026-07-01",
            ),
            ReferralEntry(
                name="عيادة جدة",
                type="clinic",
                city="Jeddah",
                languages=["ar"],
                contact="012-000-0000",
                telehealth=False,
                verified_by="Operator, 2026-07-01",
            ),
            ReferralEntry(
                name="منصة عن بعد",
                type="telehealth",
                city="Riyadh",
                languages=["ar"],
                contact="https://example.invalid",
                telehealth=True,
                verified_by="Operator, 2026-07-01",
            ),
        ]
    )
    session.commit()

    client.patch("/account/city", headers=headers, json={"city": "Riyadh"})
    rows = client.get("/referrals", headers=headers).json()
    names = {r["name"] for r in rows}
    assert "عيادة الرياض" in names and "منصة عن بعد" in names
    assert "عيادة جدة" not in names  # different city, not telehealth

    tap = client.post(f"/referrals/{rows[0]['id']}/tap", headers=headers)
    assert tap.json() == {"ok": True}

    from palio.db.models import AuditLog

    taps = session.execute(
        select(AuditLog).where(
            AuditLog.subject_id == user_id, AuditLog.action == "referral_tapped"
        )
    ).scalars().all()
    assert taps


def test_export_then_hard_delete(env, session):
    client, headers, user_id = env
    chat = client.post("/chat/sessions", headers=headers).json()
    gateway.fake_registry.install("router", lambda s, m: json.dumps({"role": "companion"}))
    gateway.fake_registry.install("companion", lambda s, m: "أهلاً")
    client.post(f"/chat/sessions/{chat['id']}/messages", headers=headers, json={"content": "مرحبا"})

    exported = client.get("/account/export", headers=headers).json()
    assert exported["profile"]["nickname"] == "نور"
    assert len(exported["messages"]) == 2
    assert any(p["text"] == "CONFIRMED_TRIGGER_IN_REPORT" for p in exported["patterns"])
    assert exported["consents"] == []

    resp = client.request("DELETE", "/account", headers=headers)
    assert resp.json() == {"deleted": True}

    # Every user-owned row is gone (Phase 6 gate).
    from palio.db.models import ChatSession, Message, User

    session.expire_all()
    assert session.get(User, user_id) is None
    for model in (Message, Pattern, ChatSession, StrategyLog, SupportPlan):
        rows = session.execute(select(model).where(model.user_id == user_id)).scalars().all()
        assert rows == [], model.__name__

    # The append-only audit ledger keeps the (opaque) deletion record.
    from palio.db.models import AuditLog

    ledger = session.execute(
        select(AuditLog).where(
            AuditLog.subject_id == user_id, AuditLog.action == "account_deleted"
        )
    ).scalars().all()
    assert ledger

    # Token is dead.
    assert client.get("/account/export", headers=headers).status_code == 401
