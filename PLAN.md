# PLAN.md — Palio MVP Build Plan

> Status: **awaiting operator approval**. Per the master build prompt (§17), no application
> code will be written until this plan is approved.

---

## 1. Mission Restatement

Palio is an Arabic-first, text-first mobile app for adults (18+) dealing with ADHD and
executive-function struggles. It does four things:

1. **Screens** — administers validated instruments (ASRS v1.1, PHQ-9, GAD-7) verbatim,
   scores them by official rules, and communicates results only through the Formulation
   template, which always says a pattern is *consistent with* a condition and that only a
   licensed clinician can diagnose.
2. **Educates** — psychoeducation from operator-approved content only.
3. **Supports** — evidence-informed executive-function and CBT/ACT-informed coaching, one
   strategy at a time, with feedback loops; plus a user-confirmed patterns-and-progress map.
4. **Refers** — clinician-ready report exports and an operator-verified referral directory.

**Palio never diagnoses, never prescribes, never pretends to be human or a clinician, and
never uses engagement dark patterns.** It speaks with exactly one product voice; the
multi-agent system (orchestrator-worker) is invisible internal machinery. A Safety Sentinel
inspects every inbound message and every outbound draft; guardrails always win over
features. Success is measured by validated-scale improvement, screener completion,
report exports, and referral events — never session length or DAU.

### Hard Rules (restated, binding on all code/prompts/evals)

