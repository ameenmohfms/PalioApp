"""Report & referral endpoints (spec §9)."""

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from palio.audit.events import record_audit
from palio.auth.deps import DbDep, UserDep
from palio.db.models import Consent, ReferralEntry, Report
from palio.reports import generator

router = APIRouter(tags=["reports"])


class GenerateIn(BaseModel):
    language: str | None = Field(default=None, pattern="^(ar|en)$")
    # ONLY surfaced in the report if the user explicitly typed it here (§9).
    user_medications: str | None = Field(default=None, max_length=2000)
    consent_share: bool = Field(description="user confirmed they intend to share this summary")


class ReportOut(BaseModel):
    id: str
    language: str
    created_at: str


@router.post("/reports", response_model=ReportOut)
def create_report(body: GenerateIn, user: UserDep, db: DbDep) -> ReportOut:
    if not body.consent_share:
        raise HTTPException(status_code=400, detail="report consent is required")
    db.add(Consent(user_id=user.id, consent_key="report_share", version="1", granted=True))
    report = generator.generate(
        db, user, language=body.language, user_medications=body.user_medications
    )
    return ReportOut(
        id=str(report.id),
        language=report.language.value,
        created_at=report.created_at.isoformat() if report.created_at else "",
    )


@router.get("/reports", response_model=list[ReportOut])
def list_reports(user: UserDep, db: DbDep) -> list[ReportOut]:
    rows = db.execute(
        select(Report).where(Report.user_id == user.id).order_by(Report.created_at.desc())
    ).scalars()
    return [
        ReportOut(
            id=str(r.id),
            language=r.language.value,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]


@router.get("/reports/{report_id}/download")
def download(report_id: str, user: UserDep, db: DbDep) -> FileResponse:
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown report") from None
    report = db.execute(
        select(Report).where(Report.id == rid, Report.user_id == user.id)
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="unknown report")
    path = generator.reports_dir() / report.meta["file"]
    if not path.is_file():
        raise HTTPException(status_code=410, detail="report artifact no longer available")
    return FileResponse(path, media_type="application/pdf", filename="palio_report.pdf")


# ── Referral directory (§9): options, not endorsements ───────────────────────


class ReferralOut(BaseModel):
    id: str
    name: str
    type: str
    city: str
    languages: list[str]
    contact: str
    telehealth: bool


@router.get("/referrals", response_model=list[ReferralOut])
def referrals(user: UserDep, db: DbDep, city: str | None = None) -> list[ReferralOut]:
    stmt = select(ReferralEntry)
    chosen_city = city or user.city
    if chosen_city:
        stmt = stmt.where(
            (ReferralEntry.city.ilike(chosen_city)) | (ReferralEntry.telehealth.is_(True))
        )
    rows = db.execute(stmt.order_by(ReferralEntry.name).limit(100)).scalars()
    return [
        ReferralOut(
            id=str(r.id),
            name=r.name,
            type=r.type,
            city=r.city,
            languages=r.languages or [],
            contact=r.contact,
            telehealth=r.telehealth,
        )
        for r in rows
    ]


@router.post("/referrals/{referral_id}/tap")
def referral_tap(referral_id: str, user: UserDep, db: DbDep) -> dict:
    """Primary success metric (§3): the user reached toward real care."""
    try:
        rid = uuid.UUID(referral_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown referral") from None
    if db.get(ReferralEntry, rid) is None:
        raise HTTPException(status_code=404, detail="unknown referral")
    record_audit(actor="user", action="referral_tapped", subject_id=user.id)
    return {"ok": True}


class CityIn(BaseModel):
    city: str | None = Field(default=None, max_length=64)


@router.patch("/account/city")
def set_city(body: CityIn, user: UserDep, db: DbDep) -> dict:
    """User-chosen city, used only for referral filtering (N9)."""
    user.city = (body.city or "").strip()[:64] or None
    db.flush()
    return {"city": user.city}
