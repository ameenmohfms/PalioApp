"""Sentinel Layer 1: deterministic multilingual rules (spec §6).

Design:
- Benign idioms are removed from the text FIRST, so "المذاكرة بتقتلني" or
  "this project is killing me" never reaches the risk patterns (false-alarm
  guard — false alarms drive away exactly the people who need the app).
- L3 patterns are an instant floor for unambiguous active intent; nuance is
  the classifier's job (Layer 2), never this file's.
- Arabic matching runs on normalized text (diacritics stripped, alef/ya
  unified) with MSA + Gulf/Egyptian dialect variants.

Every change to this file must keep the §13 eval suite green.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from palio.db.models import RiskLevel

# ── Normalization ─────────────────────────────────────────────────────────────

_AR_DIACRITICS = re.compile(r"[ً-ٰٟـ]")  # harakat, dagger alef, tatweel


def normalize(text: str) -> str:
    """Lowercase EN; strip Arabic diacritics/tatweel; unify alef/ya/waw-hamza."""
    text = unicodedata.normalize("NFC", text)
    text = _AR_DIACRITICS.sub("", text)
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
        .replace("ة", "ه")
    )
    return text.lower()


# ── Rule table ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Rule:
    id: str
    level: RiskLevel
    pattern: re.Pattern


def _r(rule_id: str, level: RiskLevel, pattern: str) -> Rule:
    return Rule(rule_id, level, re.compile(pattern))


# Benign idioms removed before risk matching. Patterns run on normalized text.
BENIGN_IDIOMS: list[re.Pattern] = [
    re.compile(p)
    for p in [
        # EN hyperbole
        r"\b(this|that|the)\s+[\w\s]{0,20}\b(is|was)\s+killing\s+me\b",
        r"\b(you'?re|he'?s|she'?s)\s+killing\s+(me|it)\b",
        r"\bkilled\s+it\b",
        r"\bdead\s+tired\b",
        r"\bdying\s+(of|from)\s+(laughter|boredom|hunger|embarrassment)\b",
        r"\bdying\s+to\s+(see|know|try|go|meet|hear|watch)\b",
        r"\bto\s+die\s+for\b",
        r"\bkills?\s+me\s+every\s+time\b",
        r"\bmy\s+feet\s+are\s+killing\s+me\b",
        # AR hyperbole (normalized): study/work/traffic "is killing me"
        r"(المذاكره|الدراسه|الشغل|الدوام|الواجب|الاختبار|الزحمه|الحرارة|الحراره|الجوع)\s*\S{0,12}\s*(بتقتلني|تقتلني|يقتلني|قتلتني|قتلني|ذبحني|ذبحتني|تذبحني)",
        r"(بتقتلني|تقتلني|يقتلني|قتلتني|ذبحني|ذبحتني)\s*(المذاكره|الدراسه|الشغل|الدوام|الواجب|الاختبار|الزحمه)",
        # dying of laughter / love it to death / dead tired (AR)
        r"(اموت|بموت|ميت|ميته|طحت)\s+من\s+(الضحك|التعب|الجوع|النعاس|الملل|الحر)",
        r"(اموت|بموت)\s+علي\s+\S+",  # "أموت على القهوة" = I love X
        r"(يقتلني|تقتلني|يذبحني)\s+(الضحك|الفضول)",
        r"(تعبان|طفشان|زهقان)\s+موت",
        r"ضحكت\s+لين\s+(مت|طحت)",
    ]
]

# L3 — unambiguous active intent / plan / in-progress emergency. Instant floor.
L3_RULES: list[Rule] = [
    # EN — active suicidal intent
    _r(
        "en_l3_kill_myself_intent",
        RiskLevel.l3,
        r"\bi\s*(?:want\s+to|wanna|am\s+going\s+to|'?m\s+going\s+to|(?:'?m\s+)?gonna|will|'?ll|"
        r"plan\s+to|am\s+about\s+to|'?m\s+about\s+to|(?:'?ve\s+|\s+have\s+)?decided\s+to)\s+"
        r"(?:kill\s+myself|end\s+my\s+life|end\s+it\s+all|take\s+my\s+(?:own\s+)?life)\b",
    ),
    _r("en_l3_kill_myself_now", RiskLevel.l3, r"\bkill(?:ing)?\s+myself\s+(?:tonight|today|now|this week)\b"),
    _r(
        "en_l3_plan",
        RiskLevel.l3,
        r"\bi\s+(?:have|'?ve\s+got|got|made)\s+(?:a\s+)?plan\s+to\s+(?:die|kill\s+myself|end\s+my\s+life)\b",
    ),
    _r("en_l3_jump", RiskLevel.l3, r"\bi'?\s*(?:am|m)?\s*going\s+to\s+jump\s+(?:off|from)\b"),
    _r(
        "en_l3_overdose_in_progress",
        RiskLevel.l3,
        r"\bi\s+(?:just\s+)?(?:took|swallowed)\s+(?:a\s+lot\s+of|too\s+many|all\s+(?:the|my))\s+(?:pills|tablets|medication)\b",
    ),
    _r(
        "en_l3_harm_others_means",
        RiskLevel.l3,
        r"\bi\s+bought\s+a\s+(?:gun|knife|weapon)\s+to\s+(?:kill|hurt|shoot|stab)\b",
    ),
    # AR (normalized) — سأنتحر and dialect variants
    _r(
        "ar_l3_suicide_intent",
        RiskLevel.l3,
        r"(ساانتحر|سانتحر|سوف انتحر|راح انتحر|رح انتحر|حانتحر|هانتحر|بنتحر الليله|"
        r"ابغي انتحر|ابغى انتحر|ابي انتحر|ودي انتحر|ناوي انتحر|ناويه انتحر|قررت انتحر|قررت الانتحار)",
    ),
    _r(
        "ar_l3_kill_self",
        RiskLevel.l3,
        r"(ساقتل نفسي|سوف اقتل نفسي|راح اقتل نفسي|رح اقتل نفسي|حقتل نفسي|هقتل نفسي|"
        r"بقتل نفسي|ابغي اقتل نفسي|ابغى اقتل نفسي|ابي اقتل نفسي|ودي اقتل نفسي|ناوي اقتل نفسي|قررت اقتل نفسي)",
    ),
    _r(
        "ar_l3_end_life",
        RiskLevel.l3,
        r"(سانهي حياتي|ساانهي حياتي|سوف انهي حياتي|راح انهي حياتي|رح انهي حياتي|بنهي حياتي|قررت انهي حياتي|هنهي حياتي)",
    ),
    _r(
        "ar_l3_overdose_in_progress",
        RiskLevel.l3,
        r"(بلعت|اخذت|شربت)\s+(كل|كميه كبيره من|علبه)\s*(الحبوب|حبوب|الادويه|دوا)",
    ),
]

# L2 — passive ideation, self-harm without plan, abuse disclosure.
L2_RULES: list[Rule] = [
    # EN passive ideation
    _r(
        "en_l2_wish_dead",
        RiskLevel.l2,
        r"\bi\s+(?:wish\s+i\s+(?:was|were)\s+dead|want\s+to\s+die|wanna\s+die|"
        r"don'?t\s+want\s+to\s+(?:live|be\s+alive|wake\s+up)(?:\s+anymore)?)\b",
    ),
    _r(
        "en_l2_better_off",
        RiskLevel.l2,
        r"\b(?:everyone\s+would\s+be\s+)?better\s+off\s+without\s+me\b|\bbetter\s+off\s+dead\b",
    ),
    _r(
        "en_l2_suicidal_thoughts",
        RiskLevel.l2,
        r"\b(?:think(?:ing)?\s+about\s+(?:suicide|ending\s+it|killing\s+myself)|suicidal\s+thoughts?)\b",
    ),
    _r(
        "en_l2_self_harm",
        RiskLevel.l2,
        r"\b(?:cut(?:ting)?\s+myself|hurt(?:ing)?\s+myself|harm(?:ing)?\s+myself|self[- ]harm)\b",
    ),
    _r("en_l2_no_reason_live", RiskLevel.l2, r"\b(?:no\s+reason\s+to\s+(?:live|go\s+on)|tired\s+of\s+living)\b"),
    _r(
        "en_l2_abuse",
        RiskLevel.l2,
        r"\b(?:my\s+(?:husband|wife|father|mother|brother|partner)\s+(?:hits|beats|hurts)\s+me|"
        r"i'?m\s+being\s+abused)\b",
    ),
    # AR (normalized) passive ideation
    _r(
        "ar_l2_wish_death",
        RiskLevel.l2,
        r"(اتمني اموت|اتمني الموت|ليتني اموت|ليتني ما كنت موجود|ودي اموت|ابغي اموت|ابغى اموت|"
        r"ابي اموت|نفسي اموت|يا ريت اموت|اتمني ما اصحي|ما ابغي اعيش|ما ابي اعيش|مو حاب اعيش|ما عاد ابي اعيش)",
    ),
    _r(
        "ar_l2_suicidal_thoughts",
        RiskLevel.l2,
        r"(افكر في الانتحار|افكر بالانتحار|تراودني افكار انتحاريه|افكار انتحاريه|جالي افكار انتحاريه|فكرت انتحر)",
    ),
    _r(
        "ar_l2_self_harm",
        RiskLevel.l2,
        r"(اجرح نفسي|جرحت نفسي|اذيت نفسي|اوذي نفسي|اضر نفسي|ضربت نفسي|احرق نفسي)",
    ),
    _r(
        "ar_l2_tired_of_life",
        RiskLevel.l2,
        r"(تعبت من الحياه|زهقت من حياتي|طفشت من حياتي|كرهت حياتي|ما في سبب اعيش|مليت من كل شي وابي اختفي)",
    ),
    _r(
        "ar_l2_abuse",
        RiskLevel.l2,
        r"(يضربني|تضربني|يعتدي علي|اتعرض للضرب|اتعرض للعنف|يوذيني جسديا)",
    ),
]


@dataclass
class RuleResult:
    level: RiskLevel
    hits: list[str] = field(default_factory=list)
    stripped_idioms: list[str] = field(default_factory=list)


def evaluate(text: str) -> RuleResult:
    """Run the deterministic layer. Returns the highest rule level (L0 if none)."""
    norm = normalize(text)

    stripped: list[str] = []
    for idiom in BENIGN_IDIOMS:
        norm, n = idiom.subn(" ", norm)
        if n:
            stripped.append(idiom.pattern)

    hits: list[str] = []
    level = RiskLevel.l0
    for rule in L3_RULES:
        if rule.pattern.search(norm):
            hits.append(rule.id)
            level = RiskLevel.l3
    if level != RiskLevel.l3:
        for rule in L2_RULES:
            if rule.pattern.search(norm):
                hits.append(rule.id)
                level = RiskLevel.l2

    return RuleResult(level=level, hits=hits, stripped_idioms=stripped)
