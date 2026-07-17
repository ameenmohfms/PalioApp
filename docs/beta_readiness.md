# Beta readiness report (spec §12 Phase 7 deliverable)

Date: 2026-07-17 · Branch: `claude/palio-adhd-app-build-1b8kta`

## What ships

| Area | State |
|---|---|
| Safety spine | Sentinel pre/post-pass (rules + classifier, degraded mode), deterministic Crisis Protocol with golden-pinned script, N8 boot gate verified in Docker both directions |
| Conversation | Orchestrator turn loop, router (sticky assessment, coach), Companion + Coach agents, N7 minor gate, L2 check-in protocol, dependency-signal boundary nudge |
| Assessment | ASRS v1.1 / PHQ-9 / GAD-7 (EN verbatim, versioned), scoring engine tested on published vectors, Formulation with verbatim honest line, PHQ-9 item-9 escalation at answer time |
| Coaching | 10 bilingual strategies (signoff-flagged), assign→try→rate→adapt lifecycle, L1–L2 suppression |
| Memory | Pattern Extractor (evidence-mandatory, proposed-only), user confirmation queue, context packs (confirmed-only, token-capped), memory pause, hard-deletable nodes |
| Bridge to care | Structured (LLM-free) clinician PDF (AR RTL + EN) with disclaimer header, consent-gated; referral directory + tap metrics; full export; hard delete |
| Case Review | Four-lens weekly/post-intake/post-L2 job, support-plan upsert, operator flags to audit ledger, usage-spike + exclusivity heuristics |
| Ops | Docker Compose, CI (lint/type/tests incl. CI-blocking safety evals), token-gated operator metrics (success metrics only — no DAU/session-length), job retention purge |

## Eval & test status

- API: 190+ tests green, including the §13 CI-blocking families:
  L3 active intent (AR/EN/dialect, 100% on rules alone), L2 passive ideation, L0 hyperbole
  guard, N1/N3/N4 draft scans, prompt injection, dependency language, minor self-report.
- Golden crisis-script snapshots pinned (clinical re-review required to change).
- Live behavioral families (diagnosis-seeking, medication, jailbreak, sycophancy,
  undeliverable promises) run via `evals/runner/run_live.py` — require ANTHROPIC_API_KEY;
  **must be run and reviewed before beta** (no key available in the build environment).
- Load test (dev container, 2 uvicorn workers, degraded-sentinel hot path, 20 concurrent
  users × 3 turns): 60/60 ok, p50 225 ms, p95 988 ms, max 1.06 s. Re-run against staging
  with live models before beta: `evals/runner/load_test.py`.

## Blocking before beta (spec §16 — operator inputs)

1. 🔴 Verified crisis lines per launch country → production boot is impossible until then (by design).
2. 🔴 Clinically verified Arabic ASRS/PHQ-9/GAD-7 → Arabic screening disabled until then (by design).
3. 🔴 Clinical advisor sign-off: crisis script (golden files), minor-redirect script,
   formulation template, 10 strategies, psychoeducation content (directory currently empty
   — psychoeducation agent intentionally not enabled without content).
4. 🔴 Referral directory seed data (seeder refuses unverified entries).
5. 🔴 PDPL counsel review (see docs/pdpl_checklist.md).
6. 🔴 App-store wellness-category compliance review.

## Known gaps / deferred (logged in DECISIONS.md)

- Embedding-based pattern retrieval deferred (D32) — recency ranking in v1.
- Psychoeducation agent routes to companion until operator-approved `/content/psychoeducation`
  exists (A4 charter: no content file → no coverage claims).
- True token streaming deferred (D23) — server-side full generation + post-pass, streamed
  presentation.
- OTP email delivery: dev returns code in response; production requires operator SMTP wiring.
- Live-model latency targets (§5) are p95 targets with metrics, not yet measured in production.
