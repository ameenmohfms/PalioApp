# DECISIONS.md — Palio technical decision log

Format: `D<N> (<date>) — <decision>. Rationale: <one line>.`

- D1 (2026-07-16) — Monorepo layout `/app /api /prompts /content /config /evals /docs` per PLAN.md. Rationale: matches spec §12 Phase 0 and keeps safety assets (prompts/config/evals) version-locked with code.
- D2 (2026-07-16) — Python 3.12 in Docker; local dev venv also 3.12 via `uv`. Rationale: spec-locked runtime; uv for fast reproducible installs.
- D3 (2026-07-16) — Model IDs are env-configured (`PALIO_MODEL_FAST`, `PALIO_MODEL_MAIN`). Spec's `claude-haiku-4-5` exists and is the fast default; spec's `claude-sonnet-4-6` does not exist at the Anthropic API, so the main default is `claude-sonnet-5` (closest current equivalent, per PLAN.md C8). Rationale: operator can swap models without code change; no hard-coded model names outside config.
- D4 (2026-07-16) — SQLAlchemy 2.0 declarative models + Alembic migrations; UUID primary keys generated server-side (`gen_random_uuid()`). Rationale: spec-locked ORM; server-side UUIDs keep inserts race-safe across API and worker.
- D5 (2026-07-16) — Postgres image `pgvector/pgvector:pg16`. Rationale: official pgvector build of Postgres 16, no custom image to maintain.
- D6 (2026-07-16) — Row-level user scoping enforced via mandatory `user_scoped()` query helper; direct `select()` on user-owned tables is lint-checked in code review, and tests assert cross-user reads fail. Rationale: single choke-point beats ad-hoc WHERE clauses.
- D7 (2026-07-16) — `messages.content` and other user text columns are `TEXT` with encryption at rest delegated to the DB volume/provider layer; no app-layer field crypto in v1. Rationale: spec requires encryption at rest, not field-level; app-layer crypto would break pgvector search and add key-management scope.
- D8 (2026-07-16) — Jobs: single `jobs` table (status, run_at, lease_until, attempts, payload JSONB) polled by an APScheduler worker process; handlers idempotent. Rationale: spec forbids Redis/queue infra in v1.
- D9 (2026-07-16) — Append-only enforcement for `safety_events` and `audit_log` via Postgres trigger that raises on UPDATE/DELETE. Rationale: A6 must hold even against buggy app code, not just convention.
- D10 (2026-07-16) — Expo app scaffolded from `create-expo-app` blank-typescript (Expo SDK 57) to inherit the correct version matrix, then template example code removed and expo-router structure added by hand. Rationale: hand-pinning an RN version matrix is error-prone; residue removed instead.
- D11 (2026-07-16) — API and worker share one Docker image with different commands. Rationale: one build, no drift between web and job code.
- D12 (2026-07-16) — `APP_ENV` ∈ {development, test, production}; production is the default when unset. Rationale: fail-safe direction — forgetting config must yield the strictest behavior (N8 validation on).
- D13 (2026-07-16) — Pattern embeddings: `intfloat/multilingual-e5-small` (384-dim) run locally in the worker; column typed `vector(384)`. Rationale: strong AR+EN retrieval, no third-party data sharing (PDPL), swappable via env later.
- D14 (2026-07-16) — App test runner pinned to Jest 29 (`jest@^29.7`, `@types/jest@^29.5`) because `jest-expo@57` is built on the Jest 29 ecosystem; Jest 30 mixes incompatible `jest-mock`/`jest-runtime`. `npm ci --legacy-peer-deps` needed for `react-server-dom-webpack` peer pin. Rationale: match the preset's supported matrix.
- D15 (2026-07-16) — Worker is a plain poll loop over the jobs table (2s idle sleep); APScheduler is added only when recurring schedules land (weekly Case Review, Phase 7) to enqueue jobs on cron — execution stays in the same loop. Rationale: one execution path; scheduler only produces rows.
