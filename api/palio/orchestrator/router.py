"""Router: picks the one primary role per turn (spec §5). Haiku structured
output; sticky assessment mode; falls back to companion on any failure —
routing must never take down a turn."""

import json
import re
import uuid
from enum import StrEnum

import structlog

from palio.config import get_settings
from palio.llm import gateway, prompts

log = structlog.get_logger()


class Role(StrEnum):
    companion = "companion"
    assessment = "assessment"
    psychoeducation = "psychoeducation"
    coach = "coach"


_JSON_RE = re.compile(r'\{[^{}]*"role"[^{}]*\}')

# Roles whose agents exist yet. Later phases extend this; routing to an
# unimplemented role falls back to companion (which explains what it can do).
IMPLEMENTED: set[Role] = {Role.companion}


def route(
    text: str,
    *,
    assessment_active: bool = False,
    user_id: uuid.UUID | None = None,
) -> Role:
    if assessment_active:
        return Role.assessment if Role.assessment in IMPLEMENTED else Role.companion
    try:
        result = gateway.complete(
            "router",
            system=prompts.load("router"),
            messages=[
                {
                    "role": "user",
                    "content": f'state: {{"assessment_active": '
                    f"{str(assessment_active).lower()}}}\n"
                    f"message: {text}",
                }
            ],
            model=get_settings().palio_model_fast,
            max_tokens=80,
            temperature=0.0,
            user_id=user_id,
            enforce_budget=False,
        )
        match = _JSON_RE.search(result.text)
        role = Role(json.loads(match.group(0))["role"]) if match else Role.companion
    except (gateway.LLMError, ValueError, KeyError, json.JSONDecodeError) as exc:
        log.warning("router_fallback", error=str(exc))
        role = Role.companion
    return role if role in IMPLEMENTED else Role.companion
