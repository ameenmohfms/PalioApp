"""Engine, session factory, and the mandatory user-scoping helper (D6).

Every query against a user-owned table MUST go through `user_scoped()`.
Row-level scoping is a Hard-Rule-adjacent control (§11): forgetting a
WHERE clause must be impossible by construction, not by review.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Select, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from palio.config import get_settings

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


@contextmanager
def db_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def user_scoped(model: type, user_id: uuid.UUID) -> Select:
    """Build a SELECT restricted to one user's rows.

    Raises if the model has no user_id column — user-owned tables must
    declare one; global tables (instruments, referral directory) must
    not be queried through this helper.
    """
    col = getattr(model, "user_id", None)
    if col is None:
        raise TypeError(f"{model.__name__} has no user_id column; user_scoped() is mandatory "
                        "only for user-owned tables — use plain select() for global tables.")
    return select(model).where(col == user_id)
