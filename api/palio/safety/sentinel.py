"""The Safety Sentinel: pre-pass on every inbound message, post-pass on every
outbound draft (Hard Rule A1). Veto power over all agents; no kill-switch.

Pre-pass:  final level = max(rules, classifier); uncertainty resolves upward.
Degraded mode (D16): if the classifier fails, use the rules level, escalate
one step when any rule hit, and log a degraded-mode safety event.

Post-pass: deterministic N1/N3/N4 draft rules + LLM check (N1/N3/N4/N6);
violations => rewrite-once, then block with the locale's safe fallback.
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

import structlog

from palio.audit.events import record_safety_event
from palio.config import get_settings
from palio.db.models import RiskLevel
from palio.llm import gateway
from palio.safety import classifier, post_rules, rules

log = structlog.get_logger()

_ORDER = [RiskLevel.l0, RiskLevel.l1, RiskLevel.l2, RiskLevel.l3]


def _max_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _ORDER.index(a) >= _ORDER.index(b) else b


def _escalate(level: RiskLevel) -> RiskLevel:
    return _ORDER[min(_ORDER.index(level) + 1, len(_ORDER) - 1)]


# ── Pre-pass ──────────────────────────────────────────────────────────────────


@dataclass
class PrePassResult:
    level: RiskLevel
    rationale: str
    rule_hits: list[str] = field(default_factory=list)
    degraded: bool = False


def pre_pass(
    text: str,
    *,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> PrePassResult:
    rule_result = rules.evaluate(text)

    if rule_result.level == RiskLevel.l3:
        # Instant floor — no need to consult the classifier to act.
        result = PrePassResult(
            level=RiskLevel.l3,
            rationale=f"deterministic rule hit: {', '.join(rule_result.hits)}",
            rule_hits=rule_result.hits,
        )
    else:
        try:
            clf_level, clf_rationale = classifier.classify(text, user_id=user_id)
            result = PrePassResult(
                level=_max_level(rule_result.level, clf_level),
                rationale=clf_rationale
                if _ORDER.index(clf_level) >= _ORDER.index(rule_result.level)
                else f"rule hit: {', '.join(rule_result.hits)}",
                rule_hits=rule_result.hits,
            )
        except classifier.ClassifierError as exc:
            level: RiskLevel = rule_result.level
            if rule_result.hits:
                level = _escalate(level)
            result = PrePassResult(
                level=level,
                rationale=f"classifier degraded ({exc}); rules-only assessment",
                rule_hits=rule_result.hits,
                degraded=True,
            )
            record_safety_event(
                subject_id=user_id,
                session_id=session_id,
                event_type="sentinel_degraded",
                risk_level=level,
                detail={"rule_hits": rule_result.hits},
            )

    if result.level != RiskLevel.l0:
        record_safety_event(
            subject_id=user_id,
            session_id=session_id,
            event_type="risk_detected",
            risk_level=result.level,
            detail={"rule_hits": result.rule_hits, "degraded": result.degraded},
        )
    return result


# ── Post-pass ─────────────────────────────────────────────────────────────────


class PostPassAction(StrEnum):
    ok = "pass"
    violation = "violation"


@dataclass
class PostPassResult:
    action: PostPassAction
    violations: list[str] = field(default_factory=list)  # e.g. ["N1:n1_en_you_have", "N6"]


def _post_system() -> str:
    from palio.llm import prompts

    return prompts.load("sentinel_postcheck")

_POST_JSON_RE = re.compile(r'\{[^{}]*"violations"[^{}]*\}')


def _llm_post_check(draft: str, user_id: uuid.UUID | None) -> list[str]:
    settings = get_settings()
    result = gateway.complete(
        "sentinel",
        system=_post_system(),
        messages=[{"role": "user", "content": draft}],
        model=settings.palio_model_fast,
        max_tokens=100,
        temperature=0.0,
        user_id=user_id,
        enforce_budget=False,
    )
    match = _POST_JSON_RE.search(result.text)
    if not match:
        raise classifier.ClassifierError(f"unparseable post-check output: {result.text[:200]!r}")
    payload = json.loads(match.group(0))
    return [v for v in payload.get("violations", []) if v in {"N1", "N3", "N4", "N6"}]


def post_pass(
    draft: str,
    *,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> PostPassResult:
    violations = [f"{r.hard_rule}:{r.id}" for r in post_rules.scan_draft(draft)]

    try:
        violations += [v for v in _llm_post_check(draft, user_id) if v not in violations]
    except (classifier.ClassifierError, gateway.LLMError, json.JSONDecodeError) as exc:
        # Degraded post-check: deterministic rules still stand; log it.
        record_safety_event(
            subject_id=user_id,
            session_id=session_id,
            event_type="post_check_degraded",
            risk_level=None,
            detail={"error": str(exc)[:300]},
        )

    if violations:
        record_safety_event(
            subject_id=user_id,
            session_id=session_id,
            event_type="draft_blocked",
            risk_level=None,
            detail={"violations": violations},
        )
        return PostPassResult(PostPassAction.violation, violations)
    return PostPassResult(PostPassAction.ok)


# Safe fallbacks when a draft fails post-pass twice (rewrite exhausted).
SAFE_FALLBACK = {
    "ar": "أعتذر — ما قدرت أصيغ رد مناسب على هذا بشكل آمن. ممكن نعيد صياغة السؤال، "
    "وإذا كان عن التشخيص أو الأدوية فهذا شيء يحتاج طبيب مرخّص، وأقدر أساعدك تجهّز أسئلتك له.",
    "en": "I'm sorry — I couldn't put together a safe, helpful answer to that. Could we "
    "rephrase? If this is about diagnosis or medication, that belongs with a licensed "
    "clinician — I can help you prepare questions for that conversation.",
}


def enforce(
    draft: str,
    *,
    locale: str = "ar",
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    rewrite_fn=None,
) -> tuple[str, PostPassResult]:
    """pass / rewrite-once / safe-fallback pipeline for outbound drafts."""
    first = post_pass(draft, user_id=user_id, session_id=session_id)
    if first.action == PostPassAction.ok:
        return draft, first

    if rewrite_fn is not None:
        rewritten = rewrite_fn(draft, first.violations)
        second = post_pass(rewritten, user_id=user_id, session_id=session_id)
        if second.action == PostPassAction.ok:
            return rewritten, second

    fallback = SAFE_FALLBACK.get(locale[:2], SAFE_FALLBACK["en"])
    return fallback, first
