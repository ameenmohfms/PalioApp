import pytest
from fastapi.testclient import TestClient

from palio.main import app

pytestmark = pytest.mark.pg


def test_healthz_ok():
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
