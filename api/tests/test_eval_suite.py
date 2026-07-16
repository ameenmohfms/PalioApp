"""CI-blocking safety eval runner (spec §13).

Loads /evals/cases/*.yaml and drives the Sentinel directly:
- pre-pass families run with a scripted L0 classifier so ONLY the
  deterministic rules layer decides — CI needs no API key, and the L3 gate
  ("L3 detection cases pass 100%") holds even with the classifier down.
- postpass families scan canned outbound drafts through the deterministic
  draft rules the same way.
- families marked requires_classifier are skipped here and run via
  evals/runner/run_live.py (needs ANTHROPIC_API_KEY).

Safety regressions in these families block merge.
"""

import json
from pathlib import Path

import pytest
import yaml

from palio.db.models import RiskLevel
from palio.llm import gateway
from palio.safety import sentinel
from palio.safety.sentinel import PostPassAction

CASES_DIR = Path(__file__).resolve().parents[2] / "evals" / "cases"
_ORDER = ["L0", "L1", "L2", "L3"]


def _families() -> list[dict]:
    families = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            families.append(yaml.safe_load(fh))
    assert families, f"no eval cases found in {CASES_DIR}"
    return families


def _ci_cases(kind: str) -> list[tuple[str, dict]]:
    out = []
    for family in _families():
        if family.get("requires_classifier"):
            continue
        if (family.get("type", "prepass")) != kind:
            continue
        for case in family["cases"]:
            out.append((f"{family['family']}::{case['id']}", case))
    return out


@pytest.fixture(autouse=True)
def _rules_only_sentinel():
    """Classifier and LLM post-check scripted to contribute nothing."""

    def responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": "L0", "rationale": "scripted neutral"})

    gateway.fake_registry.install("sentinel", responder)
    yield
    gateway.fake_registry.clear()


@pytest.mark.parametrize(
    ("case_id", "case"), _ci_cases("prepass"), ids=lambda p: p if isinstance(p, str) else ""
)
def test_prepass_case(case_id: str, case: dict):
    result = sentinel.pre_pass(case["input"])
    expect = case["expect"]

    if "level" in expect:
        assert result.level == RiskLevel(expect["level"]), (
            f"{case_id}: expected {expect['level']}, got {result.level} "
            f"(hits={result.rule_hits}, rationale={result.rationale})"
        )
    if "min_level" in expect:
        assert _ORDER.index(result.level.value) >= _ORDER.index(expect["min_level"]), case_id
    if "max_level" in expect:
        assert _ORDER.index(result.level.value) <= _ORDER.index(expect["max_level"]), case_id
    if expect.get("ui") == "crisis_screen":
        assert result.level == RiskLevel.l3, f"{case_id}: crisis screen requires L3"


@pytest.mark.parametrize(
    ("case_id", "case"), _ci_cases("postpass"), ids=lambda p: p if isinstance(p, str) else ""
)
def test_postpass_case(case_id: str, case: dict):
    result = sentinel.post_pass(case["draft"])
    expect = case["expect"]

    if expect.get("clean"):
        assert result.action == PostPassAction.ok, (
            f"{case_id}: allowed frame was flagged: {result.violations}"
        )
    else:
        assert result.action == PostPassAction.violation, f"{case_id}: violation not caught"
        wanted = expect["violation"]
        assert any(v.split(":")[0] == wanted for v in result.violations), (
            f"{case_id}: expected {wanted}, got {result.violations}"
        )


def test_l3_family_is_present_and_complete():
    """Guard against the L3 family being emptied or renamed."""
    l3 = [f for f in _families() if f["family"] == "l3_active_intent"]
    assert l3 and len(l3[0]["cases"]) >= 8
    assert l3[0]["ci_blocking"] is True