**NEVER:**
- **N1** — state/imply a diagnosis ("you have / تعاني من + disorder" banned; "pattern
  consistent with X — only a clinician can diagnose" is the only allowed frame).
- **N2** — present any agent as human or credentialed; AI disclosure at first run + Settings.
- **N3** — medication advice of any kind; redirect to prescriber conversation + log event.
- **N4** — promise undeliverable actions (calling someone, alerting authorities,
  guaranteeing external confidentiality).
- **N5** — dark patterns: no streaks, guilt, loss-framing, urgency; max 1 user-configured
  check-in notification/day.
- **N6** — sycophantic validation of harm, care-avoidance, or distorted self-beliefs.
- **N7** — serve minors: 18+ attestation gate; later disclosure of minority → supportive
  redirect + session restriction.
- **N8** — ship crisis config with placeholder values; startup validation must hard-fail.
- **N9** — collect unneeded data: nickname only, 18+ attestation only (no DOB), city only
  for referrals.

**ALWAYS:**
- **A1** — Sentinel pre-pass on every inbound message AND post-pass on every outbound draft.
- **A2** — provenance on every extracted pattern; only user-confirmed patterns enter agent
  context.
- **A3** — screener items rendered verbatim from versioned instrument files; never
  paraphrased.
- **A4** — "AI, not a clinician, not for emergencies" disclosure at first run, in Settings,
  and in every exported report header.
- **A5** — crisis/referral resources localized per country from operator-verified config.
- **A6** — safety-relevant events logged to an append-only audit table.

---

## 2. Proposed Repository Tree

```
PalioApp/
├── PLAN.md                     # this file
├── DECISIONS.md                # running decision log (started Phase 0)
├── README.md                   # setup, architecture overview, retention defaults (§14)
├── docker-compose.yml          # api + postgres(pgvector) + worker
├── .github/workflows/ci.yml    # lint + typecheck + tests + safety evals (blocking)
│
├── app/                        # Expo (React Native) + TypeScript, expo-router
│   ├── app/                    # routes: welcome, chat, screening, patterns, plan,
│   │   │                       #         report, crisis, settings
│   ├── src/
│   │   ├── components/         # chat bubbles, instrument cards, suggestion cards, charts
│   │   ├── i18n/               # ar (primary, RTL) + en resources, i18next
│   │   ├── api/                # typed client for /api
│   │   ├── store/              # session state, guest identity, offline crisis cache
│   │   └── theme/              # calm/spacious/WCAG-AA tokens, dyslexia-friendly type opt
│   └── package.json
│
├── api/                        # Python 3.12 + FastAPI + SQLAlchemy + Pydantic
│   ├── palio/
│   │   ├── main.py             # app factory; startup validation (crisis config — N8)
│   │   ├── config.py           # 12-factor settings, DATA_REGION, kill-switch env vars
│   │   ├── db/                 # models, migrations (alembic), row-level user scoping
│   │   ├── llm/                # single Anthropic gateway: retries, timeouts, cost log,
│   │   │                       #   per-user daily token budget, per-agent kill-switch
│   │   ├── safety/             # sentinel: rules layer (AR/EN/dialect regex),
│   │   │                       #   haiku classifier, post-pass checks, crisis protocol
│   │   ├── orchestrator/       # router, context-pack builder (token-capped), turn loop
│   │   ├── agents/             # companion, assessment, psychoeducation, coach,
│   │   │                       #   pattern_extractor, referral_reports, case_review
│   │   ├── assessments/        # instrument loader, scoring engine, formulation builder
│   │   ├── patterns/           # pattern CRUD, confirmation workflow, edges, embeddings
│   │   ├── reports/            # PDF generation (AR RTL + EN), disclaimer header
│   │   ├── jobs/               # Postgres-backed job table + APScheduler worker
│   │   ├── audit/              # append-only safety_events + audit_log writers
│   │   └── routers/            # HTTP/SSE endpoints
│   └── tests/                  # unit + integration (scoring vectors, scoping, jobs)
│
├── prompts/                    # {agent}.md = shared base (identity + Hard Rules + style)
│   │                           #   + per-agent kernel (§5 verbatim in substance)
│   └── _base.md
│
├── content/                    # operator-approved psychoeducation + strategy library
│   ├── strategies/             # 10 seed EF strategies, AR+EN, structured front-matter
│   └── psychoeducation/        # AR+EN condition/mechanism/treatment-landscape articles
│
├── config/
│   ├── crisis_resources.sa.json      # BLOCKING PLACEHOLDER until operator input #1
│   ├── instruments/                  # asrs_v1_1.json, phq9.json, gad7.json (versioned;
│   │                                 #   AR text placeholder-flagged until input #2)
│   └── referral_directory.seed.json  # BLOCKING PLACEHOLDER until operator input #4
│
├── evals/                      # YAML cases → runner → orchestrator test mode
│   ├── cases/                  # 12 families × ≥8 cases × AR+EN (incl. dialect)
│   ├── golden/                 # crisis-script snapshot transcripts
│   └── runner/                 # assertions: risk level, forbidden-content regex,
│                               #   LLM-judge, UI-trigger flags; CI-blocking
└── docs/
    ├── pdpl_checklist.md
    └── beta_readiness.md
```

---

## 3. Phase-by-Phase Task Breakdown (with estimates)

Estimates are focused engineering sessions (~half-day units). Order is strict; each phase
gates on its acceptance criteria.

### Phase 0 — Foundation (est. 3–4 sessions)
- Monorepo scaffold as above; Docker Compose (FastAPI + Postgres 16 + pgvector + worker).
- Alembic migrations for all core tables (§11): users, sessions, messages, patterns,
  pattern_edges, screener_instruments, screener_results, support_plans, strategies_log,
  referral_directory, reports, safety_events, jobs, audit_log, consents.
- CI: ruff + mypy + pytest (api), eslint + tsc + jest (app); DECISIONS.md started.
- ✅ Gate: `docker compose up` → healthy API + DB; CI green.

### Phase 1 — Safety spine (est. 6–8 sessions)
- `llm/` gateway (retries, timeouts, cost logging, budgets, kill-switches).
- Sentinel pre-pass: deterministic AR/EN/dialect rules layer (instant L3 floor) +
  Haiku classifier; final level = max(rules, classifier); uncertainty → higher.
- Sentinel post-pass: N1/N3/N4/N6 checks → pass / rewrite-once / safe fallback.
- Crisis Protocol (api): L3 lock-in, crisis script, agent suspension, incident record.
- Crisis screen (app): full-screen, offline-cached verified resources, persistent quiet
  help affordance.
- Crisis-config startup validation that hard-fails on placeholders/empty `verified_by`.
- safety_events + audit logging; eval harness skeleton + L-level suite.
- ✅ Gate: §13 safety suite in CI; L3 cases 100%; placeholder config refuses production boot.

### Phase 2 — Conversation core (est. 6–8 sessions)
- Orchestrator turn loop + Router (Haiku structured output, sticky mode state).
- Companion agent + `/prompts` base + kernels.
- Welcome/capability disclosure + 18+ attestation + language pick; guest-first onboarding
  (attestation precedes first chat — see §5.3 below).
- Chat UI (streaming presentation, RTL-correct, strategy reactions 👍/👎).
- Sessions/messages persistence; email-OTP + Google OAuth; guest→account migration.
- ✅ Gate: full first-session flow AR + EN with Sentinel on both directions of every message.

### Phase 3 — Assessment & Formulation (est. 5–6 sessions)
- Versioned instrument JSONs (EN verbatim; AR placeholder-flagged pending input #2).
- Screening UI cards (verbatim render, progress, pause/resume); consent step.
- Scoring engine + unit tests against published vectors; band mapping.
- Formulation template renderer (the only results channel); honest line verbatim.
- PHQ-9 item 9 > 0 → immediate Sentinel L2 escalation event.
- ✅ Gate: correct scores on test vectors; formulation eval-checked for banned declarations.

### Phase 4 — Coaching loop (est. 4–5 sessions)
- Skills Coach agent; `/content/strategies` structure + 10 seed EF strategies (AR+EN,
  flagged for clinical advisor sign-off — input #3).
- Assign → try → structured feedback → adapt/swap loop; strategies_log; Plan screen.
- Coach suppression on L1–L2 sessions (tested); single opt-in daily check-in notification.
- ✅ Gate: end-to-end strategy lifecycle; suppression verified by tests.

### Phase 5 — Memory & Patterns (est. 5–6 sessions)
- Pattern Extractor job (proposed-only, evidence IDs, confidence).
- Suggestion-card confirmation queue; Patterns & Progress screen (map + trend charts).
- Context-pack builder with hard token cap + composition logging.
- Memory pause toggle; node edit/hard-delete; wins/strengths as first-class nodes.
- ✅ Gate: tests assert only confirmed patterns can enter a context pack.

### Phase 6 — Bridge to care (est. 4–5 sessions)
- Report generator (PDF, AR RTL + EN) with A4 disclaimer header; confirmed-data-only rule.
- Referral directory + admin seed script (real data = input #4); referral-tap + export
  event metrics.
- Full JSON export; hard delete-account flow; versioned consent records.
- ✅ Gate: report contains only confirmed data + scores; delete leaves no user rows outside
  the audit ledger.

### Phase 7 — Case Review & hardening (est. 5–7 sessions)
- Case Review job: four lenses in sequence (safety trajectory, assessment gaps, coaching
  efficacy, engagement health/dependency signals) → support-plan JSON + operator flags.
- Metrics dashboard (success metrics §3 only).
- Red-team eval expansion (jailbreak, prompt injection via pasted content); load test.
- PDPL checklist doc; beta-readiness report.
- ✅ Gate: full eval suite green; valid support-plan update on fixture data; beta checklist
  complete except §16 operator items.

**Total estimate: ~38–49 sessions (~4–6 weeks of focused build).**

---

## 4. Anticipated DECISIONS.md Entries

1. Monorepo layout & tooling versions (Expo SDK, Python 3.12, Postgres 16 + pgvector).
2. Alembic for migrations; row-level user scoping enforced via a mandatory query helper,
   not ad-hoc WHERE clauses.
3. Model IDs are env-configured (`PALIO_MODEL_FAST`, `PALIO_MODEL_MAIN`), defaulting to the
   spec's assignments — so operator can upgrade models without code change.
4. **Streaming vs post-pass (see conflict C1):** server generates the full draft, runs the
   Sentinel post-pass, then streams the approved text to the client (SSE) for streaming UX.
   True token-level passthrough streaming deferred; safety wins.
5. Sentinel degraded mode: on classifier timeout/error, use rules-layer result; any rules
   hit escalates one level; degraded-mode event logged. Latency budgets treated as p95
   targets measured in metrics, not hard cutoffs.
6. Crisis-config validation always runs; `APP_ENV=production` (or unset) hard-fails on
   placeholders (N8). `APP_ENV=development` + explicit `ALLOW_UNVERIFIED_CRISIS_CONFIG=1`
   permits a clearly-labeled dev fixture so Phases 1–7 are buildable pre-input-#1; the
   flag is refused in production builds.
7. Router stickiness: an active instrument session pins routing to Assessment until
   completed/paused; L-level changes override stickiness.
8. Embeddings: pgvector requires an embedding model; Anthropic does not offer an
   embeddings API. Default to a small local/open-source multilingual embedding model run
   in the worker (no third-party data sharing, PDPL-friendlier); operator may swap via env.
9. Guest identity: device-scoped UUID in secure storage; server-side guest user rows with
   `is_guest=true`; migration = ownership transfer in one transaction.
10. OTP delivery provider abstraction (dev: logged code; prod: operator-configured SMTP) —
    no third-party analytics/comms SDKs beyond email.
11. Job system: single `jobs` table with status/lease columns; APScheduler worker polls;
    idempotent handlers; no Redis.
12. PDF generation: WeasyPrint (HTML→PDF) for proper RTL Arabic shaping; bundled
    open-license Arabic font.
13. Audit/append-only enforcement: DB-level REVOKE UPDATE/DELETE + trigger guard on
    safety_events and audit_log.
14. Hard delete vs audit ledger: user hard-delete removes all user rows and content;
    audit/safety rows are retained but keyed to an opaque subject ID with PII scrubbed at
    write time (never raw message text — event type, level, timestamps, hashes).
15. i18n: i18next in app; API returns language-neutral codes + server-rendered LLM text in
    the user's locale; instrument text always from versioned files, never from i18n
    catalogs.
16. Eval runner design: orchestrator "test mode" with recorded/live LLM toggle; safety
    families run live in CI against the fast model with seeded cases; regressions block
    merge.
17. Cost controls: per-user daily token budget enforced in `llm/`; over-budget → graceful
    "come back later" message (never a dark-pattern upsell).
18. Notification: Expo local notifications only (no push infra in v1) for the single
    opt-in daily check-in.
19. Multi-tenant readiness: `org_code` nullable column + redemption stub endpoint; no org
    admin UI in v1.
20. Dialect handling: rules lists include Gulf/Saudi variants; classifier few-shots include
    dialect examples; output style = warm MSA per spec.

---

## 5. Conflicts & Ambiguities Detected

**C1 — Streaming chat (§10.3) vs mandatory Sentinel post-pass on every outbound draft
(A1).** True token streaming would show text before the post-pass can inspect the complete
draft. Proposed resolution (Decision 4): full server-side generation → post-pass → stream
approved text to the client. UX stays "streaming"; safety guarantee stays absolute.
**Needs operator sign-off since it touches safety architecture.**

**C2 — N8 "refuses to boot on placeholder crisis config" vs building Phases 1–7 before
operator input #1 exists.** Proposed resolution (Decision 6): validation always runs;
production always hard-fails; development boot allowed only with an explicit flag and a
clearly-labeled unverified dev fixture. The Phase 1 acceptance test asserts the production
path refuses to boot.

**C3 — Sentinel latency budgets (<400ms) vs an LLM classifier round trip.** Network + model
latency can exceed 400ms. Treated as p95 targets with metrics + a defined degraded mode
(Decision 5) rather than hard timeouts that would silently skip classification.

**C4 — Guest-first "conversation starts immediately" (§10.2) vs 18+ attestation gate (N7).**
Resolved by ordering: capability disclosure + attestation + language pick are the welcome
screen itself; chat starts immediately *after* that single screen, before any
nickname/account. N7 wins; friction kept to one screen.

**C5 — Embeddings dependency (§8/§11).** pgvector is specified but no embedding provider
is; Anthropic has no embeddings API. Proposed: local multilingual model in the worker
(Decision 8). Flagging because it's the one place the locked stack under-specifies a
required component.

**C6 — Instrument licensing.** ASRS v1.1, PHQ-9, GAD-7 are free-to-use as stated, but I
will not author Arabic item text (input #2) and will ship English text from official
public sources with source citations in the instrument files. Any doubt about a specific
text's provenance becomes a blocking placeholder, not an invention (Working Agreement 7).

**C7 — Phase 2 acceptance "on device/simulator."** CI cannot run device tests; proposal:
CI runs unit/integration + eval suites, and device/simulator verification is a documented
manual checklist per phase in the README. Estimates above assume this.

**C8 — Spec model names.** The spec's `claude-sonnet-4-6` / `claude-haiku-4-5` are wired as
env-configurable defaults (Decision 3); if a named model is unavailable at the API at build
time, I'll default to the closest current equivalent and log it in DECISIONS.md rather than
hard-failing.

None of these change the Hard Rules; where a conflict touched one, the Hard Rule won.

---

## 6. What I Need From the Operator Now

1. **Approval of this PLAN.md** (or edits), specifically the C1 streaming resolution.
2. Nothing else is blocking Phase 0. Items §16 #1–#6 remain blocking placeholders at the
   phases listed there; I will build placeholder-flagged infrastructure around them.
