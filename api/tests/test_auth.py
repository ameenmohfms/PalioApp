"""Auth flows over HTTP: guest-first, attestation gate, OTP, migration."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from palio.llm import gateway
from palio.main import app

pytestmark = pytest.mark.pg


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fakes():
    def sentinel_responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": "L0", "rationale": "scripted"})

    gateway.fake_registry.install("sentinel", sentinel_responder)
    gateway.fake_registry.install(
        "router", lambda s, m: json.dumps({"role": "companion", "why": "x"})
    )
    gateway.fake_registry.install("companion", lambda s, m: "أهلاً! وش اللي شاغل بالك اليوم؟")
    yield
    gateway.fake_registry.clear()


def _guest(client, **overrides) -> dict:
    body = {
        "device_guest_id": uuid.uuid4().hex,
        "nickname": "نور",
        "locale": "ar",
        "attested_adult": True,
    }
    body.update(overrides)
    resp = client.post("/auth/guest", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_guest_requires_attestation(client):
    resp = client.post(
        "/auth/guest",
        json={
            "device_guest_id": uuid.uuid4().hex,
            "nickname": "x",
            "locale": "ar",
            "attested_adult": False,
        },
    )
    assert resp.status_code == 403


def test_guest_first_chat_flow(client):
    guest = _guest(client)
    headers = {"Authorization": f"Bearer {guest['token']}"}

    chat = client.post("/chat/sessions", headers=headers).json()
    resp = client.post(
        f"/chat/sessions/{chat['id']}/messages",
        headers=headers,
        json={"content": "اليوم صار عندي فوضى في المذاكرة"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "L0"
    assert "شاغل" in data["reply"]

    history = client.get(f"/chat/sessions/{chat['id']}/messages", headers=headers).json()
    assert [h["role"] for h in history] == ["user", "assistant"]


def test_sessions_are_user_scoped(client):
    guest_a = _guest(client)
    guest_b = _guest(client)
    chat_a = client.post(
        "/chat/sessions", headers={"Authorization": f"Bearer {guest_a['token']}"}
    ).json()
    resp = client.get(
        f"/chat/sessions/{chat_a['id']}/messages",
        headers={"Authorization": f"Bearer {guest_b['token']}"},
    )
    assert resp.status_code == 404


def test_otp_upgrade_keeps_guest_data(client):
    guest = _guest(client)
    headers = {"Authorization": f"Bearer {guest['token']}"}
    chat = client.post("/chat/sessions", headers=headers).json()
    client.post(
        f"/chat/sessions/{chat['id']}/messages", headers=headers, json={"content": "مرحبا"}
    )

    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    code = client.post("/auth/otp/request", json={"email": email}).json()["dev_code"]
    verified = client.post(
        "/auth/otp/verify", json={"email": email, "code": code}, headers=headers
    ).json()
    assert verified["is_guest"] is False
    assert verified["user_id"] == guest["user_id"]  # guest row became the account

    # Old session still reachable with the new token.
    new_headers = {"Authorization": f"Bearer {verified['token']}"}
    history = client.get(f"/chat/sessions/{chat['id']}/messages", headers=new_headers).json()
    assert len(history) == 2


def test_otp_wrong_code_rejected(client):
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/auth/otp/request", json={"email": email})
    resp = client.post("/auth/otp/verify", json={"email": email, "code": "000000"})
    assert resp.status_code == 401


def test_guest_migration_into_existing_account(client):
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    # Existing account (no guest attached).
    code = client.post("/auth/otp/request", json={"email": email}).json()["dev_code"]
    account = client.post("/auth/otp/verify", json={"email": email, "code": code}).json()

    # New device, new guest, with data.
    guest = _guest(client)
    headers = {"Authorization": f"Bearer {guest['token']}"}
    chat = client.post("/chat/sessions", headers=headers).json()
    client.post(
        f"/chat/sessions/{chat['id']}/messages", headers=headers, json={"content": "مرحبا"}
    )

    # Sign in on that device: guest data re-parents to the account.
    code2 = client.post("/auth/otp/request", json={"email": email}).json()["dev_code"]
    merged = client.post(
        "/auth/otp/verify", json={"email": email, "code": code2}, headers=headers
    ).json()
    assert merged["user_id"] == account["user_id"]

    account_headers = {"Authorization": f"Bearer {merged['token']}"}
    history = client.get(
        f"/chat/sessions/{chat['id']}/messages", headers=account_headers
    ).json()
    assert len(history) == 2

    # The guest token no longer works (its user row is gone).
    resp = client.post("/chat/sessions", headers=headers)
    assert resp.status_code == 401


def test_google_fake_flow(client, monkeypatch):
    monkeypatch.setenv("PALIO_FAKE_GOOGLE_AUTH", "1")
    sub = uuid.uuid4().hex[:12]
    resp = client.post(
        "/auth/google", json={"id_token": f"fake-google:{sub}:g-{sub}@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_guest"] is False
