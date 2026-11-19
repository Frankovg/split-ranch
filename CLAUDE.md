# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## What this is

Split Ranch: Android-first app for shared expenses in groups (flat, trip, couple…) with one running balance per group and no periods, plus an offline "Quick splits" tool. Monorepo: pnpm workspaces (JS/TS) + uv (Python). Design docs live in `docs/00`–`13` (the root README still says "planning only", but the API and mobile app are implemented; docs are the spec for business rules, data model and API). Code comments and log messages must be in English; UI strings go through i18n keys only.

- `apps/api` — FastAPI API (Python package `split_ranch`, one process, no background worker). Python 3.12.
- `apps/mobile` — Expo SDK 58 / React Native dev-client app (not Expo Go), Expo Router, NativeWind, Zustand, i18next (Spanish default, English).
- `packages/domain` — pure TS money/split/settle logic (`@split-ranch/domain`).
- `packages/domain-vectors` — language-neutral JSON test vectors.
- `packages/api-client` — `openapi.json` exported from the API + generated TS types (`@split-ranch/api-client`); never edit by hand.
- `supabase/` — local Supabase CLI stack config (Postgres + Auth). `infra/` — Render blueprint and runbooks.

## Commands

Root (`package.json`):

```sh
pnpm install
pnpm test | pnpm typecheck | pnpm lint     # recursive, --if-present
pnpm db:up / db:down                        # supabase start / stop (Docker)
pnpm api:dev                                # uvicorn on :8000
pnpm mobile:dev                             # expo start --dev-client + keeps adb reverse (8081, 8000) applied
pnpm adb:reverse                            # one-shot adb reverse for every connected device
pnpm domain:test                            # TS domain + parity vectors
pnpm api:test                               # pytest
pnpm api:openapi                            # export OpenAPI + regenerate packages/api-client (after any API schema/route change)
```

API (run in `apps/api`; see its README for env vars):

```sh
uv sync
uv run pytest                               # single test: uv run pytest tests/unit/test_auth.py::test_name -q
uv run ruff check . && uv run ruff format --check . && uv run mypy   # mypy is strict
uv run alembic upgrade head                 # also: downgrade -1, check
```

Mobile / domain: `pnpm --filter @split-ranch/mobile typecheck|test|export:android|doctor`, `pnpm --filter @split-ranch/domain typecheck|test`. Single vitest file: `pnpm --filter @split-ranch/mobile exec vitest run src/features/quick-splits/quick-splits.test.ts`.

CI (`.github/workflows/ci.yml`) runs domain typecheck/test, mobile typecheck/test, API ruff + format + mypy + pytest (against a Postgres service via `TEST_DATABASE_URL`), an API-contract job (fails if `packages/api-client` is stale versus the exported OpenAPI), and a gitleaks scan.

## Architecture

**Money logic is implemented twice** (TS in `packages/domain`, Python in `apps/api/src/split_ranch/domain`) with mirrored names (`allocate`, `resolve_shares`/`resolveShares`, `compute_balances`, `settle`). Parity is enforced by the shared JSON vectors in `packages/domain-vectors`, consumed by `apps/api/tests/parity` and the domain package tests. Changing a vector is a money-behaviour change; change both implementations together.

**API layering** (`apps/api/src/split_ranch/`): `api/routers` (thin; JWT → `Actor`, membership → `GroupActor` (left members get 404) via `api/deps.py`) → `use_cases` (one function per business action: authz, transactions, history) → `repositories` (SQLAlchemy queries, always scoped by `group_id`) → `models` (SQLAlchemy 2.0, schema `app`). `schemas` are strict Pydantic v2 (`extra=forbid`, discriminated union on `split_type`). Auth is Supabase JWT verified against the project's JWKS; the mobile app uses Supabase for auth only and talks to FastAPI for all data (`/v1/...`).

**Database**: Alembic owns only the `app` schema: 9 tables (`docs/02-data-model.md`). Add a table only with the feature that needs it — no tables "for later". Split rules are `SplitSpec` JSON on `groups.split_rule` / `categories.split_rule`; every change is recorded in the append-only `history` table; the balance is computed on request from live expenses plus confirmed `payments` (no periods, nothing stored); one active admin per group (partial unique index); expense creation is idempotent through the client-generated id. Tenant isolation is enforced in the DB too: composite tenant-safe FKs, deferred share-sum constraint triggers, an append-only trigger on `history`, and RLS enabled with no policies. There is no job queue or worker; `migrations/sql` is only used by old migrations (0002 and 0005's downgrade); 0006 rebuilt the schema and refuses to run on non-empty tables, never by the app. API uses the transaction pooler (`DATABASE_URL`, prepared statements disabled); migrations use `DATABASE_URL_SESSION`. Migrations run against the cloud database: the user runs them, and `infra/render.yaml` also runs `alembic upgrade head` on every deploy. Never run the alembic CLI without an explicit local URL: its default is the cloud database.

**Tests**: DB tests run each test in one rolled-back transaction. With `TEST_DATABASE_URL` set, the fixture **drops and recreates the `app` schema** in that DB — never point it at a real database. Without it, a throwaway Postgres is started via `pgserver`.

**Mobile**: `app/` holds thin routes only; logic lives in `src/features/*` (quick-splits is fully offline and persisted in MMKV via Zustand; group screens use `features/groups/api.ts`, typed calls through `api`/`unwrap` from `src/lib/api` (openapi-fetch; `features/groups/types.ts` only aliases the generated types); the open group comes from the route `group/[groupId]` via `features/groups/route.ts`, nothing persisted). `src/components/ui` is owned React Native Reusables code (each file has a `// Source:` header noting local changes). `src/theme/tokens.ts` mirrors `global.css` and a test keeps them in sync. All `EXPO_PUBLIC_*` env vars are bundled — never secrets; missing ones disable features rather than crash.

## Conventions

Conventional Commits, trunk-based short-lived branches, one Alembic migration per PR, Python fully typed, TS strict with `noUncheckedIndexedAccess`.
