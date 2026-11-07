# 11 — Repository structure

Monorepo, pnpm workspaces for JS/TS and **uv** for Python. No Turborepo/Nx at first (few packages; pnpm `--filter` is enough). Add Turborepo only if CI times hurt.

```
split-ranch/
├── apps/
│   ├── mobile/                 # Expo app (see 05-mobile-app)
│   └── api/                    # FastAPI + worker
│       ├── pyproject.toml      # uv-managed; package "split_ranch"
│       ├── src/split_ranch/    # domain/ schemas/ use_cases/ repositories/ models/ api/ jobs/ integrations/ core/
│       ├── migrations/         # Alembic
│       └── tests/              # unit/ integration/ parity/ tenant_isolation/
├── packages/
│   ├── domain/                 # @split-ranch/domain — pure TS: money, split, settle (no RN imports)
│   ├── domain-vectors/         # shared JSON test vectors + JSON Schemas
│   ├── api-client/             # generated OpenAPI types + openapi-fetch wrapper
│   └── config/                 # shared eslint/tsconfig/prettier presets
├── supabase/
│   └── config.toml             # Supabase CLI local stack: auth providers, JWT settings, exposed schemas
├── infra/
│   ├── render.yaml             # Render blueprint: web + worker (staging/prod); DB lives in Supabase
│   └── README.md               # runbooks: Supabase project settings checklist, secrets rotation, restore drill, Google Workspace setup
├── docs/                       # these documents
├── .github/workflows/
├── .env.example
├── package.json  pnpm-workspace.yaml
└── README.md
```

**Why the Python domain lives inside `apps/api`** and not in `packages/`: only the API uses it; parity is guaranteed by `domain-vectors`, not by sharing code. Mirror the module and function names exactly (`allocate`, `resolve_shares`, `settle`).

## Conventions
- **Branches**: trunk-based, short-lived `feat/…`, `fix/…`; squash merge.
- **Commits**: Conventional Commits (`feat(api): …`, `fix(mobile): …`).
- **Python**: `snake_case`, typed everywhere, one use case per module (`use_cases/expenses/create_expense.py`), routers named by resource.
- **TS**: `camelCase` in code, API types stay `snake_case` (generated); feature folders; components `PascalCase.tsx`; hooks `useX.ts`.
- **Comments and log messages in English.** UI strings only via i18n keys.
- **Migrations**: one per PR, reviewed by hand.
- **ADRs**: significant decisions after this plan go in `docs/adr/NNNN-title.md`.

## Local development

The local stack is the **Supabase CLI** (`supabase start`), which runs Postgres + Auth (and other Supabase services we ignore) in Docker, using `supabase/config.toml`. No docker-compose file and no Redis are needed.

- Local Postgres: `postgresql://postgres:postgres@localhost:54322/postgres` (the CLI's default port; Alembic creates the `app` schema and the `split_api` role).
- Local Auth: Google provider configured in `config.toml` with the dev web client ID (secret via `env()`), `skip_nonce_check = false`.
- Signing in from the Android dev build against the local stack requires the device to reach the host (`adb reverse tcp:54321 tcp:54321`). For day-to-day mobile work it is simpler to point the dev build at the **staging** Supabase project and a local or staging API.
- Backend tests don't need Supabase: CI uses a plain `postgres` container and signs test JWTs with a local ES256 key served by a fake JWKS.

Root scripts (`package.json`):

| Script | Does |
|---|---|
| `pnpm db:up` / `db:down` | `supabase start` / `supabase stop` |
| `pnpm db:reset` | `supabase db reset` (empty DB) then `alembic upgrade head` + seed |
| `pnpm api:dev` | `cd apps/api && uv run uvicorn split_ranch.main:app --reload` |
| `pnpm worker:dev` | `cd apps/api && uv run procrastinate --app=split_ranch.jobs.app.app worker` |
| `pnpm api:migrate` | `alembic upgrade head` |
| `pnpm api:seed` | demo data |
| `pnpm mobile:dev` | `expo start --dev-client` (dev build installed on device/emulator) |
| `pnpm api:openapi` | dump OpenAPI and regenerate `packages/api-client` |
| `pnpm test` | all test suites (domain TS + Py + parity) |
| `pnpm lint` / `typecheck` | all workspaces |
| `pnpm vectors:gen` | regenerate random parity vectors (seeded) |

Physical device → local API: use `adb reverse tcp:8000 tcp:8000` or point the dev build at the staging API via `EXPO_PUBLIC_API_URL`.

## Environment variables (`.env.example`)

```
# API (transaction pooler in cloud; local stack uses the direct port)
DATABASE_URL=postgresql+psycopg://split_api:split_api@localhost:54322/postgres
# worker + migrations (session pooler / direct in cloud: needs LISTEN/NOTIFY)
DATABASE_URL_SESSION=postgresql+psycopg://split_api:split_api@localhost:54322/postgres
SUPABASE_URL=http://localhost:54321
SUPABASE_JWT_ISSUER=http://localhost:54321/auth/v1
SUPABASE_SECRET_KEY=            # worker only (account deletion)
GOOGLE_SERVICE_ACCOUNT_JSON_B64=
GOOGLE_SHARED_DRIVE_ID=
SENTRY_DSN=
APP_ENV=dev
# supabase/config.toml reads these for the local Google provider
SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=
SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET=
# mobile (EXPO_PUBLIC_* are bundled — never secrets)
EXPO_PUBLIC_API_URL=http://localhost:8000
EXPO_PUBLIC_SUPABASE_URL=http://localhost:54321
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID=
EXPO_PUBLIC_SENTRY_DSN=
```
