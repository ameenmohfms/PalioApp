"""Auth endpoints: guest-first, email OTP, Google OAuth, guest migration."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from palio.auth import google, service, tokens
from palio.auth.deps import DbDep
from palio.config import get_settings
from palio.db.models import Locale, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _optional_guest(session, authorization: str | None) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        user_id = tokens.verify(authorization.removeprefix("Bearer ").strip())
    except tokens.TokenError:
        return None
    return session.get(User, user_id)


class GuestIn(BaseModel):
    device_guest_id: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=1, max_length=64)
    locale: Locale = Locale.ar
    attested_adult: bool


class TokenOut(BaseModel):
    token: str
    user_id: str
    nickname: str
    is_guest: bool


@router.post("/guest", response_model=TokenOut)
def guest(body: GuestIn, session: DbDep) -> TokenOut:
    if not body.attested_adult:
        # N7: no service without the 18+ attestation.
        raise HTTPException(status_code=403, detail="18+ attestation required")
    user = service.get_or_create_guest(
        session,
        device_guest_id=body.device_guest_id,
        nickname=body.nickname,
        locale=body.locale,
        attested_adult=body.attested_adult,
    )
    return TokenOut(
        token=tokens.issue(user.id),
        user_id=str(user.id),
        nickname=user.nickname,
        is_guest=user.is_guest,
    )


class OtpRequestIn(BaseModel):
    email: EmailStr


@router.post("/otp/request")
def otp_request(body: OtpRequestIn, session: DbDep) -> dict:
    code = service.request_otp(session, body.email)
    out: dict = {"sent": True}
    if code is not None and not get_settings().is_production:
        out["dev_code"] = code  # non-production convenience only
    return out


class OtpVerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


@router.post("/otp/verify", response_model=TokenOut)
def otp_verify(
    body: OtpVerifyIn,
    session: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenOut:
    if not service.verify_otp(session, body.email, body.code):
        raise HTTPException(status_code=401, detail="invalid or expired code")
    guest_user = _optional_guest(session, authorization)
    user = service.sign_in(session, email=body.email, guest=guest_user)
    return TokenOut(
        token=tokens.issue(user.id),
        user_id=str(user.id),
        nickname=user.nickname,
        is_guest=user.is_guest,
    )


class GoogleIn(BaseModel):
    id_token: str


@router.post("/google", response_model=TokenOut)
def google_sign_in(
    body: GoogleIn,
    session: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenOut:
    try:
        sub, email = google.verify_id_token(body.id_token)
    except google.GoogleAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    guest_user = _optional_guest(session, authorization)
    user = service.sign_in(session, email=email, google_sub=sub, guest=guest_user)
    return TokenOut(
        token=tokens.issue(user.id),
        user_id=str(user.id),
        nickname=user.nickname,
        is_guest=user.is_guest,
    )
