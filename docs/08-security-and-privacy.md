# 08 — Security and privacy

## Authentication
- **Supabase Auth** owns identities and sessions: it verifies the Google ID token (with nonce) and issues access tokens (default 1 h) and refresh tokens (rotated, with reuse detection, handled by Supabase).
- Supabase project settings to apply: Google as the only enabled provider (email/password, magic link and anonymous sign-ins **disabled**), asymmetric JWT signing keys, access-token lifetime 1 h (shorten to 15–30 min if needed), refresh-token reuse interval default, "Confirm email" irrelevant for Google.
- FastAPI verifies every request token locally against the JWKS (asymmetric algorithm only, `iss`, `aud=authenticated`, `exp`, `role=authenticated`). Key rotation in Supabase is picked up automatically through `kid`.
- Mobile: session persisted by `supabase-js` in encrypted MMKV, key in `expo-secure-store` (Android Keystore-backed).
- Logout → `supabase.auth.signOut()`; "sign out everywhere" → `signOut({ scope: 'global' })`. Note: an already-issued access token remains valid until it expires (≤ 1 h). Acceptable for this app; if instant revocation is ever needed, the API can check a `sessions_revoked_after` timestamp per user.
- **Keys**: the publishable (anon) key is public by design and grants nothing on our data (private `app` schema + RLS with no policies). The secret/service-role key is used only by the worker for account deletion and never leaves the server.

## Authorisation (multi-tenant)
1. Every household route resolves `Membership(user_id from JWT, household_id from path)`; missing → `404`.
2. Role checks in use cases (`require_admin(actor)`), not in routers.
3. Repositories require `household_id` as a mandatory argument; there is no "get expense by id" without household scope.
4. Composite foreign keys make cross-household references impossible at the DB level (see [02](02-data-model.md)).
5. Tests: an automated **tenant-isolation test suite** iterates every household route with a user from another household and asserts 404 (generated from the OpenAPI route list, so new routes are covered automatically).
6. **Supabase Data API exposure**: the `app` schema is not listed in the exposed schemas, and every `app` table has RLS enabled with no policies. A CI/staging check calls the Data API with the publishable key and asserts it cannot reach any `app` table.
7. Later (defence in depth): real RLS policies with `SET LOCAL app.household_id` for the `split_api` role.

Permission matrix (MVP):

| Action | Member | Admin |
|---|---|---|
| Create expense | ✓ | ✓ |
| Edit/delete own expense | ✓ | ✓ |
| Edit/delete others' expenses | — | ✓ |
| Manage categories, rules, invitations, roles, settings | — | ✓ |
| Close early / reopen period | — | ✓ |
| Mark transfer sent | debtor | debtor |
| Confirm/dispute transfer | creditor | creditor; admin only if creditor left (with note) |

## Input validation
- Pydantic v2 strict models, `extra="forbid"`, length limits on all strings, enums for every state, money as int with bounds (≤ 1 000 000 € per expense).
- Server recomputes everything derived (shares, balances); client values are hints.
- No file uploads (receipt photos are out of scope).

## Transport and platform
- HTTPS only (HSTS); Android `usesCleartextTraffic=false`.
- CORS closed (mobile only) except the public quick-event page.
- Rate limiting on auth and public share endpoints.
- Dependency scanning: Dependabot/Renovate + `pip-audit` + `pnpm audit` in CI.
- No secrets in the app bundle beyond public client IDs.

## Secrets management
| Secret | Where |
|---|---|
| Supabase DB URLs (transaction + session pooler, `split_api` role), Supabase secret key (worker only), Google service-account JSON, Sentry DSN (server) | Render environment groups per env |
| Supabase Google provider client secret | Supabase dashboard (per project) |
| EAS build-time values (Sentry auth token, Google client IDs, Supabase URL + publishable key — public, but per environment) | EAS environment variables |
| FCM v1 service account | EAS credentials |
| Local dev | `.env` (git-ignored); `.env.example` committed |
Rotation runbook documented in `infra/README.md` (Phase 7).

## GDPR (EU personal data)

**Roles:** the operator of Split Ranch is the **data controller**. Processors: Supabase (database + authentication, Frankfurt), Render (API/worker hosting, Frankfurt), Google (Sign-In, Sheets), GitHub (encrypted backups), Expo (push tokens), Sentry (EU region). Sign DPAs with each; list them in the privacy policy.

**Personal data processed:** name, email, avatar URL (Google), household membership, expenses (amounts, descriptions — may reveal lifestyle), optional payment handles (phone for Bizum), push tokens, device/crash metadata, auth logs (IP, user agent — kept by Supabase). Quick-split participant names of **non-users** (stored only if the owner saves/shares the event).

**Lawful bases:** contract (providing the service to members); legitimate interest (security logs, fraud/abuse prevention); consent (push notifications, optional analytics). Non-user names in Quick splits: legitimate interest of the user, minimised (first names only, encouraged), never used for anything else.

**Principles applied:**
- Data minimisation: no contacts access, no location, no analytics SDK in MVP beyond Sentry (PII scrubbing on, `sendDefaultPii=false`).
- Data residency: primary data in the EU (Frankfurt); Google Sheets data lives in the household admin's personal Google Drive (no data-region guarantee; disclosed).
- Rights: in-app **export my data** (JSON/CSV, async job) and **delete account** (required by Google Play too, with a web URL for deletion requests). Deletion anonymises the member in shared households (others' financial records stay coherent), deletes the personal profile, push tokens and Quick-split events owned by the user, and finally deletes the Supabase auth user (which removes sessions and identities).
- Sharing to Google Sheets: explained at household creation; per-user opt-out of being shared.

**Retention (defaults):**

| Data | Retention |
|---|---|
| Household expenses, revisions, snapshots | While the household exists; deleted 30 days after household deletion |
| Left members' read access | Until household deletion |
| Sessions / refresh tokens | Managed by Supabase Auth; removed on sign-out or account deletion |
| Supabase auth/API logs | Per Supabase plan retention (Free plan: short, about a day) |
| DB backups (GitHub Actions artifacts, gpg-encrypted) | 60 days |
| Idempotency keys | 48 h |
| Logs | 30 days; Sentry 90 days |
| Quick events (saved) | Until deleted by owner; shared links expire after 90 days (configurable) |
| AI transcripts (future) | With the expense; raw audio not stored |

**Privacy policy** (Phase 7 deliverable): plain-language Spanish + English, linked in the store listing, sign-in screen and settings. Include a Records of Processing Activities (RoPA) entry and a lightweight DPIA note (financial-ish data, small scale → DPIA likely not mandatory, but document the assessment).

## Security checklist per release
- [ ] Tenant-isolation suite green
- [ ] Supabase Data API cannot reach `app` tables with the publishable key
- [ ] No new endpoint without auth dependency (lint rule/test)
- [ ] Dependency audit clean or accepted
- [ ] Secrets not in diff (gitleaks in CI)
- [ ] Sentry PII scrubbing verified
