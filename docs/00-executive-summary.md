# 00 — Executive summary

> Status: planning. Last research pass: 2026-11-07. Library versions quoted here were checked on that date; re-verify at the start of each phase.

## Vision

Split Ranch makes shared household money boring: everyone logs what they pay during the month, the app knows how each expense is split, and at month end it tells each person exactly who pays whom, with as few transfers as possible. A mirror in Google Sheets gives the household a familiar, read-only view.

A second, independent tool — **Quick splits** — solves the dinner/trip case: split a bill with people who don't have the app, offline, without logging in.

## Scope

### MVP
- Google sign-in (Android) through **Supabase Auth**; the FastAPI backend verifies Supabase access tokens.
- Households, invitations by code/link, roles (admin/member). The data model supports several households per user from day one; the household switcher UI is post-MVP.
- Categories (defaults + custom).
- Expense CRUD with split rules: equal, weights/percentages, exact amounts, single person (not split), personal (excluded from settlement). Subset of members per expense.
- Rule precedence: expense override → category/recurring rule → household default.
- Live balance, automatic month-end close (with grace days), settlement with minimal transfers, transfer confirmation by the receiver.
- Change history (revisions, soft delete, optimistic locking, settlement snapshots).
- Automatic Google Sheets export per household.
- **Quick splits** (modes 1 and 2), computed locally, shareable as text.

### Post-MVP (ordered in [10-roadmap.md](10-roadmap.md))
Recurring expenses, push notifications, payment button, budgets with alerts, comments/reactions/approval, private-expense visibility, multi-household UI, PDF/CSV export and charts, home-screen widget, full offline sync.

### Out of scope
Receipt photos/attachments and OCR (dropped by the product owner, 2026-11-07), multi-currency (only the `currency` column exists, always `EUR`), iOS (architecture keeps the door open), AI features (architecture only — see [07](07-future-ai.md)).

## Key decisions

| Area | Decision | Why (short) |
|---|---|---|
| Architecture | **Modular monolith**: one FastAPI service + one worker process | Small team; one deploy unit; clear module boundaries instead of microservices |
| Business logic | **Use-case layer** (`create_expense`, `close_period`, …) called by REST routers today and AI tools later | Single place for rules, authz and auditing |
| Money | Integer **cents**; own `allocate` using the **largest remainder method** with deterministic tie-break, implemented in TS and Python, verified by **shared JSON test vectors** | Sum of parts always equals total; identical results on client and server |
| Shared domain | Pure `money` + `split` + `settle` modules with no DB/framework imports, in both languages | Reused by household, Quick splits (client, offline) and backend |
| Mobile | Expo SDK **58** (RN 0.88, New Architecture only), Expo Router, TypeScript strict | Current stable; file-based routing; EAS |
| UI | **NativeWind 4.2 (Tailwind v3) + React Native Reusables**, with a planned upgrade to NativeWind v5 / Tailwind v4 once stable; Uniwind as fallback | NativeWind v5 is still RC (5.0.0-rc.1, 2026-11-02); Reusables supports both NativeWind and Uniwind |
| Client data | TanStack Query (server state) + Zustand (UI/session state) + React Hook Form + Zod | Standard, small, well-typed |
| Backend | FastAPI, SQLAlchemy **2.0.x** (pin; 2.1 just reached RC/final — upgrade deliberately), Alembic, Pydantic v2, Python 3.12 | As requested |
| DB | **Supabase Postgres** (Frankfurt, `eu-central-1`), our tables in a private `app` schema managed by Alembic | Source of truth; same provider as auth; the Supabase Data API is not used |
| Jobs | **Procrastinate** (Postgres-backed queue) instead of Celery + Redis | Transactional enqueue (job is created in the same transaction as the period close), periodic tasks, retries; one less infrastructure piece. Celery/Dramatiq remain options if volume grows |
| Auth | **Supabase Auth**: native Google ID token (Credential Manager on Android) → `supabase.auth.signInWithIdToken` → Supabase session (access + refresh handled by `supabase-js`). FastAPI verifies the Supabase JWT locally against the project JWKS (asymmetric keys) | No token issuing/rotation code of our own; Apple sign-in later is configuration. Legacy Google Sign-In on Android is deprecated, so a Credential Manager library is still needed |
| Sheets | Google Sheets + Drive API with a service account **writing into a Shared Drive** (requires a Google Workspace account owned by the project) | Service accounts have no Drive storage of their own and cannot own files in "My Drive" |
| Push | Expo Push Service (FCM v1 credentials via EAS) | Simple, free, iOS-ready |
| Hosting | **Supabase** (Postgres + Auth, Frankfurt) + **Render, Frankfurt** for the FastAPI web service and the worker (Supabase cannot run a Python service) | Two managed EU providers, no database to operate; Fly.io as alternative for the Python processes |
| CI/CD | GitHub Actions + EAS Build/Submit/Update; Render auto-deploy from `main` (staging) and tags (prod); Alembic migrations against the Supabase project before deploy | Low ops |
| Observability | Sentry (mobile + API, EU data region), structured JSON logs (structlog) | Fast feedback with little setup |

