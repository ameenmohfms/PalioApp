"""End-to-end screening flow over HTTP (Phase 3)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from palio.main import app

pytestmark = pytest.mark.pg


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    resp = client.post(
        "/auth/guest",
        json={
            "device_guest_id": uuid.uuid4().hex,
            "nickname": "Test",
            "locale": "en",
            "attested_adult": True,
        },
    )
    data = resp.json()
    return {"Authorization": f"Bearer {data['token']}"}, data["user_id"]


def test_placeholder_arabic_instruments_never_offered(client, auth):
    headers, _ = auth
    instruments = client.get("/screeners", headers=headers).json()
    assert {i["key"] for i in instruments} == {"asrs_v1_1", "phq9", "gad7"}
    assert all(i["language"] == "en" for i in instruments)


def test_consent_required(client, auth):
    headers, _ = auth
    instruments = client.get("/screeners", headers=headers).json()
    resp = client.post(
        "/screeners/start",
        headers=headers,
        json={"instrument_id": instruments[0]["id"], "consent": False},
    )
    assert resp.status_code == 400


def test_full_phq9_flow_with_item9_escalation(client, auth, session):
    headers, user_id = auth
    instruments = client.get("/screeners", headers=headers).json()
    phq9 = next(i for i in instruments if i["key"] == "phq9")

    started = client.post(
        "/screeners/start",
        headers=headers,
        json={"instrument_id": phq9["id"], "consent": True},
    ).json()

    # Answer items one by one (pausable by design); item 9 gets a positive value.
    values = {1: 2, 2: 2, 3: 1, 4: 2, 5: 1, 6: 1, 7: 1, 8: 0, 9: 1}
    for item_id, value in values.items():
        resp = client.post(
            f"/screeners/results/{started['id']}/answer",
            headers=headers,
            json={"item_id": item_id, "value": value},
        )
        assert resp.status_code == 200

    # Item-9 escalation happened at ANSWER time, before completion.
    from palio.db.models import Job, SafetyEvent

    events = session.execute(
        select(SafetyEvent).where(
            SafetyEvent.subject_id == uuid.UUID(user_id),
            SafetyEvent.event_type == "phq9_item9_positive",
        )
    ).scalars().all()
    assert events, "PHQ-9 item 9 > 0 must record an immediate safety event"
    jobs = session.execute(select(Job).where(Job.kind == "case_review")).scalars().all()
    assert any(j.payload.get("trigger") == "phq9_item9_positive" for j in jobs)

    done = client.post(
        f"/screeners/results/{started['id']}/complete", headers=headers
    ).json()
    assert done["scores"]["total"] == sum(values.values())
    assert done["band_key"] == "moderate"
    assert "phq9_item9_positive" in done["alerts"]
    assert done["ui_action"] == "show_resources"
    assert "Only a licensed clinician can diagnose" in done["honest_line"]

    # Completed screenings are immutable.
    resp = client.post(
        f"/screeners/results/{started['id']}/answer",
        headers=headers,
        json={"item_id": 1, "value": 0},
    )
    assert resp.status_code == 409

    history = client.get("/screeners/results", headers=headers).json()
    assert history[0]["completed"] is True
    assert history[0]["band"] == "moderate"


def test_incomplete_screening_cannot_complete(client, auth):
    headers, _ = auth
    instruments = client.get("/screeners", headers=headers).json()
    gad7 = next(i for i in instruments if i["key"] == "gad7")
    started = client.post(
        "/screeners/start",
        headers=headers,
        json={"instrument_id": gad7["id"], "consent": True},
    ).json()
    client.post(
        f"/screeners/results/{started['id']}/answer",
        headers=headers,
        json={"item_id": 1, "value": 2},
    )
    resp = client.post(f"/screeners/results/{started['id']}/complete", headers=headers)
    assert resp.status_code == 400
    assert "missing answers" in resp.json()["detail"]


def test_results_are_user_scoped(client, auth):
    headers_a, _ = auth
    instruments = client.get("/screeners", headers=headers_a).json()
    started = client.post(
        "/screeners/start",
        headers=headers_a,
        json={"instrument_id": instruments[0]["id"], "consent": True},
    ).json()

    resp_b = client.post(
        "/auth/guest",
        json={
            "device_guest_id": uuid.uuid4().hex,
            "nickname": "B",
            "locale": "en",
            "attested_adult": True,
        },
    ).json()
    headers_b = {"Authorization": f"Bearer {resp_b['token']}"}
    resp = client.post(
        f"/screeners/results/{started['id']}/answer",
        headers=headers_b,
        json={"item_id": 1, "value": 1},
    )
    assert resp.status_code == 404
