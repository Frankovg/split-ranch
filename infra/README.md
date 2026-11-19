# Infra and cloud setup

Everything here needs accounts owned by the project, so it is done by a person, once.

**Cost target: €0/month.** Split Ranch is used by one household (two people), so there is a single
cloud environment (`prod`) on free tiers only. Development runs against the local Supabase stack
(`pnpm db:up`). The free-tier limits and what each one means for us are listed in
[Free-tier limits](#free-tier-limits).

## 1. Google Cloud (project `split-ranch`, no billing account needed)
- [ ] OAuth consent screen: External, app name, scopes `openid email profile`. Leave it in **Testing** mode and add both of your Google accounts as test users. That avoids Google's app verification, and these basic scopes do not need it anyway.
- [ ] OAuth client **Web**: its client ID and secret go to Supabase's Google provider and to `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`.
- [ ] OAuth client **Android** per signing key: package `com.splitranch.app` plus the SHA-1 of each EAS keystore you use (`eas credentials`), and the debug keystore for local dev builds. Only register keys you own. If the app is ever distributed through Google Play, also add the **Play App Signing** SHA-1, or Credential Manager returns `cancelled` after the account pick.
- [ ] Web client: no Authorized JavaScript origins, and no redirect URIs beyond what Supabase needs. Supabase accepts Google ID tokens without a nonce, so nothing else should be able to obtain ID tokens for this client.
- Google Sheets export is not built yet: no service account or spreadsheet is needed until it is (see docs/06).

## 2. Supabase (Free plan; one project `split-ranch-prod`, region Frankfurt `eu-central-1`)
- [ ] Auth → Providers: **Google only** (client ID = Web client ID; also add the Android client ID to "Authorized Client IDs"); email, phone and anonymous sign-ins **off**; nonce check on.
- [ ] Auth → JWT: asymmetric signing keys (ES256) active; access token expiry 3600 s.
- [ ] API settings → exposed schemas: keep `public`, `graphql_public` only (**never add `app`**).
- [ ] SQL: create role `split_api` (login, strong password, `BYPASSRLS`), grant usage/create on schema `app` to it (Alembic creates the tables). Use the **shared pooler** URLs. They are IPv4; the direct connection is IPv6-only on Free, and Render and GitHub Actions need IPv4:
  - `DATABASE_URL` = transaction pooler (port 6543) as `split_api`
  - `DATABASE_URL_SESSION` = session pooler (port 5432) as `split_api`
- [ ] Copy the project URL and publishable key into EAS env (`EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`), and the secret key into Render (`SUPABASE_SECRET_KEY`).
- [ ] Backups (§6): Free has no automatic or downloadable backups.
- [ ] Verify: with the publishable key, `GET {SUPABASE_URL}/rest/v1/expenses` must fail (schema not exposed).

## 3. Render (Free web service, region Frankfurt)
- [ ] New Blueprint from `infra/render.yaml`. It defines **one** web service running the API (there is no background worker). Migrations run at the end of the build, because the pre-deploy command is paid-only.
- [ ] Env group `split-ranch-prod`: `DATABASE_URL`, `DATABASE_URL_SESSION`, `SUPABASE_URL`, `SUPABASE_JWT_ISSUER` (`https://<ref>.supabase.co/auth/v1`), `SUPABASE_SECRET_KEY`, `SENTRY_DSN`, `APP_ENV=prod`, and optionally `EXPO_ACCESS_TOKEN` (Expo push security; turn on "enhanced security for push notifications" in the Expo dashboard only after this is deployed, or every push fails with `UNAUTHORIZED`).
- [ ] Deploys: automatic from `main` once CI passes (`autoDeployTrigger: checksPass`).

## 4. Expo / EAS (free tier)
- [ ] `eas init` in `apps/mobile`, profiles `development` / `preview` / `production`.
- [ ] Distribution: install the **APK** directly from the EAS build page on both phones (`preview` profile with `buildType: apk`). That skips Google Play and its one-time $25 developer fee. If the monthly free cloud builds ever run out, `eas build --local` builds on your own machine for free.
- [ ] Register the keystores' SHA-1 in Google Cloud (step 1).
- [ ] Push (post-MVP): Expo Push + FCM v1 are free; upload the FCM service account when that phase starts.

## 5. Sentry (free Developer plan, EU region, optional)
- [ ] Projects `split-ranch-api` and `split-ranch-mobile`; DSNs into Render and EAS env. If unset, Sentry stays off.

## 6. GitHub Actions: weekly backup
- [ ] Repository secrets: `SUPABASE_DB_URL` (session pooler URL as the `postgres` role) and `BACKUP_PASSPHRASE` (long random string; also keep it in your password manager, since without it the backups cannot be read).
- [ ] Run `.github/workflows/db-backup.yml` once by hand (`workflow_dispatch`) and check that the artifact appears. After that it runs every Monday and keeps 60 days of encrypted dumps (the worst case is losing up to a week of data). The dumps contain emails and every expense, so they are always encrypted, even in a private repo.

## Free-tier limits

| Service | Limit | What it means here |
|---|---|---|
| Supabase | 500 MB DB, 50k MAU, 5 GB egress, **2 free projects** | Years of a household's expenses fit in a few MB |
| Supabase | **Pauses after ~7 days of low activity** | Regular use of the app keeps it active; the weekly backup is a safety net, not a guarantee. If it pauses anyway, resume it in the dashboard (data kept, restorable up to 1 year) |
| Supabase | No backups, no PITR | Covered by §6 |
| Render | Spins down after 15 min idle; **~1 min cold start** | The first request after a quiet spell is slow |
| Render | 750 instance hours/month per workspace | One service is at most ~744 h, so it fits even if it never sleeps |
| Render | No free workers, no pre-deploy command | The app needs no worker; migrations run in the build |
| GitHub Actions | Private repo: 2,000 min/month, 500 MB artifacts | Backup job ≈ 1–2 min/day, small artifacts |

## Runbooks
- **Secret rotation**: rotate in the provider, update the Render env group / EAS env / GitHub secret, redeploy. For Supabase JWT keys use "rotate": the old key stays valid in JWKS until revoked, so the API keeps accepting live sessions.
- **Project paused**: Supabase dashboard → project → **Resume project**. The API fails with DB errors until it is back.
- **Restore drill** (before launch and every 6 months): download the latest backup artifact, `gpg -d backup.tar.gz.gpg | tar xz`. Then restore into the local stack (`pnpm db:up`) or into a new Free project:
  ```sh
  psql --single-transaction --variable ON_ERROR_STOP=1 \
    --file backup/roles.sql --file backup/schema.sql \
    --command 'SET session_replication_role = replica' \
    --file backup/data.sql --dbname "$TARGET_DB_URL"
  ```
  Finally run `uv run alembic current` and a read-only smoke test against it.
