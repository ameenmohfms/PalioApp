"""N7: adults only. Deterministic detection of self-reported minority plus
the fixed supportive redirect. Once flagged, the user row is restricted and
every subsequent turn gets the redirect — no normal service resumes."""

import re

from palio.safety.rules import normalize

# Explicit self-reported age under 18 (EN + AR incl. Arabic-Indic digits),
# and common phrasings. Deliberately narrow: only first-person age claims.
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_EN_AGE = re.compile(r"\bi(?:'m| am)\s+(\d{1,2})(?:\s*years?\s*old|\s*yo\b|\s*,|\s*$|\s+and\b)")
_EN_AGE2 = re.compile(r"\b(\d{1,2})\s*years?\s*old\b.{0,12}\b(?:me|i am|i'm)\b")
_AR_AGE = re.compile(r"عمري\s*(\d{1,2})|انا\s*عندي\s*(\d{1,2})\s*سنه|عندي\s*(\d{1,2})\s*سنه")
_EN_SCHOOL = re.compile(r"\bi(?:'m| am)\s+(?:in\s+)?(?:middle\s+school|9th\s+grade|10th\s+grade)\b")
_AR_SCHOOL = re.compile(r"انا\s*(?:في|ب)\s*(?:المتوسط|متوسطه|اول ثانوي|ثاني متوسط|ثالث متوسط)")


def detects_minor(text: str) -> bool:
    norm = normalize(text).translate(_AR_DIGITS)
    for pattern in (_EN_AGE, _EN_AGE2, _AR_AGE):
        for match in pattern.finditer(norm):
            age = next((g for g in match.groups() if g), None)
            if age is not None and 5 <= int(age) < 18:
                return True
    return bool(_EN_SCHOOL.search(norm) or _AR_SCHOOL.search(norm))


# Fixed supportive redirect (deterministic; N7). Age-appropriate resources
# are a pointer to trusted adults + school/health services, not invented
# hotlines (Working Agreement 7).
MINOR_REDIRECT = {
    "ar": (
        "شكراً لصراحتك معي. باليو مصمّم للبالغين (١٨ سنة فأكثر)، ولذلك ما أقدر أكمل "
        "معك كالمعتاد — وهذا ليس رفضاً لك أبداً.\n\n"
        "اللي تمر فيه يستحق دعماً حقيقياً يناسب عمرك: كلّم شخصاً بالغاً تثق فيه — أحد "
        "الوالدين، مرشد المدرسة، أو طبيب العائلة. هم يقدرون يوصلونك للمساعدة الصحيحة.\n\n"
        "وإذا كنت في خطر الآن، اتصل بالطوارئ فوراً."
    ),
    "en": (
        "Thank you for being honest with me. Palio is built for adults (18+), so I can't "
        "continue as usual — and that is not a rejection of you.\n\n"
        "What you're going through deserves real support that fits your age: please talk "
        "to a trusted adult — a parent, a school counselor, or your family doctor. They "
        "can connect you to the right help.\n\n"
        "If you are in danger right now, call emergency services immediately."
    ),
}
