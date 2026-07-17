"""Operator referral-directory seeder (spec §12 Phase 6, §16 #4).

Usage: python -m palio.admin.seed_referrals

Reads config/referral_directory.seed.json. Refuses to seed entries with an
empty verified_by or placeholder markers — the directory is real, verified
professionals or nothing.
"""

import json
import re
import sys
from pathlib import Path

from sqlalchemy import select

from palio.config import get_settings
from palio.db.base import db_session
from palio.db.models import ReferralEntry

_PLACEHOLDER_RE = re.compile(r"placeholder|changeme|todo|example", re.IGNORECASE)


def seed() -> int:
    path = Path(get_settings().config_dir) / "referral_directory.seed.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    seeded = 0
    with db_session() as db:
        for entry in entries:
            blob = json.dumps(entry, ensure_ascii=False)
            if _PLACEHOLDER_RE.search(blob) or not str(entry.get("verified_by", "")).strip():
                print(f"REFUSED (unverified/placeholder): {entry.get('name', '?')}",
                      file=sys.stderr)
                continue
            exists = db.execute(
                select(ReferralEntry).where(
                    ReferralEntry.name == entry["name"], ReferralEntry.city == entry["city"]
                )
            ).scalar_one_or_none()
            if exists:
                continue
            db.add(
                ReferralEntry(
                    name=entry["name"],
                    type=entry["type"],
                    city=entry["city"],
                    languages=entry.get("languages", []),
                    contact=entry["contact"],
                    telehealth=bool(entry.get("telehealth", False)),
                    verified_by=entry["verified_by"],
                )
            )
            seeded += 1
    print(f"seeded {seeded} referral entries")
    return seeded


if __name__ == "__main__":
    seed()
