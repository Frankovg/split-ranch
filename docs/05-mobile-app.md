# 05 — Mobile app

## Platform baseline (verified 2026-11-07)
- **Expo SDK 58** (React Native 0.88, React 19.x). New Architecture only (legacy dropped after SDK 54). If the Phase 0 spike finds NativeWind/Reusables issues on 58, pin **SDK 57** and revisit at the next SDK.
- **Expo Router** (file-based, typed routes enabled, `Stack.Protected` for auth gating).
- **Development builds** (not Expo Go): Google sign-in, push and MMKV need native modules.
- TypeScript `strict`, `noUncheckedIndexedAccess`.

## Folder structure (`apps/mobile`)

```
apps/mobile/
├── app/                              # Expo Router routes only (thin)
│   ├── _layout.tsx                   # providers: Query, Theme, Toast, i18n
│   ├── (auth)/sign-in.tsx  (auth)/quick-splits.tsx
│   ├── (app)/_layout.tsx             # stack of the signed-in area
│   ├── (app)/(tabs)/_layout.tsx      # tabs: Inicio · Gastos · Cuentas rápidas · Ajustes
│   ├── (app)/(tabs)/index.tsx        # active group: balance, suggestions, members, recent
│   ├── (app)/(tabs)/expenses.tsx     # grouped by day, month filter, totals
│   ├── (app)/(tabs)/quick/index.tsx
│   ├── (app)/(tabs)/settings.tsx
│   ├── (app)/expense/new.tsx         # presented as modal
│   ├── (app)/expense/[id].tsx        # edit / delete (any member)
│   ├── (app)/groups/index.tsx        # my groups (switch), create, join with code
│   ├── (app)/group/settings.tsx      # name, members, invite, leave, remove + delete (admin)
│   ├── (app)/group/settle.tsx        # suggestions, record payment, confirm / dispute / cancel
│   ├── quick/[id].tsx                # Quick split editor (also reachable signed out)
│   └── dev/gallery.tsx               # component gallery, dev builds only
├── src/
│   ├── features/                     # auth/  groups/  quick-splits/  settings/  dev/
│   ├── components/ui/                # React Native Reusables (copied, owned)
│   ├── components/                   # app-level composites (MoneyText, MemberAvatarStack…)
│   ├── lib/api/                      # openapi-fetch client over @split-ranch/api-client (token from Supabase session)
│   ├── lib/supabase.ts               # Supabase client, auth only (no data queries)
│   ├── lib/query/                    # QueryClient, persister, query keys
│   ├── lib/money/                    # re-export of @split-ranch/domain + parse/format
│   ├── stores/                       # Zustand: session, preferences (theme, language, active group), quick splits
│   ├── i18n/                         # es, en
│   ├── platform/                     # android-specific code (payment intents, widget later)
│   └── theme/                        # tokens bridge (see 13-design-system)
├── global.css  tailwind.config.js  app.config.ts  eas.json
```

Routes stay thin: a route file renders a feature screen component from `src/features/*`.

**Quick splits without login:** the root layout lets `(tabs)/quick` and `quick/[id]` render signed out. The sign-in screen has a secondary action "Usar Cuentas rápidas sin cuenta".

## Key screens

| Screen | Content |
|---|---|
| Sign-in | Google button (Credential Manager), Quick splits link, privacy policy link |
| Groups | My groups (tap to make one active; persisted in `stores/preferences.ts`), create a group, join with the 8-letter code typed by hand. Shown instead of Home when the user has no group |
| Home | Active group name (opens Groups) and settings; my running balance, "pending confirmation", my suggested payments, Settle up; members with their nets; recent expenses; "+ Gasto" |
| New/edit expense | Amount, description, payer, category chips, "split between" (equal) members. Edit sends only the changed fields (`If-Match`); shows who added and who last edited it; delete with confirmation. Planned: date picker, weights/percentages/exact with live preview |
| Expenses list | `SectionList` grouped by `expense_date` (day headers), chips This month / Last month / All, summary card (total, top categories, per payer). Planned: category/payer/text filters, custom range |
| Settle up | Suggestions (greedy, after payments already sent) with "I've paid" / "I received it" and a note; payment list with Received / Not received (note) / Cancel |
| Group settings | Rename, members (admin badge), invite (share the code), leave; admin: remove member, delete group (type the name) |
| Categories & rules | Planned: default rule editor (equal / weights / percentages with live 100% check), per-category rules. Any member may edit them |
| Quick splits | List of local events; editor with mode toggle (total vs itemised), participants chips (tap to rename, mark "Soy yo" or remove), result card with a manual "Debe / Ha pagado" button per debtor, Share |
| Settings | Theme (system/light/dark), language, sign out. Planned: profile, notifications, delete account |

## State and data

| Kind | Tool |
|---|---|
| Server state | **TanStack Query v5**: query keys `['group', gid, 'expenses', filters]` (everything of a group under `['group', gid]`, invalidated after any expense or payment change), etc. `staleTime` 30 s for lists, invalidation after mutations |
| Persistence | `@tanstack/query-async-storage-persister` (backed by MMKV) so the last data is shown offline |
| Session | **`supabase-js`** auth client: persists and auto-refreshes the session. Storage adapter = encrypted MMKV whose encryption key lives in `expo-secure-store` (SecureStore alone has a ~2 KB value limit, too small for a Supabase session) |
| Client state | **Zustand**: auth status mirrored from `onAuthStateChange`, active group id, Quick-splits drafts (persisted via MMKV) |
| Forms | **React Hook Form + Zod** (`@hookform/resolvers/zod`). Zod schemas mirror the Pydantic ones (generated types for shape; Zod for UX validation, e.g. percentages must sum to 100 %) |
| Money/splits | `@split-ranch/domain` for previews and the whole Quick-splits computation |

