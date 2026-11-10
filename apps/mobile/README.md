# @split-ranch/mobile

Android app of Split Ranch (Expo SDK 58, React Native 0.88, Expo Router, NativeWind 4.2 + Tailwind CSS 3.4, React Native Reusables). Spec: `docs/05-mobile-app.md`, `docs/13-design-system.md`, `docs/03-business-rules.md` §6–7.

## Run it (development build, not Expo Go)

Google sign-in, MMKV (Nitro) and SecureStore are native modules, so Expo Go is not supported.

```bash
pnpm install                              # from the repo root (pnpm workspace, nodeLinker: hoisted)
cd apps/mobile
cp .env.example .env.local                # optional, see below
npx expo run:android                      # local dev build (Android SDK + device/emulator), or an EAS development build
pnpm --filter @split-ranch/mobile start   # = expo start --dev-client (root: pnpm mobile:dev)
```

From the repo root, `pnpm mobile:dev` also keeps `adb reverse tcp:8081` and `tcp:8000` applied on every connected emulator/USB phone (re-applied within ~3 s after an emulator restart), so the app reaches Metro and the API on `localhost`. One-shot: `pnpm adb:reverse`.

`expo start` also generates `.expo/types/router.d.ts` (typed routes). Without it `tsc` still passes, only with looser `href` types.

## Scripts

| Script | Does |
|---|---|
| `pnpm --filter @split-ranch/mobile typecheck` | `tsc --noEmit` (strict + `noUncheckedIndexedAccess`) |
| `pnpm --filter @split-ranch/mobile test` | Vitest for the pure TS modules (quick-split logic, share text, tokens sync, API client retry) |
| `pnpm --filter @split-ranch/mobile export:android` | `expo export --platform android` (proves the JS bundle builds) |
| `pnpm --filter @split-ranch/mobile doctor` | `expo-doctor` |

## Environment variables

All are public (`EXPO_PUBLIC_*` is inlined into the bundle — never secrets) and optional. Missing values disable the related feature; the app then runs signed out and Quick splits still work.

| Variable | Used for |
|---|---|
| `EXPO_PUBLIC_SUPABASE_URL` | Supabase Auth (auth only, no data queries) |
| `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key |
| `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` | Google sign-in (the web client id configured in the Supabase Google provider) |
| `EXPO_PUBLIC_API_URL` | FastAPI base URL for `src/lib/api` |

## Layout

- `app/` — routes only (thin). Root `Stack` with `Stack.Protected`: `(app)` (tabs Inicio · Gastos · Cuentas rápidas · Ajustes) when signed in, `(auth)` (sign-in + signed-out Quick splits list at `/quick-splits`) when signed out, `quick/[id]` always, `dev/gallery` only in `__DEV__`.
- `src/features/quick-splits/` — `model.ts` (pure updates), `compute.ts` (store → `resolveShares` → `computeBalances` → `settle` from `@split-ranch/domain`), `share-text.ts` (WhatsApp text), screens and components.
- `src/components/ui/` — React Native Reusables components added with the CLI (owned code; each file has a `// Source:` header listing local changes, mainly 48 dp touch targets).
- `src/components/` — `MoneyText`, `MoneyInput`, `EmptyState`, `FormField`, `Screen`, `BackendPlaceholder`.
- `src/lib/` — `money` (re-exports the domain + display helpers), `supabase.ts`, `api/`, `query/`, `storage.ts` (MMKV; session in an AES-256 encrypted MMKV whose key lives in SecureStore).
- `src/stores/` — Zustand: session (mirrored from `onAuthStateChange`), preferences (theme/language, persisted), quick splits (persisted).
- `src/theme/` — tokens mirror of `global.css` (kept in sync by a test), React Navigation theme, theme sync.
- `src/i18n/` — i18next + expo-localization, Spanish default, English second; keys are type-checked.

## What is real vs placeholder

- **Real:** Quick splits (offline, signed out, both modes, result card, share text, manual "has paid" status), theme switch, language switch, design-system base and dev gallery, auth wiring (needs env + Google Cloud/Supabase setup to actually sign in), API fetch wrapper.
- **Placeholder:** Inicio and Gastos show an empty state saying they need the backend (no fake data). Not built yet: expense form/detail, periods, members, categories, onboarding, `join/[code]`, push, persisted query cache, OpenAPI-generated client, Sentry.
- **Google sign-in:** uses the free `GoogleSignin` API of `@react-native-google-signin/google-signin`, which still wraps the legacy Google Sign-In SDK and cannot embed a nonce; the nonce is generated but only sent to Supabase when the provider applies it. See the TODO for the Credential Manager spike (T-0.4) in `src/features/auth/google.ts`.
- **Payments:** no links to payment platforms; people pay outside the app.
