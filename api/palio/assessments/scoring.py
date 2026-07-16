"""Scoring engine: official rules only, from the instrument definition.

Unit-tested against published scoring vectors (tests/test_scoring.py).
Never interprets — bands come verbatim from the definition; interpretation
belongs to the Formulation template alone (spec §7).
"""

from dataclasses import dataclass, field


class ScoringError(ValueError):
    pass


@dataclass
class ScoreResult:
    scores: dict = field(default_factory=dict)
    band_key: str = ""
    band_label: str = ""
    alerts: list[str] = field(default_factory=list)  # e.g. ["phq9_item9_positive"]


def _validate(definition: dict, answers: dict[int, int]) -> None:
    items = {item["id"] for item in definition["items"]}
    values = {opt["value"] for opt in definition["scale"]}
    missing = items - set(answers)
    if missing:
        raise ScoringError(f"missing answers for items: {sorted(missing)}")
    extra = set(answers) - items
    if extra:
        raise ScoringError(f"unknown item ids: {sorted(extra)}")
    bad = {k: v for k, v in answers.items() if v not in values}
    if bad:
        raise ScoringError(f"answer values outside the scale: {bad}")


def score(definition: dict, answers: dict[int, int]) -> ScoreResult:
    """answers: {item_id: scale_value}. Requires every item answered."""
    _validate(definition, answers)
    scoring = definition["scoring"]
    method = scoring["method"]

    if method == "sum":
        total = sum(answers.values())
        band = next(
            b for b in scoring["bands"] if b["min"] <= total <= b["max"]
        )
        alerts = [
            a["event"]
            for a in scoring.get("alerts", [])
            if answers.get(a["item"], 0) >= a["min_value"]
        ]
        return ScoreResult(
            scores={"total": total},
            band_key=band["key"],
            band_label=band["label"],
            alerts=alerts,
        )

    if method == "asrs":
        shaded_from = {int(k): v for k, v in scoring["shaded_from"].items()}
        shaded = {i for i, v in answers.items() if v >= shaded_from[i]}
        part_a = set(scoring["part_a_items"])
        part_a_shaded = len(shaded & part_a)
        part_b_shaded = len(shaded - part_a)
        positive = part_a_shaded >= scoring["part_a_positive_min"]
        band = scoring["bands"][1] if positive else scoring["bands"][0]
        return ScoreResult(
            scores={
                "part_a_shaded": part_a_shaded,
                "part_b_shaded": part_b_shaded,
                "total_shaded": part_a_shaded + part_b_shaded,
                "raw_total": sum(answers.values()),
            },
            band_key=band["key"],
            band_label=band["label"],
        )

    raise ScoringError(f"unknown scoring method: {method}")
