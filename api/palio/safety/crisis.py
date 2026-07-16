"""Crisis Protocol (L3, spec §6).

At L3 every other agent is suspended and the reply is this DETERMINISTIC
script — no LLM generation at all, so the crisis path cannot hallucinate,
promise the undeliverable (N4), or drift from the reviewed text. Golden
snapshot tests in /evals/golden pin the script verbatim.

DRAFT STATUS: script text is written to spec (calm, direct, encourages
immediate human contact, no exploration of method/means) and requires
licensed clinical-advisor sign-off before beta (spec §16 #3).
"""

import uuid
from dataclasses import asdict, dataclass

from palio.audit.events import record_safety_event
from palio.db.models import RiskLevel
from palio.safety import crisis_config

# One product voice; honest about what Palio can and cannot do (N2, N4).
CRISIS_SCRIPT = {
    "ar": (
        "شكراً لأنك قلت هذا هنا. اللي تمرّ فيه الآن جدّي، وأنا آخذ كلامك على محمل الجد.\n\n"
        "أنا ذكاء اصطناعي، وما أقدر أتصل بأحد أو أرسل مساعدة — لكن في أشخاص حقيقيين "
        "يقدرون يساعدونك الآن.\n\n"
        "إذا كان فيه خطر مباشر على حياتك، اتصل بالطوارئ فوراً.\n"
        "وإذا تقدر، تواصل الآن مع أحد الأرقام الظاهرة على الشاشة، أو مع شخص تثق فيه "
        "وقريب منك — لا تبقَ وحدك الليلة.\n\n"
        "وجودك مهم. الخطوة الوحيدة المطلوبة منك الآن هي إنك تكلّم إنساناً يقدر يكون معك."
    ),
    "en": (
        "Thank you for saying this here. What you're going through is serious, and I'm "
        "taking your words seriously.\n\n"
        "I'm an AI — I can't call anyone or send help. But there are real people who can "
        "help you right now.\n\n"
        "If your life is in immediate danger, call emergency services now.\n"
        "If you can, reach one of the numbers on this screen, or someone you trust who is "
        "nearby — please don't stay alone tonight.\n\n"
        "You matter. The one step that matters right now is talking to a human who can be "
        "with you."
    ),
}


@dataclass
class CrisisPayload:
    script: str
    country: str
    lines: list[dict]
    verified: bool
    locale: str
    ui_action: str = "crisis_screen"  # app must render the full-screen crisis view


def trigger(
    *,
    locale: str = "ar",
    country: str = "SA",
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    trigger_detail: dict | None = None,
) -> CrisisPayload:
    """Run the Crisis Protocol: fixed script + operator-verified resources +
    append-only incident record. Callers must suspend all other agents."""
    resources = crisis_config.load(country)
    lines = [asdict(line) for line in resources.lines] if resources else []
    verified = bool(resources and resources.verified)

    record_safety_event(
        subject_id=user_id,
        session_id=session_id,
        event_type="crisis_protocol_triggered",
        risk_level=RiskLevel.l3,
        detail={"country": country, "resources_verified": verified, **(trigger_detail or {})},
    )

    lang = locale[:2] if locale[:2] in CRISIS_SCRIPT else "en"
    return CrisisPayload(
        script=CRISIS_SCRIPT[lang],
        country=country,
        lines=lines,
        verified=verified,
        locale=lang,
    )
