"""JWT session tokens. Guest and account users get the same token shape;
the user row's is_guest flag is the source of truth."""

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from palio.config import get_settings

ALGORITHM = "HS256"


class TokenError(Exception):
    pass


def issue(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=settings.jwt_ttl_hours)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def verify(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        return uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise TokenError("invalid token") from exc