## Decisions taken with the product owner (2026-11-07)
- **Period close is automatic**: at 00:00 (household time zone) on day 1 + `grace_days` (default 3) the previous period closes. Admins may close earlier or reopen. The **receiver confirms** each transfer.
- **Membership is evaluated per full month**: whoever belongs to the household during a period participates in that period's default splits. Leaving takes effect at the end of the current period. See [03](03-business-rules.md#membership-changes) and the trade-offs in [12](12-open-questions.md).
- **Hosting**: simple PaaS in the EU.
- **Documentation language**: English.
- **Supabase** for authentication and the database (replaces own JWT issuing and Render Postgres).
- **No receipt photos** (no file storage needed).

## Assumptions
1. Households are small (2–8 members); a few hundred expenses per month at most.
2. Members are adults with a Google account; Spain is the primary market (EUR, Spanish locale, Bizum culture).
3. The app UI will be Spanish first, with i18n in place from day one (English second).
4. One project-owned Google Workspace account is acceptable (≈ €7/month) to host the Shared Drive for spreadsheets.
5. No regulated payment flows: the app never moves money, it only calculates and records.

## Critical review of the original brief (summary)
- **Celery + Redis** is more than needed: Procrastinate gives transactional, idempotent job creation on the database we already run. Redis can be added later for rate limiting/caching.
- **Service-account-owned spreadsheets** no longer work reliably (zero Drive quota). Use a Shared Drive, or alternatively let a household admin connect their own Google account with the `drive.file` scope. See [06](06-google-sheets.md).
- **Bizum has no public P2P API or deep link with a pre-filled amount.** The "pay" button becomes "copy amount + phone, open your bank app", plus real pre-filled links for providers that support them (e.g. PayPal.me). See [03](03-business-rules.md#payment-button).
- **Editing a closed period after partial payments**: model transfers as ledger entries so a recalculation yields residual transfers; keep the "freeze + adjustment in next period" rule as the product behaviour. See [03](03-business-rules.md#critical-review-of-the-edit-model).
- **"Full month" membership** retroactively changes default splits when someone joins mid-month. Offer "starts this month / starts next month" at join time. See [12](12-open-questions.md).
- **Settlement minimisation** is NP-hard in the exact sense; a deterministic greedy algorithm guarantees at most _n − 1_ transfers, which is optimal enough for households. An exact solver for _n ≤ 10_ is optional.

## Top risks
1. NativeWind/Expo SDK version churn (v5 RC, SDK 58 just out) → Phase 0 spike, pinned versions.
2. Google Sign-In library landscape (legacy API deprecated; the maintained Credential Manager option of `react-native-google-signin` is paid) → spike and thin abstraction. Supabase does not remove this: it consumes the ID token the native library returns.3. Google Sheets quotas (60 writes/min per user; a service account counts as one user) → batching, one `batchUpdate` per tab, queue throttling.
4. Edits after close producing confusing results → strict state machine, snapshots and clear UI diffs.
5. Scope creep across many post-MVP features → strict phase gates.
6. Supabase specifics: its Data API must not expose our tables (private schema), the worker needs a session-mode or direct connection for LISTEN/NOTIFY, and free projects pause after a week of inactivity (run staging and prod on the Pro plan).
