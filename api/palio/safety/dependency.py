"""Dependency-signal heuristics (spec §5 A8 / §13 family 8).

Deterministic layer: exclusivity language and usage spikes. The Case Review
LLM lens interprets; this module only measures. On an exclusivity hit the
turn loop tells the companion to add a caring boundary + human-connection
nudge (never shaming)."""

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from palio.db.models import Message, MessageRole
from palio.safety.rules import normalize

EXCLUSIVITY_PATTERNS = [
    re.compile(p)
    for p in [
        r"\byou'?re\s+the\s+only\s+(?:one|person|friend)\s+i\s+(?:talk|speak)\s+to\b",
        r"\byou'?re\s+my\s+only\s+friend\b",
        r"\bi\s+(?:can\s+)?only\s+talk\s+to\s+you\b",
        r"\bi\s+don'?t\s+need\s+(?:anyone|people|humans)\s+(?:anymore|now)\b.{0,20}\byou\b|\byou\b.{0,30}\bdon'?t\s+need\s+(?:anyone|people)\s+anymore\b",
        # AR (normalized)
        r"انت الوحيد اللي اكلمه|انت الوحيد الذي اكلمه|انت الوحيده اللي اكلمها",
        r"ما عندي غيرك|ما لي غيرك|انت صديقي الوحيد|ما اقدر اكلم احد غيرك",
        r"ما عاد احتاج احد غيرك|استغنيت عن الناس",
    ]
]


def exclusivity_hit(text: str) -> bool:
    norm = normalize(text)
    return any(p.search(norm) for p in EXCLUSIVITY_PATTERNS)


def usage_spike(db: Session, user_id: uuid.UUID, factor: float = 2.5, floor: int = 40) -> bool:
    """True if the last 7 days' user messages exceed `factor` x the prior
    7 days AND at least `floor` messages — quiet users trying more isn't a
    spike."""
    now = datetime.now(UTC)

    def count(start, end) -> int:
        return db.execute(
            select(func.count(Message.id)).where(
                Message.user_id == user_id,
                Message.role == MessageRole.user,
                Message.created_at >= start,
                Message.created_at < end,
            )
        ).scalar_one()

    recent = count(now - timedelta(days=7), now)
    previous = count(now - timedelta(days=14), now - timedelta(days=7))
    if recent < floor:
        return False
    return recent >= factor * max(previous, 1)
