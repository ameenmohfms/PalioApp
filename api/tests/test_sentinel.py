"""Sentinel pre/post-pass behavior with scripted fake classifier responses."""

import json

import pytest

from palio.db.models import RiskLevel
from palio.llm import gateway
from palio.safety import crisis, sentinel
from palio.safety.sentinel import PostPassAction


@pytest.fixture(autouse=True)
def _clean_fakes():
    yield
    gateway.fake_registry.clear()


def _install_classifier(level: str = "L0", rationale: str = "scripted"):
    def responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": []})
        return json.dumps({"level": level, "rationale": rationale})

    gateway.fake_registry.install("sentinel", responder)


def _install_post_check(violations: list[str]):
    def responder(system, messages):
        if "violations" in system:
            return json.dumps({"violations": violations})
        return json.dumps({"level": "L0", "rationale": "scripted"})

    gateway.fake_registry.install("sentinel", responder)


# ── pre-pass ──────────────────────────────────────────────────────────────────


def test_rules_l3_short_circuits_classifier():
    # No responder installed: if the classifier were consulted, this would raise.
    result = sentinel.pre_pass("I want to kill myself")
    assert result.level == RiskLevel.l3
    assert result.rule_hits


def test_final_level_is_max_of_rules_and_classifier():
    _install_classifier("L1", "distress tone")
    result = sentinel.pre_pass("أتمنى أموت")  # rules say L2, classifier says L1
    assert result.level == RiskLevel.l2

    _install_classifier("L2", "passive ideation phrased without keywords")
    result = sentinel.pre_pass("ما عاد فيني أكمل، ودي أختفي للأبد")
    assert result.level == RiskLevel.l2  # classifier raises rules' L0


def test_classifier_cannot_lower_rules_level():
    _install_classifier("L0", "looks fine to me")
    result = sentinel.pre_pass("I keep thinking about suicide")
    assert result.level == RiskLevel.l2


def test_degraded_mode_escalates_rule_hits():
    # No fake responder installed => ClassifierError => degraded path.
    result = sentinel.pre_pass("sometimes I wish I was dead")
    assert result.degraded is True
    assert result.level == RiskLevel.l3  # L2 rule hit escalated one level


def test_degraded_mode_without_hits_stays_l0():
    result = sentinel.pre_pass("today was actually a good day")
    assert result.degraded is True
    assert result.level == RiskLevel.l0


# ── post-pass ─────────────────────────────────────────────────────────────────


def test_post_pass_blocks_diagnosis_declaration():
    _install_classifier()
    for draft in [
        "Based on everything you've told me, you have ADHD.",
        "من الواضح أنك تعاني من اضطراب فرط الحركة وتشتت الانتباه.",
        "عندك اكتئاب وتحتاج علاج.",
    ]:
        result = sentinel.post_pass(draft)
        assert result.action == PostPassAction.violation, draft
        assert any(v.startswith("N1") for v in result.violations), result.violations


def test_post_pass_allows_honest_formulation_frame():
    _install_classifier()
    for draft in [
        "Your responses show a pattern consistent with adult ADHD. Only a licensed "
        "clinician can diagnose — here's how to take the next step.",
        "إجاباتك تُظهر نمطاً يتوافق مع فرط الحركة وتشتت الانتباه عند البالغين. "
        "التشخيص لا يتم إلا عبر طبيب مرخّص — وأقدر أساعدك في الخطوة الجاية.",
    ]:
        result = sentinel.post_pass(draft)
        assert result.action == PostPassAction.ok, (draft, result.violations)


def test_post_pass_blocks_medication_advice():
    _install_classifier()
    result = sentinel.post_pass("You could try taking Ritalin, start with a low dose of 10 mg.")
    assert result.action == PostPassAction.violation
    assert any(v.startswith("N3") for v in result.violations)


def test_post_pass_blocks_undeliverable_promise():
    _install_classifier()
    result = sentinel.post_pass("Don't worry — I will call emergency services for you right now.")
    assert result.action == PostPassAction.violation
    assert any(v.startswith("N4") for v in result.violations)


def test_post_pass_llm_flags_sycophancy():
    _install_post_check(["N6"])
    result = sentinel.post_pass("You're right, therapy is pointless for someone like you.")
    assert result.action == PostPassAction.violation
    assert "N6" in result.violations


def test_enforce_rewrite_once_then_fallback():
    _install_classifier()

    def bad_rewrite(draft, violations):
        return draft  # rewrite fails to fix anything

    final, result = sentinel.enforce(
        "You have ADHD.", locale="en", rewrite_fn=bad_rewrite
    )
    assert final == sentinel.SAFE_FALLBACK["en"]

    def good_rewrite(draft, violations):
        return "This pattern is consistent with ADHD; only a licensed clinician can diagnose."

    final, result = sentinel.enforce("You have ADHD.", locale="en", rewrite_fn=good_rewrite)
    assert "consistent with" in final


# ── crisis protocol ───────────────────────────────────────────────────────────


def test_crisis_payload_is_deterministic_and_honest():
    payload = crisis.trigger(locale="ar", country="SA")
    assert payload.ui_action == "crisis_screen"
    assert payload.script == crisis.CRISIS_SCRIPT["ar"]
    # N2/N4: the script must disclose AI and never promise to call anyone.
    assert "ذكاء اصطناعي" in payload.script
    assert "ما أقدر أتصل" in payload.script
    # Repo config is a placeholder => resources must be marked unverified.
    assert payload.verified is False


def test_crisis_script_never_promises_contact():
    from palio.safety import post_rules

    for lang, script in crisis.CRISIS_SCRIPT.items():
        n4_hits = [r.id for r in post_rules.scan_draft(script) if r.hard_rule == "N4"]
        assert not n4_hits, (lang, n4_hits)
