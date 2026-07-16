"""Deterministic post-pass checks on OUTBOUND drafts (Hard Rules N1/N3/N4).

These regexes scan what Palio is about to say, not what the user said.
The allowed formulation frame — "pattern consistent with X; only a licensed
clinician can diagnose" — does not match any banned pattern by design.
N6 (sycophancy) has no reliable regex shape; the LLM post-check covers it.
"""

import re
from dataclasses import dataclass

from palio.safety.rules import normalize

_DISORDERS_EN = r"(?:adhd|add|attention\s+deficit|depression|anxiety\s+disorder|bipolar|ocd|autism|asd)"
_DISORDERS_AR = (
    r"(?:اضطراب(?:\s+\S+){0,3}|فرط الحركه(?:\s+وتشتت الانتباه)?|تشتت الانتباه|"
    r"الاكتياب|اكتياب|القلق المرضي|ثنايي القطب|الوسواس القهري|التوحد)"
)

_MEDS = (
    r"(?:ritalin|concerta|adderall|strattera|vyvanse|elvanse|dexamphetamine|atomoxetine|"
    r"prozac|zoloft|lexapro|ssri|ريتالين|كونسيرتا|اديرال|ادرال|ستراتيرا|فيفانس|اتوموكسيتين|بروزاك|زولوفت)"
)


@dataclass(frozen=True)
class DraftRule:
    id: str
    hard_rule: str  # N1 | N3 | N4
    pattern: re.Pattern


def _r(rule_id: str, hard_rule: str, pattern: str) -> DraftRule:
    return DraftRule(rule_id, hard_rule, re.compile(pattern))


DRAFT_RULES: list[DraftRule] = [
    # ── N1: diagnosis declarations ───────────────────────────────────────────
    _r(
        "n1_en_you_have",
        "N1",
        rf"\byou\s+(?:have|definitely\s+have|clearly\s+have|do\s+have|are\s+suffering\s+from|suffer\s+from)\s+{_DISORDERS_EN}\b",
    ),
    _r("n1_en_you_are", "N1", r"\byou\s+are\s+(?:adhd|autistic|bipolar|clinically\s+depressed)\b"),
    _r(
        "n1_en_diagnose",
        "N1",
        r"\b(?:i\s+(?:can\s+)?diagnose\s+you|your\s+diagnosis\s+is|diagnosing\s+you\s+with)\b",
    ),
    _r("n1_ar_you_have", "N1", rf"(?:انت مصاب ب|انت تعاني من|تعاني من)\s*{_DISORDERS_AR}"),
    _r("n1_ar_you_have2", "N1", rf"(?:عندك|لديك)\s+{_DISORDERS_AR}"),
    _r("n1_ar_diagnosis", "N1", r"(?:تشخيصك هو|اشخصك|اقدر اشخصك|هذا تشخيص)"),
    # ── N3: medication advice ────────────────────────────────────────────────
    _r(
        "n3_en_med_verbs",
        "N3",
        rf"\b(?:tak(?:e|ing)|start(?:ing)?|stop(?:ping)?|try(?:\s+taking)?|increas(?:e|ing)|"
        rf"decreas(?:e|ing)|doubl(?:e|ing)|switch(?:ing)?\s+to)\s+"
        rf"(?:some\s+|your\s+|the\s+)?{_MEDS}",
    ),
    _r("n3_en_dose", "N3", r"\b(?:dose|dosage)\s+(?:of|for)\b|\b\d+\s*mg\b"),
    _r(
        "n3_ar_med_verbs",
        "N3",
        rf"(?:خذ|تناول|جرب|ابدا ب?|اوقف|زد|قلل|ضاعف)\s*(?:جرعه|الجرعه)?\s*{_MEDS}",
    ),
    _r(
        "n3_ar_dose_change",
        "N3",
        r"(?:زد|قلل|ضاعف|خفف|خفض|وقف|اوقف)\s+(?:الجرعه|جرعه|جرعتك|الدواء|دواك)",
    ),
    _r("n3_ar_dose", "N3", r"(?:جرعه|الجرعه)\s+(?:من|ال)|[0-9٠-٩]+\s*(?:ملجم|ملغ|مجم)"),
    # ── N4: undeliverable promises ───────────────────────────────────────────
    _r(
        "n4_en_promise",
        "N4",
        r"\bi\s*(?:will|'?ll|can|am\s+going\s+to|'?ve|have)\s+(?:call(?:ed)?|contact(?:ed)?|"
        r"notif(?:y|ied)|alert(?:ed)?|reach(?:ed)?\s+out\s+to)\s+(?:the\s+)?(?:police|emergency|"
        r"ambulance|a\s+doctor|someone|your\s+family|authorities|a\s+hotline)\b",
    ),
    _r(
        "n4_en_guarantee",
        "N4",
        r"\b(?:i\s+guarantee|we\s+guarantee)\s+(?:your\s+)?(?:confidentiality|that\s+the\s+hotline)\b",
    ),
    # NOTE: patterns are written in NORMALIZED form (see rules.normalize):
    # ئ→ي so "الطوارئ" is matched as "الطواري".
    _r(
        "n4_ar_promise",
        "N4",
        r"(?:ساتصل|سوف اتصل|راح اتصل|رح اتصل|باتصل|اتصلت|سابلغ|بلغت|راح ابلغ|سوف ابلغ)"
        r"\s*(?:ب|لل)?(?:ال)?(?:شرطه|طواري|اسعاف|طبيب|اهلك|احد|جهات|خط)",
    ),
    _r("n4_ar_guarantee", "N4", r"(?:اضمن لك|نضمن)\s*(?:السريه|سريه تامه|ان الخط سري)"),
]


def scan_draft(draft: str) -> list[DraftRule]:
    """Return every deterministic draft rule the text violates."""
    norm = normalize(draft)
    return [rule for rule in DRAFT_RULES if rule.pattern.search(norm)]
