# 08 — Security and privacy

## Authentication
- **Supabase Auth** owns identities and sessions: it verifies the Google ID token (with nonce) and issues access tokens (default 1 h) and refresh tokens (rotated, with reuse detection, handled by Supabase).
- Supabase project settings to apply: Google as the only enabled provider (email/password, magic link and anonymous sign-ins **disabled**), asymmetric JWT signing keys, access-token lifetime 1 h (shorten to 15–30 min if needed), refresh-token reuse interval default, "Confirm email" irrelevant for Google.
- FastAPI verifies every request token locally against the JWKS (asymmetric algorithm only, `iss`, `aud=authenticated`, `exp`, `role=authenticated`, and `is_anonymous` missing or `false`, so anonymous accounts are refused even if they were turned on in the project). Key rotation in Supabase is picked up automatically through `kid`.
- Mobile: session persisted by `supabase-js` in encrypted MMKV, key in `expo-secure-store` (Android Keystore-backed).
- Logout → `supabase.auth.signOut()`; "sign out everywhere" → `signOut({ scope: 'global' })`. Note: an already-issued access token remains valid until it expires (≤ 1 h). Acceptable for this app; if instant revocation is ever needed, the API can check a `sessions_revoked_after` timestamp per user.
- **Keys**: the publishable (anon) key is public by design and grants nothing on our data (private `app` schema + RLS with no policies). The secret/service-role key is reserved for account deletion on the server and never leaves the server.

## Authorisation (multi-tenant)
1. Every group route resolves `Membership(user_id from JWT, group_id from path)`; missing → `404`.
2. Role checks in use cases (`require_admin(actor)`), not in routers.
3. Repositories require `group_id` as a mandatory argument; there is no "get expense by id" without group scope.
4. Composite foreign keys make cross-group references impossible at the DB level (see [02](02-data-model.md)).
5. Tests: an automated **tenant-isolation test suite** iterates every group route with a user from another group and asserts 404 (generated from the OpenAPI route list, so new routes are covered automatically).
6. **Supabase Data API exposure**: the `app` schema is not listed in the exposed schemas, and every `app` table has RLS enabled with no policies. A CI/staging check calls the Data API with the publishable key and asserts it cannot reach any `app` table.
7. Later (defence in depth): real RLS policies with `SET LOCAL app.group_id` for the `split_api` role.

Permission matrix (groups without periods, 2026-11-16):

| Action | Member | Admin |
|---|---|---|
| Create, edit and delete any expense | ✓ | ✓ |
| Manage categories, split rules, group name and time zone | ✓ | ✓ |
| Get / revoke the invite code | ✓ | ✓ |
| Record a payment | as its payer (`sent`) or receiver (`confirmed`) | same |
| Confirm / dispute a payment | its receiver | its receiver |
| Cancel a payment | its payer | its payer |
| Leave the group (zero balance) | ✓ | ✓ (the role passes to the next member) |
| Remove a member (zero balance) | — | ✓ |
| Delete the group (every balance zero) | — | ✓ |

Members who left get 404 on every group route, like outsiders. Flat edit rights are a trust decision: `history` keeps the author and before/after state of every change.

## Input validation
- Pydantic v2 strict models, `extra="forbid"`, length limits on all strings, enums for every state, money as int with bounds (≤ 1 000 000 € per expense).
- Server recomputes everything derived (shares, balances); client values are hints.
- No file uploads (receipt photos are out of scope).

## Transport and platform
- HTTPS only (HSTS); Android `usesCleartextTraffic=false`.
- CORS closed (mobile only).
- Rate limiting on auth and public share endpoints.
- Dependency scanning: Dependabot/Renovate + `pip-audit` + `pnpm audit` in CI.
- No secrets in the app bundle beyond public client IDs.

