"""Screening endpoints (spec §7).

Flow: consent → start → answer (pausable/resumable) → complete → Formulation.
Item text is served straight from the versioned definition (A3); the app
renders it in fixed cards. PHQ-9 item 9 > 0 escalates to the Sentinel L2
protocol immediately on answer, not at completion.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from palio.assessments import formulation, loader, scoring
from palio.audit.events import record_safety_event
from palio.auth.deps import DbDep, UserDep
from palio.db.models import Consent, RiskLevel, ScreenerInstrument, ScreenerResult
from palio.jobs import queue

router = APIRouter(prefix="/screeners", tags=["screeners"])

CONSENT_KEY = "screening_not_diagnosis"
CONSENT_VERSION = "1"


class InstrumentOut(BaseModel):
    id: str
    key: str
    version: str
    language: str
    title: str
    definition: dict


@router.get("")
def list_instruments(user: UserDep, db: DbDep) -> list[InstrumentOut]:
    return [
        InstrumentOut(
            id=str(inst.id),
            key=inst.key,
            version=inst.version,
            language=inst.language.value,
            title=inst.definition.get("title", inst.key),
            definition=inst.definition,
        )
        for inst in loader.offered(db)
    ]


class StartIn(BaseModel):
    instrument_id: str
    consent: bool = Field(description="user confirmed: screening, not a diagnosis")


class ResultOut(BaseModel):
    id: str
    instrument_key: str
    answers: dict[int, int]
    completed: bool


@router.post("/start", response_model=ResultOut)
def start(body: StartIn, user: UserDep, db: DbDep) -> ResultOut:
    if not body.consent:
        raise HTTPException(status_code=400, detail="screening consent is required")
    try:
        inst_id = uuid.UUID(body.instrument_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown instrument") from None
    inst = db.get(ScreenerInstrument, inst_id)
    if inst is None or inst.placeholder:
        raise HTTPException(status_code=404, detail="unknown instrument")

    db.add(
        Consent(
            user_id=user.id, consent_key=CONSENT_KEY, version=CONSENT_VERSION, granted=True
        )
    )
    result = ScreenerResult(
        user_id=user.id, instrument_id=inst.id, answers={}, scores={}, band=""
    )
    db.add(result)
    db.flush()
    return ResultOut(id=str(result.id), instrument_key=inst.key, answers={}, completed=False)


def _own_result(db, user, result_id: str) -> tuple[ScreenerResult, ScreenerInstrument]:
    try:
        rid = uuid.UUID(result_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown result") from None
    result = db.execute(
        select(ScreenerResult).where(
            ScreenerResult.id == rid, ScreenerResult.user_id == user.id
        )
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="unknown result")
    inst = db.get(ScreenerInstrument, result.instrument_id)
    return result, inst


class AnswerIn(BaseModel):
    item_id: int
    value: int


@router.post("/results/{result_id}/answer", response_model=ResultOut)
def answer(result_id: str, body: AnswerIn, user: UserDep, db: DbDep) -> ResultOut:
    result, inst = _own_result(db, user, result_id)
    if result.taken_at is not None:
        raise HTTPException(status_code=409, detail="screening already completed")

    definition = inst.definition
    item_ids = {item["id"] for item in definition["items"]}
    values = {opt["value"] for opt in definition["scale"]}
    if body.item_id not in item_ids or body.value not in values:
        raise HTTPException(status_code=400, detail="invalid item or value")

    answers = dict(result.answers or {})
    answers[str(body.item_id)] = body.value
    result.answers = answers
    db.flush()

    # PHQ-9 item 9 > 0 → immediate Sentinel escalation (spec §7, A3 charter).
    alerts = (definition.get("scoring") or {}).get("alerts", [])
    for alert in alerts:
        if body.item_id == alert["item"] and body.value >= alert["min_value"]:
            record_safety_event(
                subject_id=user.id,
                session_id=None,
                event_type=alert["event"],
                risk_level=RiskLevel.l2,
                detail={"instrument": inst.key, "item": body.item_id},
            )
            queue.enqueue(
                db, "case_review", {"user_id": str(user.id), "trigger": alert["event"]}
            )

    return ResultOut(
        id=str(result.id),
        instrument_key=inst.key,
        answers={int(k): v for k, v in answers.items()},
        completed=False,
    )


class FormulationOut(BaseModel):
    reported_summary: str
    score_meaning: str
    honest_line: str
    options: list[str]
    rescreen_days: int
    scores: dict
    band_key: str
    alerts: list[str]
    ui_action: str | None = None


@router.post("/results/{result_id}/complete", response_model=FormulationOut)
def complete(result_id: str, user: UserDep, db: DbDep) -> FormulationOut:
    result, inst = _own_result(db, user, result_id)
    if result.taken_at is not None:
        raise HTTPException(status_code=409, detail="screening already completed")

    answers = {int(k): v for k, v in (result.answers or {}).items()}
    try:
        outcome = scoring.score(inst.definition, answers)
    except scoring.ScoringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    result.scores = outcome.scores
    result.band = outcome.band_key
    result.taken_at = datetime.now(UTC)
    db.flush()

    payload = formulation.build(inst.definition, answers, outcome, locale=user.locale.value)
    return FormulationOut(
        reported_summary=payload.reported_summary,
        score_meaning=payload.score_meaning,
        honest_line=payload.honest_line,
        options=payload.options,
        rescreen_days=payload.rescreen_days,
        scores=payload.scores,
        band_key=payload.band_key,
        alerts=payload.alerts,
        ui_action="show_resources" if payload.alerts else None,
    )


class HistoryOut(BaseModel):
    id: str
    instrument_key: str
    scores: dict
    band: str
    taken_at: str | None
    completed: bool


@router.get("/results", response_model=list[HistoryOut])
def results(user: UserDep, db: DbDep) -> list[HistoryOut]:
    rows = (
        db.execute(
            select(ScreenerResult, ScreenerInstrument)
            .join(ScreenerInstrument, ScreenerResult.instrument_id == ScreenerInstrument.id)
            .where(ScreenerResult.user_id == user.id)
            .order_by(ScreenerResult.created_at.desc())
        )
        .all()
    )
    return [
        HistoryOut(
            id=str(res.id),
            instrument_key=inst.key,
            scores=res.scores,
            band=res.band,
            taken_at=res.taken_at.isoformat() if res.taken_at else None,
            completed=res.taken_at is not None,
        )
        for res, inst in rows
    ]
