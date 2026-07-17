"""The per-message turn loop (spec §5 runtime topology).

user msg → Sentinel pre-pass → L3 ⇒ Crisis Protocol (all agents suspended)
        → minor gate (N7) → Router → primary agent draft
        → Sentinel post-pass (pass / rewrite-once / safe fallback) → reply

Every inbound message and every outbound reply is persisted with its risk
level and producing agent. Nothing reaches the user without the post-pass
(Hard Rule A1) except the two deterministic scripts (crisis, minor
redirect), which are fixed reviewed text pinned by tests.
"""

from dataclasses import dataclass, field

import structlog
from sqlalchemy.orm import Session

from palio.agents import coach, companion
from palio.audit.events import record_safety_event
from palio.db.models import (
    AgentRole,
    ChatSession,
    Message,
    MessageRole,
    RiskLevel,
    User,
)
from palio.jobs import queue
from palio.llm import gateway
from palio.orchestrator import minors, router
from palio.safety import crisis, dependency, sentinel

log = structlog.get_logger()

BUSY_FALLBACK = {
    "ar": "أعتذر، ما قدرت أرد الآن لضغط مؤقت في الخدمة. رسالتك محفوظة — جرب مرة ثانية بعد قليل.",
    "en": "Sorry — I couldn't reply just now due to a temporary service issue. Your message "
    "is saved; please try again in a moment.",
}

BUDGET_FALLBACK = {
    "ar": "وصلنا حد الاستخدام اليومي لهذا الحساب. نكمل بكرة؟ كلامك محفوظ وما راح يضيع.",
    "en": "We've reached today's usage limit for this account. Shall we continue tomorrow? "
    "Everything you wrote is saved.",
}


@dataclass
class TurnResult:
    reply: str
    risk_level: RiskLevel
    agent_role: AgentRole
    ui_action: str | None = None  # crisis_screen | show_resources | None
    crisis: dict | None = None
    violations: list[str] = field(default_factory=list)


def _persist(
    db: Session,
    chat: ChatSession,
    user: User,
    role: MessageRole,
    content: str,
    risk: RiskLevel | None,
    agent: AgentRole | None = None,
) -> Message:
    msg = Message(
        session_id=chat.id,
        user_id=user.id,
        role=role,
        content=content,
        risk_level=risk,
        agent_role=agent,
    )
    db.add(msg)
    db.flush()
    return msg


def _locale(user: User) -> str:
    return user.locale.value


def process_turn(db: Session, *, user: User, chat: ChatSession, text: str) -> TurnResult:
    # 1) Sentinel pre-pass on EVERY inbound message (A1).
    pre = sentinel.pre_pass(text, user_id=user.id, session_id=chat.id)
    _persist(db, chat, user, MessageRole.user, text, pre.level)

    # 2) Crisis Protocol at L3: everything else is suspended.
    if pre.level == RiskLevel.l3:
        payload = crisis.trigger(
            locale=_locale(user),
            country="SA",
            user_id=user.id,
            session_id=chat.id,
            trigger_detail={"rule_hits": pre.rule_hits, "degraded": pre.degraded},
        )
        _persist(
            db, chat, user, MessageRole.assistant, payload.script, RiskLevel.l3, AgentRole.crisis
        )
        return TurnResult(
            reply=payload.script,
            risk_level=RiskLevel.l3,
            agent_role=AgentRole.crisis,
            ui_action="crisis_screen",
            crisis={
                "lines": payload.lines,
                "verified": payload.verified,
                "country": payload.country,
            },
        )

    # 3) Minor gate (N7): fixed redirect, session restricted from now on.
    if user.restricted_minor or minors.detects_minor(text):
        if not user.restricted_minor:
            user.restricted_minor = True
            db.flush()
            record_safety_event(
                subject_id=user.id,
                session_id=chat.id,
                event_type="minor_redirect",
                risk_level=pre.level,
                detail={},
            )
        script = minors.MINOR_REDIRECT.get(_locale(user), minors.MINOR_REDIRECT["en"])
        _persist(db, chat, user, MessageRole.assistant, script, pre.level, AgentRole.companion)
        return TurnResult(reply=script, risk_level=pre.level, agent_role=AgentRole.companion)

    # 4) L2 check-in protocol: schedule Case Review, surface the resources screen.
    ui_action = None
    if pre.level == RiskLevel.l2:
        queue.enqueue(db, "case_review", {"user_id": str(user.id), "trigger": "l2_event"})
        ui_action = "show_resources"

    # 4b) Dependency signal (A8 engagement health): log it and have the
    #     companion respond with a caring boundary + human-connection nudge.
    dependency_note = False
    if dependency.exclusivity_hit(text):
        dependency_note = True
        record_safety_event(
            subject_id=user.id,
            session_id=chat.id,
            event_type="dependency_signal",
            risk_level=pre.level,
            detail={"kind": "exclusivity_language"},
        )

    # 5) Route to the primary role. Coach suppression (A5 charter): a user
    #    flagged L1–L2 this turn gets the companion, never productivity push.
    role = router.route(text, user_id=user.id)
    if role == router.Role.coach and pre.level in (RiskLevel.l1, RiskLevel.l2):
        role = router.Role.companion
        record_safety_event(
            subject_id=user.id,
            session_id=chat.id,
            event_type="coach_suppressed",
            risk_level=pre.level,
            detail={},
        )

    agents = {
        router.Role.companion: (companion.generate, companion.rewrite, AgentRole.companion),
        router.Role.coach: (coach.generate, coach.rewrite, AgentRole.coach),
    }
    generate_fn, rewrite_fn, agent_role = agents.get(role, agents[router.Role.companion])

    # 6) Generate + 7) post-pass enforce (pass / rewrite-once / fallback).
    locale = _locale(user)
    try:
        draft = generate_fn(
            db,
            user=user,
            chat=chat,
            user_text=text,
            risk_level=pre.level,
            dependency_note=dependency_note,
        )
        final, post = sentinel.enforce(
            draft,
            locale=locale,
            user_id=user.id,
            session_id=chat.id,
            rewrite_fn=lambda d, v: rewrite_fn(d, v, user_id=user.id),
        )
        violations = post.violations
    except gateway.BudgetExceeded:
        final, violations = BUDGET_FALLBACK.get(locale, BUDGET_FALLBACK["en"]), []
    except (gateway.AgentDisabled, gateway.LLMError) as exc:
        log.error("turn_generation_failed", error=str(exc), agent=role.value)
        final, violations = BUSY_FALLBACK.get(locale, BUSY_FALLBACK["en"]), []

    _persist(db, chat, user, MessageRole.assistant, final, pre.level, agent_role)
    return TurnResult(
        reply=final,
        risk_level=pre.level,
        agent_role=agent_role,
        ui_action=ui_action,
        violations=violations,
    )
