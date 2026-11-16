# 09 — Testing and quality

## Test pyramid

| Layer | Python (API) | TypeScript (domain + mobile) |
|---|---|---|
| Domain unit | `pytest` on `domain/` | `vitest` on `packages/domain` |
| Property-based | **Hypothesis** | **fast-check** |
| Parity | shared JSON vectors | shared JSON vectors |
| Use cases / integration | pytest + real Postgres (Testcontainers or the CI service container), transaction-per-test rollback | — |
| API contract | `httpx.AsyncClient` against the app; OpenAPI schema diff check | generated client type-checks |
| Components | — | `jest-expo` + React Native Testing Library |
| E2E mobile | — | **Maestro** flows on an Android emulator (EAS Build artifact) |
| Sheets | renderer snapshot tests; nightly sandbox integration | — |

## Property tests (money and settlement)

`allocate(total, ratios)`:
- `sum(result) == total` for all `total ∈ [-10⁹, 10⁹]`, ratios non-negative with positive sum.
- each `result[i] ∈ {floor(exact_i), ceil(exact_i)}` (compare with rational arithmetic).
- zero ratio → zero.
- determinism: same input twice → same output.
- sign symmetry: `allocate(-t, r) == -allocate(t, r)`.
- scaling: `allocate(t, k·r) == allocate(t, r)` for integer `k > 0`.

`resolve_shares(expense, rule, members)`:
- shares sum to amount (except `personal`: single share = amount).
- only participants receive non-zero shares.
- exact split mismatch always raises.

`settle(nets)`:
- requires `Σ nets == 0`.
- after applying the transfers, every net is 0 (no cent lost).
- number of transfers ≤ `count(non-zero nets) − 1`.
- every transfer amount > 0; no member both pays and receives.
- deterministic for the same ordered input; permutation of input order with the same canonical order key → same output.

Ledger invariants (integration; Hypothesis stateful testing planned): random sequences of create/edit/delete expenses and record/confirm/dispute/cancel payments → `Σ nets == 0` at every step; only confirmed payments move nets; suggestions settle the confirmed-plus-sent ledger exactly.

## TS ↔ Python parity with shared vectors

```
packages/domain-vectors/
├── allocate.json
├── resolve_shares.json
├── settle.json
└── schema/*.schema.json      # JSON Schema of each vector file
```

Example (`allocate.json`):

```json
[
  {"name": "equal_three_leftover_one", "total": 1000, "ratios": [1, 1, 1], "expected": [334, 333, 333]},
  {"name": "largest_remainder_beats_order", "total": 101, "ratios": [1, 3], "expected": [25, 76]},
  {"name": "zero_ratio_skipped", "total": 1003, "ratios": [0, 50, 50], "expected": [0, 502, 501]},
  {"name": "negative_symmetry", "total": -1000, "ratios": [1, 1, 1], "expected": [-334, -333, -333]},
  {"name": "invalid_all_zero", "total": 100, "ratios": [0, 0], "error": "invalid_ratios"}
]
```

- Both test suites load every file and assert identical outputs/errors.
- A generator script (`pnpm vectors:gen`, Python) produces **random** vectors from the Python implementation (seeded); CI runs the TS suite against them → any divergence fails the build. Hand-written vectors cover documented examples from [03](03-business-rules.md).
- Changing a vector requires a note in the PR template ("money behaviour change").

## Other test suites
- **Tenant isolation** (see [08](08-security-and-privacy.md)): auto-generated from OpenAPI routes.
- **Migrations**: upgrade from empty, downgrade last, `alembic check`.
- **Auth**: tests sign Supabase-shaped JWTs with a local ES256 key exposed through a fake JWKS (valid, expired, wrong issuer/audience, `anon`/`service_role` role, `HS256`, unknown `kid`); one manual smoke test with a real Google account through the cloud Supabase project.
- **Supabase exposure check** (manual, after any change to Data API settings): the publishable key cannot read any `app` table through the Data API.

## Linters, formatters, typing

| Language | Tools |
|---|---|
| Python 3.12 | `ruff` (lint + format), `mypy --strict` (or pyright strict) with SQLAlchemy 2 typed models, `pytest`, `pytest-cov` (domain ≥ 95 %, use cases ≥ 85 %) |
| TS | `typescript` strict, `eslint` (typescript-eslint, react-hooks, expo config), `prettier` + `prettier-plugin-tailwindcss`, `vitest`/`jest-expo` |
| Repo | `pre-commit` (ruff, prettier, gitleaks), conventional commits, Renovate |

## CI/CD (GitHub Actions)

| Workflow | Trigger | Jobs |
|---|---|---|
| `ci.yml` | PR, push to main | path-filtered: **domain** (TS + Py + parity vectors), **api** (ruff, mypy, pytest with Postgres service, migrations check, OpenAPI diff), **mobile** (tsc, eslint, vitest), **api-contract** (export OpenAPI and fail if `packages/api-client/openapi.json` or the generated `schema.d.ts` is stale), gitleaks |
| `db-backup.yml` | weekly cron (Mondays) + manual | `supabase db dump` (roles, schema, data) → gpg-encrypted artifact, 60-day retention |
| `mobile-preview.yml` | manual | `eas build --profile preview` (APK, installed directly) |
| `e2e.yml` | before release | Maestro on a local emulator (Maestro Cloud is paid) |
| `nightly.yml` | cron | random parity vectors with a new seed, dependency audit |

The API deploys automatically from `main` once `ci.yml` passes (Render `autoDeployTrigger: checksPass`). Migrations run in the Render build. There is no staging environment and no tag-based release.

## Definition of done (any task)
- Tests for new behaviour (property tests for anything touching money).
- Types and lint clean.
- OpenAPI/TS client updated if the API changed (`pnpm api:openapi`, commit `packages/api-client`).
- Docs in `/docs` updated when a rule changes.
- Accessibility check for new UI (labels, touch targets, font scale 200 %).
