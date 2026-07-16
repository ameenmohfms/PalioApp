"""Scoring engine vs official scoring rules (Phase 3 gate)."""

import json
from pathlib import Path

import pytest

from palio.assessments import scoring

INSTRUMENTS = Path(__file__).resolve().parents[2] / "config" / "instruments"


def _load(name: str) -> dict:
    return json.loads((INSTRUMENTS / name).read_text(encoding="utf-8"))


PHQ9 = _load("phq9.en.json")
GAD7 = _load("gad7.en.json")
ASRS = _load("asrs_v1_1.en.json")


def _uniform(definition: dict, value: int) -> dict[int, int]:
    return {item["id"]: value for item in definition["items"]}


def _vector(definition: dict, values: list[int]) -> dict[int, int]:
    return {item["id"]: values[i] for i, item in enumerate(definition["items"])}


# ── PHQ-9 (Kroenke et al. 2001 bands) ────────────────────────────────────────


@pytest.mark.parametrize(
    ("values", "total", "band"),
    [
        ([0] * 9, 0, "minimal"),
        ([1, 1, 1, 1, 0, 0, 0, 0, 0], 4, "minimal"),
        ([1, 1, 1, 1, 1, 0, 0, 0, 0], 5, "mild"),
        ([1, 1, 1, 1, 1, 1, 1, 1, 1], 9, "mild"),
        ([2, 2, 2, 2, 2, 0, 0, 0, 0], 10, "moderate"),
        ([2, 2, 2, 2, 2, 2, 2, 0, 0], 14, "moderate"),
        ([2, 2, 2, 2, 2, 2, 2, 1, 0], 15, "moderately_severe"),
        ([3, 3, 3, 3, 3, 2, 1, 1, 0], 19, "moderately_severe"),
        ([3, 3, 3, 3, 3, 3, 2, 0, 0], 20, "severe"),
        ([3] * 9, 27, "severe"),
    ],
)
def test_phq9_bands(values, total, band):
    result = scoring.score(PHQ9, _vector(PHQ9, values))
    assert result.scores["total"] == total
    assert result.band_key == band


def test_phq9_item9_alert():
    answers = _uniform(PHQ9, 0)
    answers[9] = 1
    result = scoring.score(PHQ9, answers)
    assert result.alerts == ["phq9_item9_positive"]

    answers[9] = 0
    assert scoring.score(PHQ9, answers).alerts == []


# ── GAD-7 (Spitzer et al. 2006 bands) ────────────────────────────────────────


@pytest.mark.parametrize(
    ("values", "total", "band"),
    [
        ([0] * 7, 0, "minimal"),
        ([1, 1, 1, 1, 0, 0, 0], 4, "minimal"),
        ([1, 1, 1, 1, 1, 0, 0], 5, "mild"),
        ([2, 2, 2, 2, 1, 1, 0], 10, "moderate"),
        ([3, 3, 3, 2, 2, 1, 1], 15, "severe"),
        ([3] * 7, 21, "severe"),
    ],
)
def test_gad7_bands(values, total, band):
    result = scoring.score(GAD7, _vector(GAD7, values))
    assert result.scores["total"] == total
    assert result.band_key == band


# ── ASRS v1.1 (WHO Part A screen: ≥4 shaded of items 1–6) ────────────────────


def test_asrs_part_a_shading_thresholds():
    # Items 1–3 shade at "Sometimes" (2); items 4–6 shade at "Often" (3).
    answers = _uniform(ASRS, 0)
    answers.update({1: 2, 2: 2, 3: 2, 4: 3})
    result = scoring.score(ASRS, answers)
    assert result.scores["part_a_shaded"] == 4
    assert result.band_key == "positive"

    # "Sometimes" on item 4 is NOT shaded — screen stays negative.
    answers.update({4: 2})
    result = scoring.score(ASRS, answers)
    assert result.scores["part_a_shaded"] == 3
    assert result.band_key == "negative"


def test_asrs_part_b_counts_but_never_flips_screen():
    answers = _uniform(ASRS, 0)
    # Max out Part B only.
    for item in ASRS["items"]:
        if item["part"] == "B":
            answers[item["id"]] = 4
    result = scoring.score(ASRS, answers)
    assert result.scores["part_b_shaded"] == 12
    assert result.scores["part_a_shaded"] == 0
    assert result.band_key == "negative"


def test_asrs_all_very_often_is_positive_with_full_shading():
    result = scoring.score(ASRS, _uniform(ASRS, 4))
    assert result.scores["part_a_shaded"] == 6
    assert result.scores["total_shaded"] == 18
    assert result.band_key == "positive"


# ── Validation ───────────────────────────────────────────────────────────────


def test_missing_answers_rejected():
    with pytest.raises(scoring.ScoringError, match="missing answers"):
        scoring.score(PHQ9, {1: 1})


def test_out_of_scale_rejected():
    answers = _uniform(PHQ9, 0)
    answers[3] = 9
    with pytest.raises(scoring.ScoringError, match="outside the scale"):
        scoring.score(PHQ9, answers)