Why RHF + Zod: uncontrolled inputs keep re-renders low on mid-range Android phones; Zod gives one schema for typing and validation and is what most RN form examples use. Alternative considered: TanStack Form (good, smaller ecosystem today).

### API client and session
- `openapi-fetch` client typed with the `paths` generated in `packages/api-client` (`pnpm api:openapi`). Auth is a custom `fetch` passed to the client (`authFetch` in `src/lib/api/client.ts`), not a middleware: it reads the current access token from `supabase.auth.getSession()` (which refreshes it when close to expiry) and attaches it. On `401` it calls `supabase.auth.refreshSession()` once and re-sends a copy of the request taken before the first send (a `Request` body can be read only once, and openapi-fetch middleware cannot re-send a request). `unwrap()` turns a non-2xx result into `ApiError` (problem+json body) so React Query sees a failure.
- `supabase.auth.startAutoRefresh()` / `stopAutoRefresh()` bound to `AppState` (foreground/background), as Supabase recommends for React Native.
- On `SIGNED_OUT` (or failed refresh) → clear query cache → `Stack.Protected` redirects to sign-in.
- The Supabase client is used **only** for `auth.*`. Lint rule forbids `supabase.from(...)`/`rpc` imports in features: data goes through FastAPI.

## Google sign-in

- Android's legacy Google Sign-In is deprecated in favour of **Credential Manager**.
- **Library (decided 2026-11-12):** `react-native-nitro-google-signin` (MIT, Credential Manager on Android, built on Nitro Modules, which the app already uses for MMKV). The free API of `@react-native-google-signin/google-signin` still wraps the legacy SDK and cannot embed a nonce; its Credential Manager API (Universal Sign-In) is paid and remains the fallback. The library is wrapped in `src/features/auth/google.ts` (`signInWithGoogle(): Promise<void>`) so it can be swapped.
- Flow inside that function: generate a random nonce → `GoogleOneTapSignIn.configure({ webClientId, nonce: sha256(rawNonce) })` on **every** attempt (the library only takes the nonce in `configure()` and otherwise uses an internal one it never returns) → `signIn` → `createAccount` → `presentExplicitSignIn` → check that the ID token's `nonce` claim equals the hash → `supabase.auth.signInWithIdToken({ provider: 'google', token: idToken, nonce: rawNonce })`. Supabase verifies the Google token and the nonce (its Google provider is configured with our **web client ID**; the Android client ID is registered in Google Cloud with the app's SHA-1 fingerprints for each EAS keystore).
- The nonce is mandatory on the client: Supabase accepts a token without a nonce when the request has none, so the app never sends one. Sign-in attempts are serialized, because `configure()` is global native state.
- No config plugin on Android (autolinking + runtime `webClientId`). The library's Expo plugin only adds the iOS URL scheme and requires `iosUrlScheme`; add it when iOS is built.
- Fallback without a native library: `supabase.auth.signInWithOAuth` + `expo-web-browser` + deep-link redirect (works, but shows a browser tab; kept only as a plan B).
- Sign-out: `supabase.auth.signOut()` (+ the Google library's `signOut` so the account picker shows again).

## Push notifications

- `expo-notifications` + Expo Push Service; FCM v1 credentials uploaded to EAS. Requires a development build and a real device for testing.
- Register after sign-in and when permission is granted (Android 13+ runtime permission: ask in context, e.g. after creating the first expense, not at launch).
- Channels: `expenses`, `settlement`, `reminders` (users can mute per channel in Android settings).
- Notification payload carries `{type, group_id, path}`; tapping navigates with Expo Router.

## Offline

**MVP (read-mostly offline):**
- Persisted query cache: everything seen is available offline (read).
- Creating an expense offline: mutation is queued (TanStack Query paused mutations persisted to MMKV), shown optimistically with a "pending sync" badge. Client generates the expense UUIDv7, so replays return the stored expense instead of a duplicate.
- Edits/deletes offline are **disabled** in MVP (button shows "Necesitas conexión").
- Quick splits are fully offline by design and never leave the phone (no sync).

**Post-MVP (full offline), strategy:**
- Outbox of mutations (create/update/delete) with `base_version`.
- On replay: server applies optimistic locking. `412` → the app fetches the current version and shows a merge sheet (field-level: theirs vs mine; amount/split conflicts must be chosen explicitly). Deletes win over edits from the other side only with confirmation.
- State-dependent failures (`409 member_left`, `412`) → the app reloads the expense and shows the latest version.
- Delta pull: `GET /groups/{gid}/changes?since=<cursor>` returning changed/deleted ids per entity (uses `updated_at` + monotonic `change_seq`).
- Rejected alternatives: CRDTs / PowerSync / WatermelonDB — powerful but disproportionate for small groups where conflicts are rare and must be resolved by humans anyway (money).

## Deep links
- Scheme `splitranch://` and Android App Links on `https://<domain>/join/{code}` and `/q/{token}` (assetlinks.json served by the API host).

## Builds and releases
- `eas.json` profiles: `development` (dev client, internal), `preview` (APK for staging, internal distribution), `production` (AAB → Play).
- **EAS Update** channels `staging`/`production` for JS-only fixes; `runtimeVersion` policy `fingerprint` so native changes force a new build.
- Play tracks: internal testing → closed testing → production.

## Internationalisation and accessibility
- `i18next` + `expo-localization`; Spanish default, English second. Money and dates via `Intl`.
- Accessibility rules in [13](13-design-system.md) (touch targets ≥ 48 dp, font scaling, contrast, labels on icon buttons, amounts announced as currency).
