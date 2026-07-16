"""Formulation template (§7): honest line verbatim; never a diagnosis
declaration (N1) — every text field is scanned with the draft rules."""

import json
from pathlib import Path

import pytest

from palio.assessments import formulation, scoring
from palio.safety import post_rules

INSTRUMENTS = Path(__file__).resolve().parents[2] / "config" / "instruments"


def _load(name: str) -> dict:
    return json.loads((INSTRUMENTS / name).read_text(encoding="utf-8"))


ASRS = _load("asrs_v1_1.en.json")
PHQ9 = _load("phq9.en.json")


def _positive_asrs():
    answers = {item["id"]: 0 for item in ASRS["items"]}
    answers.update({1: 3, 2: 3, 3: 4, 4: 4, 5: 3, 6: 3})
    return answers


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_honest_line_verbatim(locale):
    answers = _positive_asrs()
    result = scoring.score(ASRS, answers)
    payload = formulation.build(ASRS, answers, result, locale=locale)
    condition = formulation.CONDITION_NAMES["asrs_v1_1"][locale]
    assert payload.honest_line == formulation.HONEST_LINE[locale].format(condition=condition)


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_formulation_never_declares_diagnosis(locale):
    """Every user-visible formulation string passes the N1/N3/N4 draft scan."""
    answers = _positive_asrs()
    result = scoring.score(ASRS, answers)
    payload = formulation.build(ASRS, answers, result, locale=locale)
    for text in (payload.reported_summary, payload.score_meaning, payload.honest_line):
        hits = post_rules.scan_draft(text)
        assert not hits, (locale, text, [h.id for h in hits])


def test_positive_band_offers_report_and_referrals():
    answers = _positive_asrs()
    payload = formulation.build(ASRS, answers, scoring.score(ASRS, answers), locale="en")
    assert "generate_clinician_report" in payload.options
    assert payload.rescreen_days == 56  # ASRS every 8 weeks (§7.5)


def test_minimal_band_skips_report_option():
    answers = {item["id"]: 0 for item in PHQ9["items"]}
    payload = formulation.build(PHQ9, answers, scoring.score(PHQ9, answers), locale="en")
    assert "generate_clinician_report" not in payload.options
    assert payload.rescreen_days == 14  # PHQ-9 every 2–4 weeks (§7.5)


def test_item9_alert_carried_into_formulation():
    answers = {item["id"]: 0 for item in PHQ9["items"]}
    answers[9] = 2
    payload = formulation.build(PHQ9, answers, scoring.score(PHQ9, answers), locale="en")
    assert "phq9_item9_positive" in payload.alerts
