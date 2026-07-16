"""Golden-transcript snapshot tests for the crisis script (spec §13).

The crisis script is deterministic and clinically reviewed text (§16 #3).
Any change must be deliberate: update /evals/golden ONLY together with
clinical re-review, never to make a test pass.
"""

from pathlib import Path

from palio.safety import crisis

GOLDEN = Path(__file__).resolve().parents[2] / "evals" / "golden"


def test_crisis_script_matches_golden_snapshots():
    for lang, script in crisis.CRISIS_SCRIPT.items():
        golden = (GOLDEN / f"crisis_script.{lang}.txt").read_text(encoding="utf-8")
        assert script == golden, (
            f"crisis script ({lang}) diverged from the golden snapshot — "
            "this text requires clinical re-review before changing"
        )


def test_both_locales_have_snapshots():
    assert {p.name for p in GOLDEN.glob("crisis_script.*.txt")} == {
        "crisis_script.ar.txt",
        "crisis_script.en.txt",
    }
