"""Instrument loading + DB sync.

Instruments live as versioned JSON files in /config/instruments (Hard Rule
A3: item text renders verbatim from these files, never paraphrased). At
boot they are upserted into screener_instruments so results can reference
a stable instrument row. placeholder=true files (unverified Arabic, spec
§16 #2) are synced but never offered to users.
"""

import json
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from palio.config import get_settings
from palio.db.models import Locale, ScreenerInstrument

log = structlog.get_logger()

VALID_KEYS = {"asrs_v1_1", "phq9", "gad7"}


def instrument_files() -> list[Path]:
    return sorted((Path(get_settings().config_dir) / "instruments").glob("*.json"))


def load_definitions() -> list[dict]:
    defs = []
    for path in instrument_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("key") not in VALID_KEYS:
            continue
        defs.append(data)
    return defs


def sync_to_db(session: Session) -> int:
    """Idempotent upsert of instrument files into screener_instruments."""
    count = 0
    for data in load_definitions():
        existing = session.execute(
            select(ScreenerInstrument).where(
                ScreenerInstrument.key == data["key"],
                ScreenerInstrument.version == data["version"],
                ScreenerInstrument.language == Locale(data["language"]),
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ScreenerInstrument(
                    key=data["key"],
                    version=data["version"],
                    language=Locale(data["language"]),
                    definition=data,
                    source=data.get("source", ""),
                    placeholder=bool(data.get("placeholder", False)),
                )
            )
            count += 1
        else:
            existing.definition = data
            existing.source = data.get("source", "")
            existing.placeholder = bool(data.get("placeholder", False))
    session.flush()
    return count


def offered(session: Session) -> list[ScreenerInstrument]:
    """Instruments users may take: never placeholders (A3 / §16 #2)."""
    return list(
        session.execute(
            select(ScreenerInstrument).where(~ScreenerInstrument.placeholder)
        ).scalars()
    )
