# Splitranch API

FastAPI service (one package, `split_ranch`, one process; no background worker).
Spec: `docs/01-architecture.md`, `docs/02-data-model.md`, `docs/03-business-rules.md`, `docs/04-api.md`.

```
src/split_ranch/
├── domain/        pure money/split/settle (mirrors packages/domain, checked by packages/domain-vectors)
├── schemas/       strict Pydantic v2 models (extra=forbid, discriminated union on split_type)
├── use_cases/     one function per business action (authz, transactions, history)
├── repositories/  SQLAlchemy queries, always scoped by household_id
├── models/        SQLAlchemy 2.0 ORM, schema "app" (10 tables)
├── api/           thin routers + dependencies (JWT -> Actor, membership -> HouseholdActor)
└── core/          settings, db, Supabase JWT verification, logging, errors, clock, uuid7
migrations/        Alembic (owns only the `app` schema)
tests/             parity/ unit/ integration/ (tenant isolation lives in integration/)
```

## Setup (uv, Python 3.12)

```sh
cd apps/api
uv python install 3.12
uv venv --python 3.12
uv sync                     # runtime + dev dependency group, from uv.lock
```

## Environment

Read from the environment or `apps/api/.env` (names match the root `.env.example`, docs/11):

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | API | `postgresql+psycopg://…` — Supabase transaction pooler in the cloud (prepared statements are disabled) |
| `DATABASE_URL_SESSION` | migrations | session pooler (IPv4 on Supabase Free). Falls back to `DATABASE_URL` |
| `SUPABASE_URL` | API | JWKS is fetched from `$SUPABASE_URL/auth/v1/.well-known/jwks.json` (cached 10 min) |
| `SUPABASE_JWT_ISSUER` | API | expected `iss`; defaults to `$SUPABASE_URL/auth/v1` |
| `SUPABASE_SECRET_KEY` | API | account deletion only (`DELETE /v1/me` answers 503 without it) |
| `SENTRY_DSN` | API | Sentry is initialised only when set (`send_default_pii=False`) |
| `EXPO_ACCESS_TOKEN` | API | optional bearer token for the Expo Push Service; required once "enhanced security for push notifications" is on for the Expo account. Secret |
| `PUSH_ENABLED` | API | `false` stops all push notifications (default `true`; tests turn it off) |
| `APP_ENV` | all | `dev` / `test` / `staging` / `prod` (`/v1/docs` is disabled in prod) |
| `TEST_DATABASE_URL` | tests | optional, see below |

Optional tuning: `LOG_LEVEL`, `LOG_JSON`, `MIN_APP_VERSION`, `PUBLIC_WEB_URL`, `JWT_LEEWAY_SECONDS`,
`JWKS_CACHE_SECONDS`, `ENSURE_USER_CACHE_SECONDS`, `RATE_LIMIT_PER_MINUTE` (per user, default 120),
`INVITE_RATE_LIMIT_PER_MINUTE` (invitation preview/accept, default 10); `0` disables a limit.
Limits are kept in process memory, which is correct only while the API runs as a single process.

## Database and migrations

```sh
uv run alembic upgrade head          # uses DATABASE_URL_SESSION (or DATABASE_URL)
uv run alembic downgrade -1
uv run alembic check                 # no pending autogenerate diff
```

* `0005` is the baseline (the older chain was squashed): it creates the tables in `app` with CHECK
  constraints, composite (tenant-safe) foreign keys, deferred share-sum constraint triggers, the
  append-only `history` trigger and **RLS enabled with no policies**. If a `split_api` role exists,
  grants are applied; creating that role (it needs a password) is an infra task.
* `0006` turns households into groups and drops periods and settlement transfers
  (see `docs/egm/design_draft.md`). It refuses to run on tables that hold rows.

Migrations run against the database in `DATABASE_URL_SESSION`; in development that is the cloud
Supabase project, so run them deliberately.

## Run

```sh
uv run uvicorn split_ranch.main:app --reload --port 8000          # API, routes under /v1
```

`/healthz` and `/readyz` are served both at the root (platform probes) and under `/v1`.
OpenAPI: `/v1/openapi.json` (Swagger UI at `/v1/docs` outside prod).

## Tests and quality gate

```sh
uv run pytest            # parity vectors, Hypothesis properties, unit and DB integration tests
uv run ruff check .
uv run ruff format --check .
uv run mypy              # strict for the whole package
```

DB tests need PostgreSQL:

* if `TEST_DATABASE_URL` is set (CI service container), it is used. **The fixture drops and
  recreates the `app` schema in that database** — never point it at a real database;
* otherwise a throw-away PostgreSQL 16 is started with [`pgserver`](https://pypi.org/project/pgserver/)
  (dev dependency, works on Windows/Linux/macOS without Docker);
* if neither works, DB tests are skipped with the reason.

Each test runs in one outer transaction that is rolled back; use-case commits become SAVEPOINT
releases, and deferred constraints are forced (`SET CONSTRAINTS ALL IMMEDIATE`) before rollback so
share-sum violations still fail the test. Parity tests read `../../packages/domain-vectors/*.json`
(override with `SPLIT_RANCH_VECTORS_DIR`).

## Not implemented yet

Google Sheets sync and push notifications (no tables and no background jobs yet: each will add what
it needs), `DELETE /me` (account deletion).
