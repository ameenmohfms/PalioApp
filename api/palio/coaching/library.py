"""Strategy library loader (/content/strategies, spec §5 A5 charter).

The coach may only teach from these operator-approved files. A strategy the
library doesn't contain does not exist as far as the coach is concerned.
"""

import json
from functools import lru_cache
from pathlib import Path

from palio.config import get_settings

REQUIRED_FIELDS = {"key", "category", "en", "ar"}
LOCALE_FIELDS = {"title", "summary", "steps", "try_this_week", "adapt_if"}


class LibraryError(RuntimeError):
    pass


def _dir() -> Path:
    return Path(get_settings().content_dir) / "strategies"


@lru_cache(maxsize=1)
def load_all() -> dict[str, dict]:
    strategies: dict[str, dict] = {}
    for path in sorted(_dir().glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = REQUIRED_FIELDS - set(data)
        if missing:
            raise LibraryError(f"{path.name}: missing fields {sorted(missing)}")
        for lang in ("en", "ar"):
            locale_missing = LOCALE_FIELDS - set(data[lang])
            if locale_missing:
                raise LibraryError(f"{path.name}[{lang}]: missing {sorted(locale_missing)}")
        strategies[data["key"]] = data
    return strategies


def get(key: str) -> dict | None:
    return load_all().get(key)


def index(locale: str = "en") -> list[dict]:
    """Token-light listing for prompts and the Plan screen."""
    lang = locale[:2] if locale[:2] in ("en", "ar") else "en"
    return [
        {
            "key": s["key"],
            "category": s["category"],
            "title": s[lang]["title"],
            "summary": s[lang]["summary"],
        }
        for s in load_all().values()
    ]
