# Evaluation harness (spec §13)

First-class safety infrastructure, built in Phase 1:

- `cases/` — YAML case families (≥8 cases each, AR + EN incl. Gulf dialect variants):
  L3 crisis, L2 passive ideation, L0 hyperbole guard, diagnosis-seeking, medication
  questions, jailbreaks, sycophancy probes, dependency language, self-reported minor,
  undeliverable promises, prompt injection, formulation-output scanning.
- `golden/` — snapshot transcripts for the crisis script.
- `runner/` — drives the orchestrator in test mode; asserts on risk level, forbidden
  content (regex + LLM judge), and UI-trigger flags.

Wired into CI: **safety regressions block merge**. L3 detection must pass 100%.

## How the suite splits

- **CI-blocking (keyless)** — run by `api/tests/test_eval_suite.py` with the classifier
  scripted to L0, so only the deterministic layers decide: L3 intent, L2 passive
  ideation, L0 hyperbole guard, N1/N3/N4 draft scans, prompt injection, dependency
  language, minor self-report.
- **Live classifier families** (`requires_classifier: true`, type prepass) — nuanced
  keyword-free phrasings; run: `.venv/bin/python ../evals/runner/run_live.py`.
- **Live behavioral families** (`behavioral_live.yaml`) — full turns through the
  orchestrator (diagnosis-seeking, medication, jailbreak, sycophancy, undeliverable
  promises); run: `run_live.py --behavioral`. Required before beta.
- **Load test** — `runner/load_test.py` against a staging deployment.
