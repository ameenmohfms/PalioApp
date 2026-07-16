"""Test bootstrap.

Postgres-backed tests (marker `pg`) expect the dev database from
`docker compose up db` / CI service. Set PALIO_TEST_DATABASE_URL to point
elsewhere. Env is pinned BEFORE any palio import so cached Settings see it.
"""

import os
import uuid

os.environ.setdefault("APP_ENV", "test")
os.environ["DATABASE_URL"] = os.environ.get(
    "PALIO_TEST_DATABASE_URL",
    "postgresql+psycopg://palio:palio-dev-only@localhost:55432/palio",
)

import pytest
from sqlalchemy import text

from palio.db.base import db_session, get_engine


def _pg_available() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if _pg_available():
        return
    skip = pytest.mark.skip(reason="Postgres not reachable; start `docker compose up db`")
    for item in items:
        if "pg" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def session():
    with db_session() as s:
        yield s


@pytest.fixture
def make_user(session):
    """Create a throwaway guest user; cleaned up by test-level delete."""
    from palio.db.models import User

    created = []

    def _make(**kw) -> "User":
        user = User(
            nickname=kw.pop("nickname", f"t-{uuid.uuid4().hex[:8]}"),
            device_guest_id=kw.pop("device_guest_id", uuid.uuid4().hex),
            **kw,
        )
        session.add(user)
        session.flush()
        created.append(user)
        return user

    yield _make

    for user in created:
        session.delete(user)
    session.flush()
