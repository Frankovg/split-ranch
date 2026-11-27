# 00 — Executive summary

> Status: API and Android app implemented (groups without periods since 2026-11-17). Last research pass: 2026-11-07. Library versions quoted here were checked on that date; re-verify at the start of each phase.

## Vision

Splitranch makes shared money boring: people in a group (a flat, a trip, a couple) log what they pay, the app knows how each expense is split, and at any time it shows each person's running balance and who should pay whom, with as few payments as possible. There are no periods: "how much did we spend last month" is a date filter.

A second, independent tool — **Quick splits** — solves the dinner/trip case: split a bill with people who don't have the app, offline, without logging in.

## Scope

### MVP
- Google sign-in (Android) through **Supabase Auth**; the FastAPI backend verifies Supabase access tokens.
- Groups: a user creates or joins several groups (switcher in the app), one invitation code per group typed by hand. All members have the same rights; the admin (the creator) is the only one who removes members and deletes the group.
- Categories (defaults + custom).
- Expense CRUD with split rules: equal, weights/percentages, exact amounts, single person (not split), personal (excluded from settlement). Subset of members per expense.
- Rule precedence: expense override → category rule → group default.
- One running balance per group (no periods, decided 2026-11-16), suggested payments with the greedy settle, payments recorded by the debtor and confirmed by the receiver. Expense list grouped by day with month filters and totals.
- Change history (one append-only `history` table, soft delete, optimistic locking).
- Automatic Google Sheets export per group.
- **Quick splits** (modes 1 and 2), computed locally, shareable as text.

### Post-MVP (ordered in [10-roadmap.md](10-roadmap.md))
Full offline sync. Push notifications and the multi-group UI, first planned here, are already built.

### Out of scope
Receipt photos/attachments and OCR (dropped by the product owner, 2026-11-07), recurring expenses, hiding `personal` expenses from other members, category budgets with alerts, the Quick-split result as an image, comments/reactions and an approval flow on expenses, a home-screen widget or "Nuevo gasto" app shortcut, and CSV/PDF export or charts beyond the Insights screen (all dropped 2026-11-26; a later export goes through Google Sheets), multi-currency (only the `currency` column exists, always `EUR`), iOS (architecture keeps the door open), AI features (architecture only — see [07](07-future-ai.md)).

## Key decisions

| Area | Decision | Why (short) |
|---|---|---|
| Architecture | **Modular monolith**: one FastAPI service (no background worker) | Small team; one deploy unit; clear module boundaries instead of microservices |
| Business logic | **Use-case layer** (`create_expense`, `record_payment`, …) called by REST routers today and AI tools later | Single place for rules, authz and auditing |
| Money | Integer **cents**; own `allocate` using the **largest remainder method** with deterministic tie-break, implemented in TS and Python, verified by **shared JSON test vectors** | Sum of parts always equals total; identical results on client and server |
| Shared domain | Pure `money` + `split` + `settle` modules with no DB/framework imports, in both languages | Reused by group, Quick splits (client, offline) and backend |
| Mobile | Expo SDK **58** (RN 0.88, New Architecture only), Expo Router, TypeScript strict | Current stable; file-based routing; EAS |
| UI | **NativeWind 4.2 (Tailwind v3) + React Native Reusables**, with a planned upgrade to NativeWind v5 / Tailwind v4 once stable; Uniwind as fallback | NativeWind v5 is still RC (5.0.0-rc.1, 2026-11-02); Reusables supports both NativeWind and Uniwind |
| Client data | TanStack Query (server state) + Zustand (UI/session state) + React Hook Form + Zod | Standard, small, well-typed |
| Backend | FastAPI, SQLAlchemy **2.0.x** (pin; 2.1 just reached RC/final — upgrade deliberately), Alembic, Pydantic v2, Python 3.12 | As requested |
| DB | **Supabase Postgres** (Frankfurt, `eu-central-1`), our tables in a private `app` schema managed by Alembic | Source of truth; same provider as auth; the Supabase Data API is not used |
| Background jobs | **None**: everything happens inside the request | Nothing the app does needs work outside a request. A feature that does (Sheets sync, push) first uses a FastAPI background task |
| Auth | **Supabase Auth**: native Google ID token (Credential Manager on Android) → `supabase.auth.signInWithIdToken` → Supabase session (access + refresh handled by `supabase-js`). FastAPI verifies the Supabase JWT locally against the project JWKS (asymmetric keys) | No token issuing/rotation code of our own; Apple sign-in later is configuration. Legacy Google Sign-In on Android is deprecated, so a Credential Manager library is still needed |
| Sheets | Google Sheets API with a service account **editing a spreadsheet owned by the group admin**, who shares it with the service account; export design pending (it was built around closed periods; a monthly export replaces it) | Service accounts have no Drive storage of their own, but they can edit a file a person owns; free, no Workspace |
| Push | Expo Push Service (FCM v1 credentials via EAS) | Simple, free, iOS-ready |
| Hosting | **Free tiers only (€0/month)**: **Supabase Free** (Postgres + Auth, Frankfurt) + one **Render Free** web service in Frankfurt running FastAPI (Supabase cannot run a Python service) | One group of two people; no staging environment. Trade-offs (cold starts, project pausing, no managed backups) are covered in `infra/README.md` |
| CI/CD | GitHub Actions + EAS Build/Update; Render auto-deploy from `main` when CI passes, with Alembic migrations in the build; weekly encrypted DB dump in GitHub Actions | Low ops, no cost |
| Observability | Sentry (mobile + API, EU data region), structured JSON logs (structlog) | Fast feedback with little setup |

