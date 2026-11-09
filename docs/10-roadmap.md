# 10 — Roadmap

Estimates assume **1 full-stack developer** (≈ 1.6× faster with 2). "w" = working weeks. Each task (`T-x.y`) is sized to become one issue/prompt: it states its goal and acceptance criteria (AC).

```mermaid
gantt
  dateFormat  YYYY-MM-DD
  axisFormat  %b
  section Foundations
  P0 Foundations & spikes        :p0, 2026-11-16, 14d
  P1 Money domain (TS+Py)        :p1, after p0, 11d
  section Parallel tracks
  P2 Quick splits (client-only)  :p2, after p1, 14d
  P3 Auth, households, categories:p3, after p1, 14d
  section Household core
  P4 Expenses, rules, balance    :p4, after p3, 21d
  P5 Close, settlement, history  :p5, after p4, 18d
  P6 Google Sheets               :p6, after p5, 11d
  P7 MVP hardening & release     :p7, after p6, 14d
```

**MVP ≈ 14–16 weeks** for one developer (P2 overlaps when a second person is available; otherwise P2 can ship right after P1 as an early public release).

## P0 — Foundations and spikes (2 w)

| Task | AC |
|---|---|
| T-0.1 Monorepo scaffold (pnpm workspaces, uv, folders per [11](11-repo-structure.md)) | `pnpm i` and `uv sync` work; `pnpm db:up` starts the local Supabase stack; `pnpm api:dev` connects to it |
| T-0.2 CI skeleton | ci.yml runs lint/type/test for empty packages; gitleaks; branch protection |
| T-0.3 **UI stack spike** on Expo SDK 58: NativeWind 4.2 + Tailwind 3 + React Native Reusables (Button, Dialog, Select, Tabs), dark mode, font scaling | Dev build on a real Android device; decision recorded (go / fallback SDK 57 / Uniwind) in [13](13-design-system.md) |
| T-0.4 **Google sign-in spike** (Universal Sign-In vs free Credential Manager lib) → `supabase.auth.signInWithIdToken` + FastAPI JWKS verification | Real device signs in to the Supabase project; a FastAPI endpoint accepts the Supabase token and rejects anon/expired ones; library choice + licence cost recorded |
| T-0.5 FastAPI skeleton: settings, structlog, Sentry, `/healthz` `/readyz`, SQLAlchemy 2 async session, Alembic init, Procrastinate worker hello-job | Tests green; worker processes a job from a DB row |
| T-0.6 Supabase prod project (Frankfurt, **Free plan**; Google provider; `app` schema, `split_api` role, Data API not exposing `app`) + Render Free web service (`render.yaml`: API + in-process worker) + EAS project (`development`/`preview`) + daily backup workflow | URL responds and reaches the DB via the shared pooler; in-process worker receives NOTIFY via session mode; preview APK installs; backup artifact produced |

Risks: version incompatibilities (mitigated by spikes and pinning).

## P1 — Money domain (1.5 w)

| Task | AC |
|---|---|
| T-1.1 `allocate` in Python and TS | All vectors in `allocate.json` pass in both; property tests green |
| T-1.2 `resolve_shares` (all split types, subsets, fallback) | Vectors + properties; examples from [03](03-business-rules.md) reproduced exactly |
| T-1.3 `settle` (greedy, deterministic) | Vectors + properties; household and quick-split examples reproduced |
| T-1.4 Money parse/format helpers (es-ES) | `"1.234,56"`, `"12,5"`, `"12.50"` parsed; invalid inputs rejected |
| T-1.5 Random vector generator + nightly parity job | CI fails on any divergence |

## P2 — Quick splits (2 w) — independent module

Depends only on P1 (+ P0 UI). Can ship before or in parallel with P3–P5.

| Task | AC |
|---|---|
| T-2.1 Local store (Zustand + MMKV) for quick events | Events survive app restart; no network calls |
| T-2.2 Mode 1 UI (total, participants, weights/exclude, optional payer) | 87,50 € example gives 21,88/21,88/21,87/21,87 and correct transfers |
| T-2.3 Mode 2 UI (itemised expenses) | Trip example from [03](03-business-rules.md) reproduced |
| T-2.4 Share as text (WhatsApp) | Text format as specified; uses `Share` API |
| T-2.5 Access without login from sign-in screen | Fresh install → Quick splits usable offline in airplane mode |
| T-2.6 (after P3) Save/sync to account: `PUT /quick-events/{id}` + server recompute | Server rejects tampered shares; list of saved events |

