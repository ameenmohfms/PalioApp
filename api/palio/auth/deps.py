"""FastAPI dependencies for authentication and DB sessions."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from palio.auth import tokens
from palio.db.base import get_session_factory
from palio.db.models import User


def db(request=None) -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbDep = Annotated[Session, Depends(db)]


def current_user(
    session: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        user_id = tokens.verify(authorization.removeprefix("Bearer ").strip())
    except tokens.TokenError:
        raise HTTPException(status_code=401, detail="invalid token") from None
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return user


UserDep = Annotated[User, Depends(current_user)]