## Decisions taken with the product owner (2026-11-07)
- **No periods** (decided 2026-11-16, replaces the manual close of 2026-11-09): one running balance per group from its creation; members settle whenever they want by recording payments, which count once the **receiver confirms** them. Any member edits any expense at any time; `history` records who changed what. See [egm/design_draft.md](egm/design_draft.md).
- **Membership**: joining never re-splits existing expenses; leaving (or being removed) needs a zero balance; the admin role passes to the next member when the admin leaves.
- **Hosting**: simple PaaS in the EU.
- **Documentation language**: English.
- **Supabase** for authentication and the database (replaces own JWT issuing and Render Postgres).
- **No receipt photos** (no file storage needed).

## Assumptions
1. Groups are small (2–8 members); a few hundred expenses per month at most.
2. Members are adults with a Google account; Spain is the primary market (EUR, Spanish locale).
3. The app UI will be Spanish first, with i18n in place from day one (English second).
4. No paid services (decided 2026-11-09): the app is for the developer's own group, so every provider runs on its free tier.
5. No regulated payment flows: the app never moves money, it only calculates and records.

## Critical review of the original brief (summary)
- **A job queue** (and Redis) is more than needed: no feature runs work outside a request.
- **Service-account-owned spreadsheets** no longer work reliably (zero Drive quota). The group admin owns the spreadsheet and shares it with the service account. See [06](06-google-sheets.md).
- **No payment-platform integration** (decided 2026-11-10): people pay each other outside the app (Bizum, cash, bank transfer…) and the app only records it — the debtor records a payment "sent" and the creditor confirms. See [03](03-business-rules.md#7-payments-outside-the-app).
- **Editing old expenses after payments** changes today's balance by the difference (accepted: no locks or adjustments; `history` shows the change). See [03 §4](03-business-rules.md#4-editing-expenses).
- **Joining mid-way** only affects expenses created afterwards, so nobody's past shares change when someone joins.
- **Settlement minimisation** is NP-hard in the exact sense; a deterministic greedy algorithm guarantees at most _n − 1_ payments, which is optimal enough for groups. An exact solver for _n ≤ 10_ is optional.

## Top risks
1. NativeWind/Expo SDK version churn (v5 RC, SDK 58 just out) → Phase 0 spike, pinned versions.
2. Google Sign-In library landscape (legacy API deprecated; the maintained Credential Manager option of `react-native-google-signin` is paid) → spike and thin abstraction. Supabase does not remove this: it consumes the ID token the native library returns.3. Google Sheets quotas (60 writes/min per user; a service account counts as one user) → batching, one `batchUpdate` per tab, queue throttling.
4. Edits to old expenses moving balances people already paid against → `history` with author and before/after, "edited by" on the expense, and the confirmed balance shown separately from pending payments.
5. Scope creep across many post-MVP features → strict phase gates.
6. Supabase specifics: its Data API must not expose our tables (private schema), migrations need a session-mode connection, and Free projects pause after a week of low activity and have no backups (regular use plus a weekly backup job; resume from the dashboard if it pauses).