## P3 — Auth, households, categories (2 w)

| Task | AC |
|---|---|
| T-3.1 `get_actor` dependency (JWKS cache, claim checks) + `ensure_user` + `GET/PATCH /me` | Unit tests with locally signed ES256 test tokens: valid, expired, wrong `iss`/`aud`, `anon` role, `HS256`; first call creates `app.users` |
| T-3.2 Supabase config as code (`supabase/config.toml` for local; documented dashboard settings for the cloud project: only Google provider, anonymous sign-ins off, token lifetime) | Fresh local stack reproduces the config; checklist ticked for the cloud project |
| T-3.3 App auth flow (sign-in screen, `signInWithGoogle` → Supabase, encrypted MMKV session storage, AppState auto-refresh, Stack.Protected) | Kill app → reopen stays signed in; sign-out → back to sign-in; expired token transparently refreshed |
| T-3.4 Households + members + roles + default categories | Create household → admin; 12 default categories copied |
| T-3.5 Invitations (code + App Link, start_period) | Second device joins via WhatsApp link; expired/exhausted handled |
| T-3.6 Tenant-isolation test harness | Every household route returns 404 for outsiders |
| T-3.7 Categories CRUD + archive (admin) | Archived categories hidden from pickers but kept on old expenses |

## P4 — Expenses, rules, live balance (3 w)

| Task | AC |
|---|---|
| T-4.1 Periods (numbered, started and closed by hand; one open at a time) | New expenses land in the open period whatever their date; none open → `409 no_open_period` |
| T-4.2 Split rules: household default + category rules (API + admin UI) | 60/40 rule must sum 100 %; live validation |
| T-4.3 `create_expense` use case + revisions + idempotency | Shares persisted; revision v1; replay with same key returns same response |
| T-4.4 Update/delete in open period with If-Match | Stale version → 412 with current data; UI shows conflict sheet |
| T-4.5 Expense form (amount keypad, category chips, payer, date, split section with live preview using the TS domain) | Preview equals server shares in 100 % of vector cases |
| T-4.6 Expense list (FlashList, filters, cursor pagination) + detail + history | 1 000 expenses scroll smoothly on a mid-range device |
| T-4.7 Live balance endpoint + home card | Σ nets = 0; matches the household example |
| T-4.8 Personal expenses (split type) | Excluded from balance and totals |
| T-4.9 Offline create queue (MVP offline) | Airplane mode → create → reconnect → exactly one expense |

## P5 — Period close, settlement, history (2.5 w)

| Task | AC |
|---|---|
| T-5.1 `close_period` + snapshot + transfers (admin early close) | Snapshot seq 1, pending transfers equal greedy result |
| ~~T-5.2 Auto-close periodic job~~ (dropped 2026-11-09: members close periods by hand) → T-5.2 Start next period | Any member starts it after the latest one closed; two at once → one wins |
| T-5.3 Transfers: sent / confirm / dispute + period → settled | State machine tests; only creditor confirms |
| T-5.4 Edit after close (reason, new snapshot, cancel pending) | Diff old vs new nets shown; Σ nets 0 |
| T-5.5 Lock on first sent/confirmed + adjustments (reversal + correction) | Correction example from [03](03-business-rules.md) produces +20/−10/−10 in April |
| T-5.6 Reopen (admin, only unlocked) | Locked → 409 |
| T-5.7 Membership changes (join current/next, leave at period end) | Join with `current` re-resolves only `participant_mode='all'` expenses |
| T-5.8 Period screen UI (timeline, balances, transfers, snapshot diff) | Usable at font scale 200 % |

## P6 — Google Sheets (1.5 w)

