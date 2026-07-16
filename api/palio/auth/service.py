"""Auth flows: guest-first identity, email OTP, Google OAuth, guest migration.

Data minimization (N9): a user is nickname + locale (+ optional city later).
18+ attestation is a boolean, never a birth date. Guest data migrates to the
account user in one transaction on first sign-in (D22)."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from palio.audit.events import record_audit
from palio.config import get_settings
from palio.db.models import (
    AuthOtp,
    ChatSession,
    Consent,
    LlmUsage,
    Message,
    Pattern,
    PatternEdge,
    Report,
    ScreenerResult,
    StrategyLog,
    SupportPlan,
    User,
)

log = structlog.get_logger()

_USER_OWNED = (
    ChatSession,
    Message,
    Pattern,
    PatternEdge,
    ScreenerResult,
    SupportPlan,
    StrategyLog,
    Report,
    Consent,
    LlmUsage,
)


class AuthFlowError(Exception):
    pass


def get_or_create_guest(
    session: Session, *, device_guest_id: str, nickname: str, locale: str, attested_adult: bool
) -> User:
    if not attested_adult:
        raise AuthFlowError("18+ attestation is required (N7)")
    user = session.execute(
        select(User).where(User.device_guest_id == device_guest_id)
    ).scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        nickname=nickname.strip()[:64] or "ضيف",  # "guest" — UI enforces a real nickname
        device_guest_id=device_guest_id,
        locale=locale,
        is_guest=True,
        attested_adult=True,
    )
    session.add(user)
    session.flush()
    record_audit(actor="system", action="guest_created", subject_id=user.id)
    return user


# ── Email OTP ────────────────────────────────────────────────────────────────


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def request_otp(session: Session, email: str) -> str | None:
    """Create an OTP. Returns the code in non-production for dev/testing;
    production delivers via the operator-configured mail path and returns None."""
    settings = get_settings()
    email = email.strip().lower()
    code = f"{secrets.randbelow(1_000_000):06d}"
    session.add(
        AuthOtp(
            email=email,
            code_hash=_hash_code(code),
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.otp_ttl_minutes),
        )
    )
    session.flush()
    if settings.is_production:
        # Operator wires SMTP at deploy time; codes must never be logged.
        log.info("otp_requested", email_domain=email.split("@")[-1])
        return None
    log.info("otp_dev_code_issued", email_domain=email.split("@")[-1])
    return code


def verify_otp(session: Session, email: str, code: str) -> bool:
    email = email.strip().lower()
    otp = session.execute(
        select(AuthOtp)
        .where(AuthOtp.email == email, ~AuthOtp.consumed)
        .order_by(AuthOtp.created_at.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    if otp is None:
        return False
    otp.attempts += 1
    if otp.attempts > 5 or otp.expires_at < datetime.now(UTC):
        otp.consumed = True
        session.flush()
        return False
    if otp.code_hash != _hash_code(code.strip()):
        session.flush()
        return False
    otp.consumed = True
    session.flush()
    return True


# ── Account attach / guest migration (D22) ──────────────────────────────────


def sign_in(
    session: Session,
    *,
    email: str | None = None,
    google_sub: str | None = None,
    guest: User | None = None,
) -> User:
    """Resolve the account user for a verified identity and migrate guest data.

    - No existing account + guest present: the guest row BECOMES the account
      (cheapest migration: nothing moves).
    - Existing account + guest present: guest-owned rows are re-parented to
      the account in this transaction, then the guest row is deleted.
    """
    email = email.strip().lower() if email else None
    account: User | None = None
    if google_sub:
        account = session.execute(
            select(User).where(User.google_sub == google_sub)
        ).scalar_one_or_none()
    if account is None and email:
        account = session.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if account is None:
        if guest is not None:
            guest.is_guest = False
            guest.email = email or guest.email
            guest.google_sub = google_sub or guest.google_sub
            session.flush()
            record_audit(actor="user", action="guest_upgraded", subject_id=guest.id)
            return guest
        account = User(
            nickname=(email or "user").split("@")[0][:64],
            email=email,
            google_sub=google_sub,
            is_guest=False,
            attested_adult=True,
        )
        session.add(account)
        session.flush()
        record_audit(actor="user", action="account_created", subject_id=account.id)
        return account

    if guest is not None and guest.id != account.id:
        for model in _USER_OWNED:
            session.execute(
                update(model).where(model.user_id == guest.id).values(user_id=account.id)
            )
        session.delete(guest)
        session.flush()
        record_audit(
            actor="user",
            action="guest_migrated",
            subject_id=account.id,
            detail={"from_guest": str(guest.id)},
        )
    if email and not account.email:
        account.email = email
    if google_sub and not account.google_sub:
        account.google_sub = google_sub
    session.flush()
    return account
