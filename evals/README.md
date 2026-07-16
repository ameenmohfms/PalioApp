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