| Task | AC |
|---|---|
| T-6.1 Service account + user-owned spreadsheet shared with it as Editor (runbook in `infra/README.md`) | Service account can write a cell in the spreadsheet |
| T-6.2 `ensure_household_spreadsheet` (verify access, write `Léeme`) | Missing share → clear error state, no crash |
| T-6.3 Pure renderer for the 4 tabs + content hash | Snapshot tests |
| T-6.4 `sync_period_tab` with backoff and error states | Simulated 429 → retries and succeeds; unchanged hash → no API calls |
| T-6.5 Triggers: period close and edit after close only (already enqueued by `write_snapshot`) | Edit after close updates only that period's tabs; the open period is never written |
| T-6.6 Sheets status in app settings | Shows last sync / error |

## P7 — MVP hardening and release (2 w)

| Task | AC |
|---|---|
| T-7.1 Privacy policy, account deletion (in-app + web URL), data export | Play Console data-safety form completed |
| T-7.2 Sentry release tracking (API + mobile source maps) | Errors show readable stacks |
| T-7.3 Maestro E2E: sign-in (test account), create household, add expenses, close, settle | Green in CI |
| T-7.4 Prod environment (free tiers; restore drill of the GitHub Actions backup into the local stack) | Restore tested |
| T-7.5 APK installed directly on both phones (no Play Store) | 1 full period cycle (start, expenses, close, settle) run with real data |
| T-7.6 Accessibility & i18n pass (es/en) | Checklist in [13](13-design-system.md) passes |

## Post-MVP — ordered by value / effort

| # | Feature | Value | Effort | Notes / dependencies |
|---|---|---|---|---|
| 1 | **Push notifications** (new/edited expense, close reminder, transfer sent/pending) | High | S (1 w) | Needed by several features below |
| 2 | **Recurring expenses** with own split rules | High | M (1.5 w) | Daily job creates expenses on `day_of_month`, `source='recurring'`; skip if already created (unique `(recurring_id, period)`) |
| 3 | **Payment button** (Bizum copy+open bank, PayPal.me, Revolut) | High | S (1 w) | Also for Quick splits |
| 4 | **Private expenses visibility** (fully hidden from others) | Medium | S (0.5 w) | Split type already exists |
| 5 | **Multi-household UI** (switcher) | Medium | S (0.5–1 w) | Data model ready |
| 6 | **Budgets** per category + alerts | Medium | M (1.5 w) | Needs push |
| 7 | **Charts, month-over-month, CSV/PDF export** | Medium | M (1.5 w) | victory-native; PDF server-side (WeasyPrint) or `expo-print` |
| 8 | **Quick-split share link + image** | Medium | S (1 w) | Public read-only page |
| 9 | **Comments/reactions + optional approval flow** | Low-Med | M (1.5 w) | Approval = expense `status='pending_approval'` before entering balance |
| 10 | **Full offline sync** | Medium | L (3 w) | Outbox, change feed, conflict UI |
| 11 | **Home-screen widget / quick add** | Low-Med | M (1.5 w) | Android widget via `react-native-android-widget`; App Shortcuts (long-press icon → "Nuevo gasto") is a cheap first step |
| 12 | **AI phase** | High (differentiator) | L | See [07](07-future-ai.md); after recurring + push |
| — | iOS | — | M | Sign in with Apple, APNs via Expo, store review |

## Dependencies summary
P1 → P2, P3 · P3 → P4 → P5 → P6 → P7 · Push → Budgets alerts, reminders · Recurring → AI (common use case).

## Main risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| UI library churn (NativeWind v5 RC, SDK 58 new) | Medium | Medium | Spike T-0.3, pin versions, Reusables supports NativeWind and Uniwind |
| Google Sign-In library/licensing | Medium | Medium | Spike T-0.4, abstraction layer |
| Sheets quotas/ownership | Low | Low (non-blocking) | User-owned file shared with the service account, closed periods only, hashes |
| Free-tier limits (Render cold start, Supabase pause, no managed backups) | Medium | Medium | In-process worker + stalled-job retry, daily backup job doubles as activity, resume runbook (`infra/README.md`) |
| Rules complexity confuses users | Medium | High | Show "why this split" (`split_origin`) everywhere; sensible defaults |
| Edits after close / adjustments misunderstood | Medium | Medium | Diff UI, clear copy, E2E tests |
| Solo developer bandwidth | High | High | Strict phase gates; Quick splits as early release to validate UI stack |