## Secrets management
| Secret | Where |
|---|---|
| Supabase DB URLs (transaction + session pooler, `split_api` role), Supabase secret key (server only), Sentry DSN (server), Expo push access token `EXPO_ACCESS_TOKEN` (server) | Render environment groups per env |
| Supabase Google provider client secret | Supabase dashboard (per project) |
| EAS build-time values (Sentry auth token, Google client IDs, Supabase URL + publishable key — public, but per environment) | EAS environment variables |
| FCM v1 service account (Firebase Admin SDK key; `firebase-adminsdk.json` is git-ignored if kept locally) | EAS credentials |
| Local dev | `.env` (git-ignored); `.env.example` committed |
Rotation runbook documented in `infra/README.md` (Phase 7).

## GDPR (EU personal data)

**Roles:** the operator of Splitranch is the **data controller**. Processors: Supabase (database + authentication, Frankfurt), Render (API hosting, Frankfurt), Google (Sign-In, Sheets), GitHub (encrypted backups), Expo (push tokens), Sentry (EU region). Sign DPAs with each; list them in the privacy policy.

**Personal data processed:** name, email, avatar URL (Google), group membership, expenses (amounts, descriptions — may reveal lifestyle), push tokens, device/crash metadata, auth logs (IP, user agent — kept by Supabase). Quick-split data (including names of **non-users**) never reaches the server: it stays on the user's phone.

**Lawful bases:** contract (providing the service to members); legitimate interest (security logs, fraud/abuse prevention); consent (push notifications: the Android permission plus the in-app switches in Settings → Notifications, both off-able at any time; optional analytics). Non-user names in Quick splits: legitimate interest of the user, minimised (first names only, encouraged), never used for anything else.

**Principles applied:**
- Data minimisation: no contacts access, no location, no analytics SDK in MVP beyond Sentry (PII scrubbing on, `sendDefaultPii=false`).
- Data residency: primary data in the EU (Frankfurt); Google Sheets data lives in the group admin's personal Google Drive (no data-region guarantee; disclosed).
- Rights: **delete account** in Settings → Account (`DELETE /v1/me`, rules in [03 §5](03-business-rules.md#5-groups-and-membership)): it anonymises the member in shared groups (others' financial records stay coherent), deletes the personal profile and push tokens (Quick splits are only on the phone; uninstalling the app removes them), and deletes the Supabase auth user (which removes sessions and identities). Every other right (access, a portable copy, rectification, restriction, objection) is exercised by email to contact@franamoroso.com, answered within a month; there is no in-app export. Google Play also needs a web URL for deletion requests: not built yet (see the TODO in `PrivacyScreen.tsx`).
- Sharing to Google Sheets: explained at group creation; per-user opt-out of being shared.

**Retention (defaults):**

| Data | Retention |
|---|---|
| Group expenses, history, payments | While the group exists; deleted 30 days after group deletion |
| Left members' read access | None: members who left get 404 (their balance was zero) |
| Sessions / refresh tokens | Managed by Supabase Auth; removed on sign-out or account deletion |
| Supabase auth/API logs | Per Supabase plan retention (Free plan: short, about a day) |
| DB backups (GitHub Actions artifacts, gpg-encrypted) | 60 days |
| Logs | 30 days; Sentry 90 days |
| AI transcripts (future) | With the expense; raw audio not stored |

**Privacy policy**: the in-app screen `/privacy` (`features/legal/PrivacyScreen.tsx`, text in the i18n files, Spanish + English), linked from sign-in and Settings → Account. Controller: Franco Gabriel Amoroso, contact@franamoroso.com. The public URL for the store listing is not published yet (TODO in `PrivacyScreen.tsx`). Include a Records of Processing Activities (RoPA) entry and a lightweight DPIA note (financial-ish data, small scale → DPIA likely not mandatory, but document the assessment).

## Security checklist per release
- [ ] Tenant-isolation suite green
- [ ] Supabase Data API cannot reach `app` tables with the publishable key
- [ ] No new endpoint without auth dependency (lint rule/test)
- [ ] Dependency audit clean or accepted
- [ ] Secrets not in diff (gitleaks in CI)
- [ ] Sentry PII scrubbing verified
