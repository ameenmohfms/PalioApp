"""Sentinel Layer 2: LLM risk classifier (fast model, spec §6).

Returns {level, rationale}. Calibration is bidirectional: distinguish
genuine signals from idiom/hyperbole, and choose the HIGHER level when
uncertain between two. The classifier can only raise the rules layer's
level, never lower it (final = max(rules, classifier))."""

import json
import re
import uuid

import structlog

from palio.config import get_settings
from palio.db.models import RiskLevel
from palio.llm import gateway

log = structlog.get_logger()

def _system() -> str:
    from palio.llm import prompts

    return prompts.load("sentinel_classifier")

_LEVELS = {level.value: level for level in RiskLevel}
_JSON_RE = re.compile(r'\{[^{}]*"level"[^{}]*\}')


class ClassifierError(Exception):
    pass


def classify(text: str, user_id: uuid.UUID | None = None) -> tuple[RiskLevel, str]:
    """Classify one inbound message. Raises ClassifierError on failure —
    the sentinel catches it and applies the degraded-mode policy (D16)."""
    settings = get_settings()
    try:
        result = gateway.complete(
            "sentinel",
            system=_system(),
            messages=[{"role": "user", "content": text}],
            model=settings.palio_model_fast,
            max_tokens=150,
            temperature=0.0,
            user_id=user_id,
            enforce_budget=False,  # safety classification is never budget-starved
        )
    except gateway.LLMError as exc:
        raise ClassifierError(str(exc)) from exc

    match = _JSON_RE.search(result.text)
    if not match:
        raise ClassifierError(f"unparseable classifier output: {result.text[:200]!r}")
    try:
        payload = json.loads(match.group(0))
        level = _LEVELS[payload["level"].strip().upper()]
        rationale = str(payload.get("rationale", ""))[:300]
    except (json.JSONDecodeError, KeyError, AttributeError) as exc:
        raise ClassifierError(f"invalid classifier payload: {result.text[:200]!r}") from exc
    return level, rationale
