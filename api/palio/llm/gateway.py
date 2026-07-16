"""Single gateway for every model call in Palio (spec §5).

All agents go through `complete()`: retries, timeouts, per-user daily token
budgets, cost logging to llm_usage, and per-agent kill-switches live here
and only here. No other module may import the anthropic SDK.

Modes:
- live: real Anthropic API.
- fake: deterministic scripted responses for tests/evals (set
  PALIO_LLM_MODE=fake and register responders via `fake_registry`).
"""

import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from palio.config import get_settings

log = structlog.get_logger()

# Latency budgets from spec §5, treated as p95 targets (PLAN C3); the hard
# request timeout is deliberately looser so slow != silently skipped.
REQUEST_TIMEOUT_S = 30.0
MAX_RETRIES = 2
RETRY_BACKOFF_S = 1.0


class AgentDisabled(Exception):
    """Raised when the agent's kill-switch env var is set."""


class BudgetExceeded(Exception):
    """Raised when the user's daily token budget is exhausted."""


class LLMError(Exception):
    """Raised when the model call failed after retries."""


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class FakeRegistry:
    """agent -> responder(system, messages) -> str. Tests install responders."""

    responders: dict[str, Callable] = field(default_factory=dict)

    def install(self, agent: str, responder: Callable) -> None:
        self.responders[agent] = responder

    def clear(self) -> None:
        self.responders.clear()


fake_registry = FakeRegistry()

_KILL_FLAGS = {
    "companion": "palio_kill_companion",
    "assessment": "palio_kill_assessment",
    "psychoeducation": "palio_kill_psychoeducation",
    "coach": "palio_kill_coach",
    "pattern_extractor": "palio_kill_pattern_extractor",
    "case_review": "palio_kill_case_review",
    "reports": "palio_kill_reports",
    # The sentinel has NO kill-switch on purpose: guardrails always win
    # (Working Agreement 4). Router likewise cannot be disabled.
}


def _mode() -> str:
    return os.environ.get("PALIO_LLM_MODE", "live")


def _check_kill_switch(agent: str) -> None:
    flag = _KILL_FLAGS.get(agent)
    if flag and getattr(get_settings(), flag, False):
        raise AgentDisabled(f"agent '{agent}' is disabled by kill-switch")


def _log_usage(user_id: uuid.UUID | None, agent: str, result: LLMResult) -> None:
    """Append to the llm_usage cost ledger (spec §5). Best-effort: a ledger
    failure must never break the user's turn."""
    if user_id is None:
        return
    from palio.db.base import db_session
    from palio.db.models import LlmUsage

    try:
        with db_session() as session:
            session.add(
                LlmUsage(
                    user_id=user_id,
                    agent=agent,
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("llm_usage_log_failed", agent=agent, error=str(exc))


def check_budget(user_id: uuid.UUID | None) -> None:
    """Call before user-facing generations. Sentinel is exempt: safety
    classification must never be starved by a spent budget."""
    if user_id is None:
        return
    from sqlalchemy import func as safunc
    from sqlalchemy import select, text

    from palio.db.base import db_session
    from palio.db.models import LlmUsage

    settings = get_settings()
    with db_session() as session:
        used = session.execute(
            select(safunc.coalesce(safunc.sum(LlmUsage.input_tokens + LlmUsage.output_tokens), 0))
            .where(LlmUsage.user_id == user_id)
            .where(LlmUsage.created_at >= text("date_trunc('day', now())"))
        ).scalar_one()
    if used >= settings.palio_daily_token_budget_per_user:
        raise BudgetExceeded(f"daily token budget exhausted ({used} tokens)")


def complete(
    agent: str,
    *,
    system: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    user_id: uuid.UUID | None = None,
    enforce_budget: bool = True,
) -> LLMResult:
    """One completion. `messages` = [{"role": "user"|"assistant", "content": str}, ...]."""
    settings = get_settings()
    _check_kill_switch(agent)
    if enforce_budget:
        check_budget(user_id)

    resolved_model = model or settings.palio_model_main

    if _mode() == "fake":
        responder = fake_registry.responders.get(agent)
        if responder is None:
            raise LLMError(f"fake mode: no responder installed for agent '{agent}'")
        text_out = responder(system, messages)
        result = LLMResult(text=text_out, model=f"fake:{resolved_model}")
        _log_usage(user_id, agent, result)
        return result

    import anthropic

    if not settings.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY is not configured")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=REQUEST_TIMEOUT_S)
    last_err: Exception | None = None
    for attempt in range(1 + MAX_RETRIES):
        started = time.monotonic()
        try:
            resp = client.messages.create(
                model=resolved_model,
                system=system,
                messages=messages,  # type: ignore[arg-type]  # plain dicts are valid MessageParam
                max_tokens=max_tokens,
                temperature=temperature,
            )
            result = LLMResult(
                text="".join(b.text for b in resp.content if b.type == "text"),
                model=resolved_model,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            )
            log.info(
                "llm_call",
                agent=agent,
                model=resolved_model,
                ms=int((time.monotonic() - started) * 1000),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            _log_usage(user_id, agent, result)
            return result
        except anthropic.APIError as exc:
            last_err = exc
            log.warning("llm_retry", agent=agent, attempt=attempt, error=str(exc))
            time.sleep(RETRY_BACKOFF_S * (2**attempt))
    raise LLMError(f"model call failed for agent '{agent}': {last_err}")
