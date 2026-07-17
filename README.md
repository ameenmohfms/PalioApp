# Palio

Arabic-first, text-first companion for adults (18+) navigating ADHD and executive-function
struggles. Palio **screens, educates, supports, and refers — it never diagnoses.**

> Palio is an AI. It is not a clinician or therapist, does not diagnose, and is not for
> emergencies. This disclosure appears at first run, in Settings, and on every exported
> report (Hard Rule A4).

## Repo layout

| Path | What |
|---|---|
| `app/` | Expo (React Native) + TypeScript mobile app, expo-router, AR/EN i18n |
| `api/` | Python 3.12 + FastAPI backend, SQLAlchemy + Alembic, worker process |
| `prompts/` | Versioned agent prompts (base + kernels, spec §5) |
| `content/` | Operator-approved strategy library & psychoeducation (AR+EN) |
| `config/` | Crisis resources, instruments, referral seed — operator-verified assets |
| `evals/` | Safety eval harness (§13); regressions block merge |
| `docs/` | PDPL checklist, beta readiness |
| `PLAN.md` / `DECISIONS.md` | Approved build plan / decision log |

## Development

Requirements: Docker + Docker Compose, Node 22, uv (or any Python 3.12 toolchain).

```bash
cp .env.example .env          # fill ANTHROPIC_API_KEY for LLM features
# Dev only: the repo ships PLACEHOLDER crisis resources, so the API refuses
# to boot (Hard Rule N8) until you explicitly acknowledge dev mode:
echo "ALLOW_UNVERIFIED_CRISIS_CONFIG=1" >> .env
docker compose up --build     # db (pgvector) + api (:8000) + worker
curl localhost:8000/healthz   # {"status":"ok"}
```

API dev loop (without Docker, against the compose db):

```bash
cd api
uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e . --group dev
.venv/bin/alembic upgrade head       # DATABASE_URL as needed
.venv/bin/pytest -q                  # `pg`-marked tests need the db running
.venv/bin/ruff check palio tests migrations && .venv/bin/mypy palio
```

App dev loop:

```bash
cd app
npm install --legacy-peer-deps
npm run lint && npm run typecheck && npm test
npm start                            # Expo dev server (device/simulator)
```

## Safety posture (non-negotiable)

- Every inbound user message and outbound draft passes the Safety Sentinel (Phase 1).
- `config/crisis_resources.*.json` currently contains **blocking placeholders**; production
  boot hard-fails until the operator supplies verified crisis lines (Hard Rule N8, §16 #1).
  Development boot requires the explicit `ALLOW_UNVERIFIED_CRISIS_CONFIG=1` escape hatch,
  which is refused when `APP_ENV=production`.
- `safety_events` and `audit_log` are append-only at the database level (trigger-enforced).

## Data & privacy (PDPL posture, §14)

- Data minimization is structural: no legal-name column, no date-of-birth column; nickname,
  locale, and an optional referral city only.
- User rights in-app (from Phase 6): full JSON export, hard delete, memory pause.
- `DATA_REGION` must point at a KSA/ME region in production; architecture is region-agnostic.
- **Retention defaults for counsel review:** user content — until user deletion (hard
  delete); `safety_events` / `audit_log` — 24 months, opaque subject IDs, PII-scrubbed at
  write time; job rows — 90 days. Operator policy may tighten these.

## Evals & safety testing

- CI-blocking safety families run inside `api` pytest (`tests/test_eval_suite.py`) with
  the LLM classifier scripted out — the L3 gate holds on deterministic rules alone.
- Live families (nuanced classifier cases + full-turn behavioral red-team):
  `ANTHROPIC_API_KEY=... api/.venv/bin/python evals/runner/run_live.py [--behavioral]`
- Load test: `python evals/runner/load_test.py --base http://localhost:8000`

## Operator

- Metrics (success metrics only — no engagement metrics by design):
  `GET /operator/metrics` with `X-Operator-Token` (set `OPERATOR_TOKEN`; endpoint is
  hidden when unset).
- Referral seeding: `python -m palio.admin.seed_referrals` (refuses unverified entries).
- Blocking inputs before beta/production: see `docs/beta_readiness.md` (§16 items).

## Status

Phases 0–7 built. Beta-blocked on the §16 operator inputs (crisis lines, verified Arabic
instruments, clinical sign-off, referral data, counsel review, store review) — see
`docs/beta_readiness.md` and `PLAN.md` for the phase gates.
