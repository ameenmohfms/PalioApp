"""Crisis-resource config loading + N8 startup validation.

Hard Rule N8: the app must refuse to ship with placeholder crisis values.
- production (APP_ENV=production or unset): any invalid file => boot fails.
- development/test: boot allowed ONLY with ALLOW_UNVERIFIED_CRISIS_CONFIG=1,
  and every payload is marked verified=false so the UI shows the dev banner.
Phone numbers are NEVER hardcoded in code or prompts (A5) — this module is
the only source of crisis resources.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from palio.config import Settings, get_settings

_PLACEHOLDER_RE = re.compile(r"placeholder|changeme|todo|xxx|fixme", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^\+?[0-9][0-9 \-]{1,18}$")


class CrisisConfigError(RuntimeError):
    """Raised when crisis config is missing/invalid and boot must stop (N8)."""


@dataclass
class CrisisLine:
    name: str
    number: str
    hours: str
    language: str


@dataclass
class CrisisResources:
    country: str
    lines: list[CrisisLine]
    updated_at: str | None
    verified_by: str
    verified: bool  # False only under the dev escape hatch


def _validate_file(path: Path) -> list[str]:
    """Return a list of problems; empty list = valid."""
    problems: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path.name}: unreadable ({exc})"]

    if not data.get("country"):
        problems.append(f"{path.name}: missing country")
    if not data.get("verified_by", "").strip():
        problems.append(f"{path.name}: verified_by is empty — operator verification required")
    if not data.get("updated_at"):
        problems.append(f"{path.name}: updated_at is empty")

    lines = data.get("lines") or []
    if not lines:
        problems.append(f"{path.name}: no crisis lines")
    for i, line in enumerate(lines):
        for key in ("name", "number", "hours", "language"):
            value = str(line.get(key, ""))
            if not value.strip():
                problems.append(f"{path.name}: lines[{i}].{key} is empty")
            elif _PLACEHOLDER_RE.search(value):
                problems.append(f"{path.name}: lines[{i}].{key} contains a placeholder value")
        number = str(line.get("number", ""))
        if number and not _PLACEHOLDER_RE.search(number) and not _NUMBER_RE.match(number):
            problems.append(f"{path.name}: lines[{i}].number is not a plausible phone number")

    for value in (str(data.get("verified_by", "")), str(data.get("country", ""))):
        if _PLACEHOLDER_RE.search(value):
            problems.append(f"{path.name}: placeholder in top-level fields")
    return problems


def _config_files(settings: Settings) -> list[Path]:
    return sorted(Path(settings.config_dir).glob("crisis_resources.*.json"))


def validate_at_boot(settings: Settings | None = None) -> bool:
    """N8 gate, called from the app factory. Returns True when resources are
    operator-verified; False when running on the dev escape hatch."""
    settings = settings or get_settings()
    files = _config_files(settings)

    problems: list[str] = [] if files else [f"no crisis_resources.*.json in {settings.config_dir}"]
    for path in files:
        problems.extend(_validate_file(path))

    if not problems:
        return True

    if settings.is_production or not settings.allow_unverified_crisis_config:
        raise CrisisConfigError(
            "REFUSING TO BOOT (Hard Rule N8) — crisis config invalid:\n  "
            + "\n  ".join(problems)
            + "\nOperator must supply verified crisis lines (spec §16 #1). "
            "For development only, set ALLOW_UNVERIFIED_CRISIS_CONFIG=1."
        )
    return False


def load(country: str, settings: Settings | None = None) -> CrisisResources | None:
    """Load resources for a country. verified=False when the file would not
    pass validation (possible only under the dev escape hatch)."""
    settings = settings or get_settings()
    path = Path(settings.config_dir) / f"crisis_resources.{country.lower()}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return CrisisResources(
        country=data.get("country", country.upper()),
        lines=[
            CrisisLine(
                name=str(line.get("name", "")),
                number=str(line.get("number", "")),
                hours=str(line.get("hours", "")),
                language=str(line.get("language", "")),
            )
            for line in data.get("lines", [])
        ],
        updated_at=data.get("updated_at"),
        verified_by=str(data.get("verified_by", "")),
        verified=not _validate_file(path),
    )
