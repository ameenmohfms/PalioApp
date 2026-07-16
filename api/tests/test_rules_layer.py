"""Unit tests for the deterministic Sentinel rules layer.

The full graded suite lives in /evals/cases and runs via test_eval_suite.py;
these are focused unit checks for normalization and the idiom guard.
"""

from palio.db.models import RiskLevel
from palio.safety import rules


def test_arabic_normalization():
    assert rules.normalize("أُريدُ") == "اريد"
    assert rules.normalize("مَدْرَسَةٌ") == "مدرسه"
    assert rules.normalize("HELLO") == "hello"


def test_l3_english_intent():
    assert rules.evaluate("I want to kill myself").level == RiskLevel.l3
    assert rules.evaluate("i'm going to end my life tonight").level == RiskLevel.l3


def test_l3_arabic_intent_with_diacritics_and_dialect():
    assert rules.evaluate("سَأَنْتَحِر").level == RiskLevel.l3
    assert rules.evaluate("ودي أنتحر").level == RiskLevel.l3
    assert rules.evaluate("راح أنهي حياتي").level == RiskLevel.l3


def test_l2_passive_ideation():
    assert rules.evaluate("sometimes I wish I was dead").level == RiskLevel.l2
    assert rules.evaluate("أتمنى أموت وأرتاح").level == RiskLevel.l2


def test_benign_idioms_stay_l0():
    for text in [
        "this project is killing me",
        "I'm dead tired after today",
        "المذاكرة بتقتلني والله",
        "أموت من الضحك على هذا المقطع",
        "الشغل يقتلني هالأسبوع",
    ]:
        result = rules.evaluate(text)
        assert result.level == RiskLevel.l0, f"{text!r} escalated: {result}"


def test_idiom_does_not_mask_real_risk():
    """A benign idiom in the same message must not strip a genuine signal."""
    text = "المذاكرة بتقتلني وصرت أفكر في الانتحار"
    assert rules.evaluate(text).level == RiskLevel.l2
