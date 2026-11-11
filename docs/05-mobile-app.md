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
│   ├── _layout.tsx                   # providers: Query, Theme, Toast, Sentry, i18n
│   ├── (auth)/sign-in.tsx
│   ├── (app)/_layout.tsx             # Stack.Protected guard={isSignedIn}
│   ├── (app)/(tabs)/_layout.tsx      # tabs: Inicio · Gastos · Cuentas rápidas · Ajustes
│   ├── (app)/(tabs)/index.tsx        # household home: balance, period card, recent
│   ├── (app)/(tabs)/expenses.tsx
│   ├── (app)/(tabs)/quick/index.tsx
│   ├── (app)/(tabs)/settings.tsx
│   ├── (app)/expense/new.tsx         # presented as modal
│   ├── (app)/expense/[id].tsx
│   ├── (app)/expense/[id]/history.tsx
│   ├── (app)/period/[seq].tsx        # summary, close, settlement, transfers, start next
│   ├── (app)/household/members.tsx
│   ├── (app)/household/categories.tsx
│   ├── (app)/household/rules.tsx
│   ├── (app)/onboarding/create-or-join.tsx
│   ├── join/[code].tsx               # deep link target (works signed out → redirects after sign-in)
│   ├── quick/[id].tsx                # Quick split editor (also reachable signed out)
│   └── dev/gallery.tsx               # component gallery, dev builds only
├── src/
│   ├── features/                     # feature modules: api hooks, components, schemas
│   │   ├── auth/  households/  expenses/  periods/  settlement/  quick-splits/  categories/
│   ├── components/ui/                # React Native Reusables (copied, owned)
│   ├── components/                   # app-level composites (MoneyText, MemberAvatarStack…)
│   ├── lib/api/                      # generated OpenAPI types + fetch client (token from Supabase session)
│   ├── lib/supabase.ts               # Supabase client, auth only (no data queries)
│   ├── lib/query/                    # QueryClient, persister, query keys
│   ├── lib/money/                    # re-export of @split-ranch/domain + parse/format
│   ├── stores/                       # Zustand: session, active household, quick-split drafts
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
| Onboarding | Create household (name) or join with code / pasted link |
| Home | Current period card (total, my net, days to close), "who owes whom" preview, recent expenses, FAB "+ Gasto" |
| New/edit expense | Amount keypad first (big numeric input), description, category chips, payer (default me), date, split section collapsed showing the resolved rule ("Igual entre 3 · por defecto"), expandable to change type/participants with live preview of shares |
| Expenses list | FlashList grouped by day, filters (period, category, payer), search |
| Expense detail | Shares, origin of rule, history link, edit/delete (reason sheet when needed, adjustment explanation when locked) |
| Period | Status timeline, totals by category, balances, transfers with I've paid / Received actions |
| Members & invitations | Share the household's invite code (WhatsApp), roles, leave |
| Categories & rules | Default rule editor (equal / weights / percentages with live 100% check), per-category rules |
| Quick splits | List of local events; editor with mode toggle (total vs itemised), participants chips (tap to rename, mark "Soy yo" or remove), result card with a manual "Debe / Ha pagado" button per debtor, Share |
| Settings | Profile, theme (system/light/dark), language, notifications, delete account |

## State and data

| Kind | Tool |
|---|---|
| Server state | **TanStack Query v5**: query keys `['household', hid, 'expenses', filters]`, etc. `staleTime` 30 s for lists, invalidation after mutations, optimistic updates for create/edit expense |
| Persistence | `@tanstack/query-async-storage-persister` (backed by MMKV) so the last data is shown offline |
| Session | **`supabase-js`** auth client: persists and auto-refreshes the session. Storage adapter = encrypted MMKV whose encryption key lives in `expo-secure-store` (SecureStore alone has a ~2 KB value limit, too small for a Supabase session) |
| Client state | **Zustand**: auth status mirrored from `onAuthStateChange`, active household id, Quick-splits drafts (persisted via MMKV) |
| Forms | **React Hook Form + Zod** (`@hookform/resolvers/zod`). Zod schemas mirror the Pydantic ones (generated types for shape; Zod for UX validation, e.g. percentages must sum to 100 %) |
| Money/splits | `@split-ranch/domain` for previews and the whole Quick-splits computation |

Why RHF + Zod: uncontrolled inputs keep re-renders low on mid-range Android phones; Zod gives one schema for typing and validation and is what most RN form examples use. Alternative considered: TanStack Form (good, smaller ecosystem today).

