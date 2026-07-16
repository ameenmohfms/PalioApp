"""The Formulation template (spec §7) — the ONLY way screening results are
ever communicated to the user.

Section 3's honest line appears VERBATIM in every formulation, both
languages. Nothing here declares a diagnosis (N1); the eval family
postpass_banned_declarations plus test_formulation.py pin this.
"""

from dataclasses import dataclass, field

from palio.assessments.scoring import ScoreResult

# The honest line (§7.3) — verbatim, both languages. The [X] slot is filled
# with the condition the instrument screens for.
HONEST_LINE = {
    "en": (
        'This pattern is consistent with {condition}. Only a licensed clinician can '
        "diagnose — here's how to take the next step."
    ),
    "ar": (
        "هذا النمط يتوافق مع {condition}. التشخيص لا يتم إلا عبر طبيب مرخّص — "
        "وهذه هي الخطوة التالية."
    ),
}

CONDITION_NAMES = {
    "asrs_v1_1": {"en": "adult ADHD", "ar": "اضطراب فرط الحركة وتشتت الانتباه لدى البالغين"},
    "phq9": {"en": "depression", "ar": "أعراض اكتئابية"},
    "gad7": {"en": "generalized anxiety", "ar": "أعراض قلق عام"},
}

# Plain-language meaning per band (§7.2) — descriptive, never declarative.
BAND_MEANING_EN = {
    "positive": "your responses fall in the range where professional evaluation is warranted",
    "negative": "your responses fall below the screening threshold",
    "minimal": "your score is in the minimal range",
    "mild": "your score is in the mild range",
    "moderate": "your score is in the range where talking to a professional is recommended",
    "moderately_severe": (
        "your score is in the range where professional support is strongly recommended"
    ),
    "severe": "your score is in the range where professional support is strongly recommended",
}


@dataclass
class Formulation:
    """Structured §7 payload; the app renders sections in order."""

    reported_summary: str  # 1. plain-language mirror of key responses
    score_meaning: str  # 2. score + band with plain meaning
    honest_line: str  # 3. verbatim
    options: list[str] = field(default_factory=list)  # 4.
    rescreen_days: int = 0  # 5.
    scores: dict = field(default_factory=dict)
    band_key: str = ""
    band_label: str = ""
    alerts: list[str] = field(default_factory=list)


def _reported_summary(definition: dict, answers: dict[int, int], locale: str) -> str:
    """Mirror the 2–3 highest-rated items back in plain language (§7.1)."""
    top = sorted(answers.items(), key=lambda kv: kv[1], reverse=True)[:3]
    items_by_id = {item["id"]: item["text"] for item in definition["items"]}
    labels = {opt["value"]: opt["label"] for opt in definition["scale"]}
    parts = [f'"{items_by_id[i]}" — {labels[v]}' for i, v in top if v > 0]
    if not parts:
        return {
            "en": "You reported few or none of the experiences this screening asks about.",
            "ar": "أجبت بأن أغلب ما يسأل عنه هذا الفحص لا ينطبق عليك حالياً.",
        }[locale[:2] if locale[:2] in ("en", "ar") else "en"]
    intro = {
        "en": "The experiences you rated highest: ",
        "ar": "أكثر ما أشرت إلى تكراره: ",
    }[locale[:2] if locale[:2] in ("en", "ar") else "en"]
    return intro + "; ".join(parts)


def build(
    definition: dict,
    answers: dict[int, int],
    result: ScoreResult,
    locale: str = "en",
) -> Formulation:
    lang = locale[:2] if locale[:2] in ("en", "ar") else "en"
    key = definition["key"]
    condition = CONDITION_NAMES.get(key, {}).get(lang, key)

    meaning = BAND_MEANING_EN.get(result.band_key, result.band_label)
    if lang == "ar":
        meaning_map = {
            "positive": "إجاباتك ضمن النطاق الذي يُستحسن معه تقييم متخصص",
            "negative": "إجاباتك تحت عتبة هذا الفحص",
            "minimal": "نتيجتك ضمن النطاق البسيط",
            "mild": "نتيجتك ضمن النطاق الخفيف",
            "moderate": "نتيجتك ضمن نطاق يُنصح معه بالتحدث إلى مختص",
            "moderately_severe": "نتيجتك ضمن نطاق يُنصح معه بشدة بدعم متخصص",
            "severe": "نتيجتك ضمن نطاق يُنصح معه بشدة بدعم متخصص",
        }
        meaning = meaning_map.get(result.band_key, result.band_label)

    score_str = ", ".join(f"{k}: {v}" for k, v in result.scores.items())
    score_meaning = (
        f"{definition['title']} — {score_str}. {meaning}."
        if lang == "en"
        else f"{definition['title']} — {score_str}. {meaning}."
    )

    options = (
        [
            "generate_clinician_report",
            "see_referral_directory",
            "continue_with_strategies",
        ]
        if result.band_key not in ("negative", "minimal")
        else ["continue_with_strategies", "see_referral_directory"]
    )

    return Formulation(
        reported_summary=_reported_summary(definition, answers, lang),
        score_meaning=score_meaning,
        honest_line=HONEST_LINE[lang].format(condition=condition),
        options=options,
        rescreen_days=int(definition.get("recommended_rescreen_days", 28)),
        scores=result.scores,
        band_key=result.band_key,
        band_label=result.band_label,
        alerts=result.alerts,
    )
