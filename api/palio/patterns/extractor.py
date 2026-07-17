"""Pattern Extractor job (A6, async — spec §8 pipeline).

session ends → this job reads the transcript → proposes observations with
evidence message IDs and confidence → user confirms/edits/rejects in the
Patterns screen. Only user-confirmed patterns ever enter agent context
(Hard Rule A2) — enforced by the context-pack builder, not here.
"""

import json
import re
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from palio.db.models import (
    ChatSession,
    Message,
    MessageRole,
    Pattern,
    PatternStatus,
    PatternType,
)
from palio.llm import gateway, prompts

log = structlog.get_logger()

MAX_OBSERVATIONS = 6
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _transcript(db: Session, chat: ChatSession) -> str:
    rows = (
        db.execute(
            select(Message).where(Message.session_id == chat.id).order_by(Message.seq)
        )
        .scalars()
        .all()
    )
    lines = [
        f"[{m.id}] {m.role.value}: {m.content}"
        for m in rows
        if m.role in (MessageRole.user, MessageRole.assistant)
    ]
    return "\n".join(lines)


def _existing_pattern_texts(db: Session, user_id: uuid.UUID) -> list[str]:
    rows = (
        db.execute(
            select(Pattern.text).where(
                Pattern.user_id == user_id,
                Pattern.status != PatternStatus.rejected,
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def extract_for_session(db: Session, session_id: uuid.UUID) -> int:
    """Run extraction for one ended session. Returns proposed-pattern count.

    Idempotent: a session that already produced patterns is skipped (the
    job may retry after a crash)."""
    chat = db.get(ChatSession, session_id)
    if chat is None:
        log.warning("extractor_missing_session", session_id=str(session_id))
        return 0
    if chat.memory_paused:
        log.info("extractor_skipped_memory_paused", session_id=str(session_id))
        return 0

    already = db.execute(
        select(Pattern).where(Pattern.user_id == chat.user_id).limit(200)
    ).scalars()
    session_msg_ids = {
        str(mid)
        for mid in db.execute(
            select(Message.id).where(Message.session_id == chat.id)
        ).scalars()
    }
    for pattern in already:
        if any(str(ev) in session_msg_ids for ev in pattern.evidence_ids or []):
            log.info("extractor_already_ran", session_id=str(session_id))
            return 0

    transcript = _transcript(db, chat)
    if not transcript.strip():
        return 0

    existing = _existing_pattern_texts(db, chat.user_id)
    prompt_input = (
        "## Existing patterns (do not duplicate)\n"
        + "\n".join(f"- {t}" for t in existing[:40])
        + "\n\n## Transcript\n"
        + transcript
    )
    result = gateway.complete(
        "pattern_extractor",
        system=prompts.load("pattern_extractor"),
        messages=[{"role": "user", "content": prompt_input}],
        max_tokens=1500,
        temperature=0.0,
        user_id=chat.user_id,
        enforce_budget=False,  # async job; capped by max_tokens per run
    )

    match = _JSON_RE.search(result.text)
    if not match:
        raise ValueError(f"extractor produced no JSON: {result.text[:200]!r}")
    payload = json.loads(match.group(0))

    created = 0
    for obs in payload.get("observations", [])[:MAX_OBSERVATIONS]:
        try:
            pattern_type = PatternType(obs["type"])
            text = str(obs["text"]).strip()[:500]
            confidence = max(0.0, min(1.0, float(obs.get("confidence", 0.0))))
            evidence = [
                uuid.UUID(ev) for ev in obs.get("evidence_ids", []) if str(ev) in session_msg_ids
            ]
        except (KeyError, ValueError):
            continue
        if not text or not evidence:
            # Provenance is mandatory (A2): no evidence => no pattern.
            continue
        db.add(
            Pattern(
                user_id=chat.user_id,
                type=pattern_type,
                text=text,
                status=PatternStatus.proposed,
                evidence_ids=evidence,
                confidence=confidence,
            )
        )
        created += 1

    summary = str(payload.get("session_summary", "")).strip()[:1000]
    if summary:
        chat.summary = summary
    db.flush()
    log.info("extractor_done", session_id=str(session_id), proposed=created)
    return created


def handle_job(session: Session, job) -> None:
    """Worker entry point (kind: pattern_extraction)."""
    extract_for_session(session, uuid.UUID(job.payload["session_id"]))