### API client and session
- `openapi-fetch` client with a middleware that reads the current access token from `supabase.auth.getSession()` (which refreshes it when close to expiry) and attaches it. On `401 token_expired` it calls `supabase.auth.refreshSession()` once and retries.
- `supabase.auth.startAutoRefresh()` / `stopAutoRefresh()` bound to `AppState` (foreground/background), as Supabase recommends for React Native.
- On `SIGNED_OUT` (or failed refresh) → clear query cache → `Stack.Protected` redirects to sign-in.
- The Supabase client is used **only** for `auth.*`. Lint rule forbids `supabase.from(...)`/`rpc` imports in features: data goes through FastAPI.

## Google sign-in

- Android's legacy Google Sign-In is deprecated in favour of **Credential Manager**.
- Options:
  1. `@react-native-google-signin/google-signin` — **Universal Sign-In** API uses Credential Manager (paid/sponsor tier); the free `GoogleSignin` API still uses the legacy SDK.
  2. Free MIT alternatives built on Credential Manager (e.g. `react-native-nitro-google-signin`, thoughtbot's `react-native-social-auth`).
- **Recommendation:** Phase 0 spike: try option 1 (best maintained, has an Expo config plugin and iOS support, and is the one Supabase's React Native guide uses) and decide whether the licence cost is acceptable; otherwise use the most active free Credential-Manager library. Either way, wrap it in `src/features/auth/google.ts` exposing `signInWithGoogle(): Promise<void>` so it can be swapped.
- Flow inside that function: generate a random nonce → pass its SHA-256 to the Google library → receive the ID token → `supabase.auth.signInWithIdToken({ provider: 'google', token: idToken, nonce: rawNonce })`. Supabase verifies the Google token (its Google provider is configured with our **web client ID**; the Android client ID is registered in Google Cloud with the app's SHA-1 fingerprints for each EAS keystore).
- Fallback without a native library: `supabase.auth.signInWithOAuth` + `expo-web-browser` + deep-link redirect (works, but shows a browser tab; kept only as a plan B).
- Sign-out: `supabase.auth.signOut()` (+ the Google library's `signOut` so the account picker shows again).

## Push notifications

- `expo-notifications` + Expo Push Service; FCM v1 credentials uploaded to EAS. Requires a development build and a real device for testing.
- Register after sign-in and when permission is granted (Android 13+ runtime permission: ask in context, e.g. after creating the first expense, not at launch).
- Channels: `expenses`, `settlement`, `reminders` (users can mute per channel in Android settings).
- Notification payload carries `{type, household_id, path}`; tapping navigates with Expo Router.

## Offline

**MVP (read-mostly offline):**
- Persisted query cache: everything seen is available offline (read).
- Creating an expense offline: mutation is queued (TanStack Query paused mutations persisted to MMKV), shown optimistically with a "pending sync" badge. Client generates the expense UUIDv7, so replays return the stored expense instead of a duplicate.
- Edits/deletes offline are **disabled** in MVP (button shows "Necesitas conexión").
- Quick splits are fully offline by design and never leave the phone (no sync).

**Post-MVP (full offline), strategy:**
- Outbox of mutations (create/update/delete) with `base_version`.
- On replay: server applies optimistic locking. `412` → the app fetches the current version and shows a merge sheet (field-level: theirs vs mine; amount/split conflicts must be chosen explicitly). Deletes win over edits from the other side only with confirmation.
- State-dependent failures (`409 reason_required`, `period_locked`) → the app asks for the reason or offers to create an adjustment.
- Delta pull: `GET /households/{hid}/changes?since=<cursor>` returning changed/deleted ids per entity (uses `updated_at` + monotonic `change_seq`).
- Rejected alternatives: CRDTs / PowerSync / WatermelonDB — powerful but disproportionate for small households where conflicts are rare and must be resolved by humans anyway (money).

## Deep links
- Scheme `splitranch://` and Android App Links on `https://<domain>/join/{code}` and `/q/{token}` (assetlinks.json served by the API host).

## Builds and releases
- `eas.json` profiles: `development` (dev client, internal), `preview` (APK for staging, internal distribution), `production` (AAB → Play).
- **EAS Update** channels `staging`/`production` for JS-only fixes; `runtimeVersion` policy `fingerprint` so native changes force a new build.
- Play tracks: internal testing → closed testing → production.

## Internationalisation and accessibility
- `i18next` + `expo-localization`; Spanish default, English second. Money and dates via `Intl`.
- Accessibility rules in [13](13-design-system.md) (touch targets ≥ 48 dp, font scaling, contrast, labels on icon buttons, amounts announced as currency).
