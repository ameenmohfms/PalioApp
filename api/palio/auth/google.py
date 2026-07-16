"""Google OAuth id_token verification.

Live mode verifies against Google's JWKS. Test/dev fake mode (PALIO_LLM_MODE
is unrelated — this uses its own env toggle) accepts tokens of the form
"fake-google:<sub>:<email>" so flows are testable without Google."""

import os

import httpx
from jose import JWTError, jwt

from palio.config import get_settings

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


class GoogleAuthError(Exception):
    pass


def verify_id_token(id_token: str) -> tuple[str, str]:
    """Return (google_sub, email) or raise GoogleAuthError."""
    if os.environ.get("PALIO_FAKE_GOOGLE_AUTH") == "1":
        parts = id_token.split(":")
        if len(parts) == 3 and parts[0] == "fake-google":
            return parts[1], parts[2]
        raise GoogleAuthError("malformed fake google token")

    settings = get_settings()
    if not settings.google_client_id:
        raise GoogleAuthError("google oauth not configured (GOOGLE_CLIENT_ID)")
    try:
        jwks = httpx.get(GOOGLE_JWKS_URL, timeout=10).json()
        claims = jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256"],
            audience=settings.google_client_id,
        )
    except (httpx.HTTPError, JWTError) as exc:
        raise GoogleAuthError(f"google token verification failed: {exc}") from exc
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleAuthError("unexpected issuer")
    if not claims.get("email_verified", False):
        raise GoogleAuthError("google email not verified")
    return str(claims["sub"]), str(claims["email"]).lower()
