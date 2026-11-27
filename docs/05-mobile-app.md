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
│   ├── (app)/_layout.tsx             # stack of the signed-in area (group screens sit above the tabs)
│   ├── (app)/(tabs)/_layout.tsx      # tabs: Ranchs · Cuentas rápidas · Ajustes (an AI chat tab later)
│   ├── (app)/(tabs)/index.tsx        # Ranchs: one card per group, "+" → create / join
│   ├── (app)/(tabs)/quick/index.tsx
│   ├── (app)/(tabs)/settings.tsx
│   ├── (app)/groups/new.tsx          # create a group
│   ├── (app)/groups/join.tsx         # join with the invitation code
│   ├── (app)/group/[groupId].tsx     # group home: balance, suggestions, members, expenses; header: search · insights · ⋮
│   ├── (app)/group/[groupId]/search.tsx    # text search over the group's expenses
│   ├── (app)/group/[groupId]/insights.tsx  # read-only: date range, totals, charts (no adding)
│   ├── (app)/group/[groupId]/settle.tsx    # suggestions, record payment, confirm / dispute / cancel
│   ├── (app)/group/[groupId]/settings.tsx  # name, members, invite, leave, remove + delete (admin)
│   ├── (app)/group/[groupId]/expense/new.tsx   # presented as modal
│   ├── (app)/group/[groupId]/category/new.tsx  # new custom category, modal
│   ├── (app)/group/[groupId]/expense/[id].tsx  # edit / delete (any member)
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
│   ├── stores/                       # Zustand: session, preferences (theme, language), quick splits
│   ├── i18n/                         # es, en
│   └── theme/                        # tokens bridge (see 13-design-system)
├── global.css  tailwind.config.js  app.config.ts  eas.json
```

Routes stay thin: a route file renders a feature screen component from `src/features/*`.

**Navigation:** the app opens on Ranchs (the group list). A group is opened by pushing `group/[groupId]`; every group screen reads the id from the route (`features/groups/route.ts`), so there is no persisted "active group" and back always returns to the list. Group screens live on the `(app)` stack above the tabs, so the tab bar is hidden inside a group. Leaving or deleting a group dismisses back to the list.

**Quick splits without login:** the root layout lets `(tabs)/quick` and `quick/[id]` render signed out. The sign-in screen has a secondary action "Usar Cuentas rápidas sin cuenta".

## Key screens

| Screen | Content |
|---|---|
| Sign-in | Google button (Credential Manager), Quick splits link, privacy policy link |
| Ranchs (home) | One card per group (name, member count, admin badge); tap opens the group. A centred "+" opens a sheet: create a group or join with the 8-letter code, each on its own screen; after either, the new group opens |
| Group home | Header: group name, search, insights and a ⋮ menu (settle up, group settings). One card: my running balance, "pending confirmation", my suggested payments, every member's net, invite hint when alone, Settle up. Below it every expense, grouped by day (infinite scroll). A centred "+" adds an expense |
| Search | Text search on the description (`q`), all dates, same rows as the expense list |
| New/edit expense | Amount, description, category select with icons ("Other" = no category) plus a button to create a custom category (name + icon, kept in the group), payer select (default: you), date ("When", default: today in the group time zone). Split table: a "Split" checkbox (off = `personal`) and one checkbox per member; mode Equally / As parts (editable percentages with € preview) / As amount (editable amounts). Editing one value gives the remainder to the members not typed yet. The table starts from the group default rule (a percentages rule opens *As parts* with its values, scaled to 100 % over today's members); an untouched table is not sent, so the group/category rule decides. Edit sends only the changed fields (`If-Match`); shows who added and who last edited it; delete with confirmation |
| Insights | Read-only (no adding): range chips This month / Last month / All, category and payer filter chips, headline total + count, ranked bars by category and by payer (top 5 + "Other"; a split hides when filtered to one value or with a single row). Planned: custom range, spending over time (needs a per-period total in `/summary`) |
| Settle up | Suggestions (greedy, after payments already sent) with "I've paid" / "I received it" and a note; payment list with Received / Not received (note) / Cancel |
| Group settings | Rename, members (admin badge), invite (share the code), leave; admin: remove member, delete group (type the name) |
| Categories & rules | Group settings → "How expenses are split": the default rule, *Equal parts* (`equal` without shares: every active member, later joiners included) or *Custom* (`percentages` naming every active member, 0 % allowed, live 100 % check). Saved rules apply only to new expenses. Planned: per-category rules. Any member may edit them |
| Quick splits | List of local events; editor with mode toggle (total vs itemised), participants chips (tap to rename, mark "Soy yo" or remove), result card with a manual "Debe / Ha pagado" button per debtor, Share |
| Settings | Theme (system/light/dark), language, **Notifications** (opens the switches screen), sign out. Planned: profile, delete account |
| Notifications (`/notifications`) | Master switch plus one switch per event type (new expense, expense edited/deleted, payments, new member), saved on the server (`/v1/me`). Shows a notice with a button to the system settings when the OS permission is denied |

## State and data

| Kind | Tool |
|---|---|
| Server state | **TanStack Query v5**: query keys `['group', gid, 'expenses', filters]` (everything of a group under `['group', gid]`; group tabs stay mounted, so mutations invalidate only what they change: an expense change → balance, expense lists, summaries, expense details; a payment change → balance, payments; see `features/groups/invalidation.ts`), etc. `staleTime` 30 s for lists, invalidation after mutations |
| Persistence | `@tanstack/query-async-storage-persister` + `PersistQueryClientProvider`, backed by an encrypted MMKV instance (`split-ranch.query-cache`, same SecureStore key as the session) so the last data is shown offline. `maxAge` = `gcTime` = 24 h; bump `CACHE_BUSTER` (`src/lib/query/client.ts`) when response shapes or query keys change. Sign-out clears the cache and deletes the disk copy |
| Session | **`supabase-js`** auth client: persists and auto-refreshes the session. Storage adapter = encrypted MMKV whose encryption key lives in `expo-secure-store` (SecureStore alone has a ~2 KB value limit, too small for a Supabase session) |
| Client state | **Zustand**: auth status mirrored from `onAuthStateChange`, theme/language preferences, Quick-splits drafts (persisted via MMKV); the open group comes from the route |
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

- `expo-notifications` + Expo Push Service. Android delivery goes through FCM: `google-services.json` (Firebase project, public identifiers, committed) is set as `android.googleServicesFile`, and the FCM V1 service-account key is uploaded to EAS (never in the repo). Requires a development build and a real device for testing.
- Code: `src/features/notifications/` (`register.ts`, `channels.ts`, `NotificationObserver.tsx` mounted in the root layout, `NotificationSettingsScreen.tsx`).
- **Registration:** channels → permission → Expo push token → `PUT /v1/me/push-tokens {token, platform, locale}`. Done silently after sign-in when permission is already granted, again when the token or the app language changes (the server writes the text in the device's language). The permission is asked in context: after the first saved expense, or when the user turns the master switch on; never at launch. Android 13+: the prompt only appears once a channel exists, so channels are created first.
- **Sign-out:** `DELETE /v1/me/push-tokens` before `supabase.auth.signOut()` (it still needs the session); a failure does not block signing out.
- **Events** (never sent to the member who did the action, to members who left, or to users with the switch off): new expense → every other active member; expense edited/deleted → its payer and participants (before and after the edit); payment sent → receiver; payment recorded as received, confirmed or disputed → payer; payment cancelled → receiver; member joined → the rest of the group.
- **Channels:** `expenses`, `payments`, `group` (users can mute each in Android settings; `expenses` is the plugin's `defaultChannel`).
- **Payload:** `data = {type, group_id, url}` with `url` one of `/group/<id>`, `/group/<id>/settle`, `/group/<id>/expense/<id>` (validated by `routing.ts`). A push received with the app open shows a banner and invalidates the group's queries; a tap (also from a cold start, `getLastNotificationResponse`) opens `url` with Expo Router.
- **Server side** (`apps/api` `use_cases/notifications.py`): sent after the response as a FastAPI background task with its own DB session; Expo is called with HTTPX (batches of 100, optional `EXPO_ACCESS_TOKEN` for enhanced push security); receipts are checked lazily on the next send to the same device (15 min – 24 h after the ticket).

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
