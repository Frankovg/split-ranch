# Infra and cloud setup

Everything here needs accounts owned by the project, so it is done by a person, once per environment.
Tick each item for **staging** and **prod**.

## 1. Google Cloud (project `split-ranch`)
- [ ] OAuth consent screen (External, app name, privacy policy URL, scopes `openid email profile`).
- [ ] OAuth client **Web** → its client ID/secret go to Supabase's Google provider and to `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`.
- [ ] OAuth client **Android** per signing key: package `com.splitranch.app` + SHA-1 of the EAS dev, preview and production keystores (`eas credentials`).
- [ ] Enable Sheets API and Drive API; create service account `sheets-writer`; download JSON key → base64 → `GOOGLE_SERVICE_ACCOUNT_JSON_B64` (Render secret).
- [ ] Google Workspace (Business Starter): create Shared Drive "Split Ranch Households", add the service account as Content manager, allow external sharing → `GOOGLE_SHARED_DRIVE_ID`.

## 2. Supabase (organisation on Pro plan; projects `split-ranch-staging`, `split-ranch-prod`, region Frankfurt `eu-central-1`)
- [ ] Auth → Providers: **Google only** (client ID = Web client ID; also add the Android client ID to "Authorized Client IDs"); email, phone and anonymous sign-ins **off**; nonce check on.
- [ ] Auth → JWT: asymmetric signing keys (ES256) active; access token expiry 3600 s.
- [ ] API settings → exposed schemas: keep `public`, `graphql_public` only (**never add `app`**).
- [ ] SQL: create role `split_api` (login, strong password, `BYPASSRLS`), grant usage/create on schema `app` to it (Alembic creates the tables). Store pooler URLs:
  - `DATABASE_URL` = transaction pooler (port 6543) as `split_api`
  - `DATABASE_URL_SESSION` = session pooler (port 5432) as `split_api`
- [ ] Copy the project URL + publishable key into EAS env (`EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`) and the secret key into Render (`SUPABASE_SECRET_KEY`, worker only).
- [ ] Prod: confirm daily backups; decide on the PITR add-on before real households onboard.
- [ ] Verify: with the publishable key, `GET {SUPABASE_URL}/rest/v1/expenses` must fail (schema not exposed).

## 3. Render (region Frankfurt)
- [ ] New Blueprint from `infra/render.yaml`; create env groups `split-ranch-staging` / `split-ranch-prod` with: `DATABASE_URL`, `DATABASE_URL_SESSION`, `SUPABASE_URL`, `SUPABASE_JWT_ISSUER` (`https://<ref>.supabase.co/auth/v1`), `SUPABASE_SECRET_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON_B64`, `GOOGLE_SHARED_DRIVE_ID`, `SENTRY_DSN`, `APP_ENV`.
- [ ] Staging auto-deploys from `main`; prod deploys from tags `api-v*` (deploy hook in GitHub secrets).

## 4. Expo / EAS
- [ ] `eas init` in `apps/mobile`, profiles `development` / `preview` / `production`.
- [ ] Upload FCM v1 service account for push (post-MVP push phase).
- [ ] Register the keystores' SHA-1 in Google Cloud (step 1).

## 5. Sentry (EU region)
- [ ] Projects `split-ranch-api` and `split-ranch-mobile`; DSNs into Render and EAS env.

## Runbooks
- **Secret rotation**: rotate in the provider, update the Render env group / EAS env, redeploy; for Supabase JWT keys use "rotate" (old key stays valid in JWKS until revoked, so the API keeps accepting live sessions).
- **Restore drill** (before launch and every 6 months): restore the latest prod backup into a scratch Supabase project, run `alembic current` and a read-only smoke test, delete the scratch project.
