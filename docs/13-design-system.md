# 13 — Design system

## 1. Library decision

### State of the ecosystem (checked 2026-11-07)

| Project | Status |
|---|---|
| **Expo SDK** | 58 (Oct 2026, RN 0.88); New Architecture only |
| **NativeWind** | `latest` = **4.2.x** (Tailwind **v3**). v5 (Tailwind v4.1+, Reanimated 4+, `react-native-css` engine, New Arch only, RN 0.81+) is at **5.0.0-rc.1** (2026-11-02), not yet promoted to `latest` |
| **Uniwind** | Alternative Tailwind **v4** engine from the Unistyles authors; Expo-focused; no PostCSS step; claims better performance (vendor claim) |
| **React Native Reusables** | shadcn/ui port on `@rn-primitives`; CLI (`init`, `add`, `doctor`); supports **NativeWind and Uniwind**; MIT; actively maintained (~6.6k stars) |
| **gluestack-ui** | **v5 stable (June 2026)** on NativeWind v5/Tailwind v4; v3 is now a legacy line (the brief mentioned v3) |
| **Tamagui** | v2 released (RC Dec 2025 → stable 2026); own compiler and theme system; strong for RN + web |

### Comparison

| Criterion | NativeWind + RN Reusables | gluestack-ui v5 | Tamagui v2 |
|---|---|---|---|
| shadcn model (copy into repo, own the code) | ✅ exact model (CLI copies components) | ✅ copy-paste components too | ❌ library-centric (you consume packages) |
| Styling | Tailwind classes | Tailwind classes (NativeWind v5) | Own styled API + tokens; compiler |
| Tailwind version today | v3 stable (v4 via NativeWind v5 RC or Uniwind) | v4 (depends on NativeWind v5 RC / preview) | n/a |
| Theme tokens + dark mode | CSS variables (`--primary` …) + `dark:` / color scheme | Tokens via Tailwind config | First-class themes, best-in-class |
| Accessibility | `@rn-primitives` (Radix-like, roles/states) | Good, explicit a11y work in v3+ | Good |
| Component breadth for our needs | Button, Input, Select, Dialog, Tabs, Avatar, Badge, Card, Skeleton, Toggle, Popover…; **no toast, date picker, bottom sheet** (add libs) | Broader (incl. toast, actionsheet, drawer) | Broad |
| Expo compatibility risk | Low with NativeWind 4.2 | Medium (bound to NativeWind v5 RC) | Low-medium (compiler setup) |
| Learning curve | Low if you know shadcn/Tailwind | Low-medium | Medium-high |
| Web reuse later | Possible | Possible | Excellent |
| Lock-in | Minimal | Low | Higher |

### Recommendation
**NativeWind 4.2 (Tailwind 3) + React Native Reusables** — your preference is viable.
- It is the only option that is both on a **stable** styling engine today and follows the shadcn ownership model.
- Upgrade path: when NativeWind v5 is promoted to `latest` (or if 4.2 misbehaves on SDK 58), migrate to NativeWind v5 + Tailwind v4, or to **Uniwind** — Reusables supports both, so the components barely change. Keeping all colours as CSS variables makes the Tailwind v3 → v4 move mostly a config rewrite (`tailwind.config.js` → `@theme` in CSS).
- gluestack-ui v5 is a good second choice (more components out of the box) but today it rides on a release-candidate engine.
- Tamagui is the right pick only if a strong web app were a near-term goal.

Phase 0 spike (T-0.3) validates: install on SDK 58, dark mode toggle, font scaling to 200 %, Dialog/Select/Tabs on Android, Reanimated 4 compatibility, release-build CSS output. Fallbacks in order: pin SDK 57 → Uniwind.

## 2. Setup (NativeWind 4.2 on Expo)

Illustrative, re-check against the NativeWind docs at implementation time:
- deps: `nativewind`, `tailwindcss@^3.4`, `react-native-reanimated`, `react-native-safe-area-context`, `prettier-plugin-tailwindcss`.
- `tailwind.config.js` with `presets: [require('nativewind/preset')]`, `content: ['./app/**/*.{ts,tsx}', './src/**/*.{ts,tsx}']`, `darkMode: 'class'`, colours mapped to CSS variables.
- `global.css` with `@tailwind base; @tailwind components; @tailwind utilities;` and the `:root` / `.dark:root` variable blocks.
- `babel.config.js`: `jsxImportSource: 'nativewind'` + `nativewind/babel`; `metro.config.js`: `withNativeWind(config, { input: './global.css' })`.
- `nativewind-env.d.ts` for `className` types.
- Then `npx @react-native-reusables/cli init` and `add button input …`.

## 3. Tokens

Semantic colour tokens (HSL CSS variables, shadcn naming so copied components work unchanged):

| Token | Light | Dark | Use |
|---|---|---|---|
| `background` / `foreground` | near-white / near-black | near-black / near-white | screens, text |
| `card` / `card-foreground` | | | cards, sheets |
| `primary` / `primary-foreground` | deep mint `163 70% 30%` | mint `#5cedc2` | links, tab tint, focus, FAB, button press fill |
| `secondary`, `muted`, `accent` (+ foregrounds) | | | chips, subtle backgrounds |
| `destructive` | red | red (lighter) | delete |
| `border`, `input`, `ring` | | | outlines, focus |
| **`positive`** | green | green | "te deben" (you are owed) |
| **`negative`** | red-orange | red-orange | "debes" (you owe) |
| **`warning`** | amber | amber | edited after close, rule fallback |
| `chart-1…6` | colour-blind-safe palette | | category charts, member colours |

Brand palette (from the author's web portfolio; dark is the reference): background `#121212`, surfaces (`card`, `muted`) `#242424`, mint `#5cedc2` for `primary` and `positive`, deep green `#122f27` for `accent` and `border`, pink `#e453bc` for `negative`, `#ff2301` destructive, `#f5ec28` warning. Light keeps the hues, darkened where they are text on a light background. `chart-1…6` keep the Okabe-Ito order with the bluish green and reddish purple replaced by the brand mint and pink. Tailwind colours are `hsl(var(--x) / <alpha-value>)`, so opacity modifiers (`bg-primary/90`) work.

Rules: never encode meaning only in colour — amounts owed carry a sign and a label ("Debes 12,50 €").

Other tokens:
- **Radius**: `--radius: 0.5rem` → `rounded-sm` 4 px (buttons, toggles), `md` 6 px (inputs), `lg` 8 px, `xl` 12 px (cards, sheets).
- **Spacing**: Tailwind 4-pt scale; screen gutter `px-4`; list row min height 56 dp.
- **Typography**: Readex Pro (400/500/600/700), embedded by the `expo-font` config plugin as one Android family `ReadexPro` with a definition per weight, so `font-medium/semibold/bold` work; `font-sans` is the base of `Text`, inputs and the navigation theme. Scale `text-xs … text-3xl`; amounts use `font-variant-numeric: tabular-nums` (`tabular-nums` class) and a dedicated `MoneyText` component.
- **Elevation**: minimal; borders over shadows (consistent in dark mode).
- **Buttons**: `default` is a high-contrast surface (`bg-foreground`, `text-background`) that fills with `primary` from the left while pressed (the portfolio's hover fill); `outline` has a muted border that turns `primary` on press. The "+" `Fab` is a mint circle centred at the bottom.
- **Background**: `ScreenBackground`, a static diagonal gradient `card → background → accent` (react-native-svg).
- **Motion**: Reanimated; respect "remove animations" (`useReducedMotion`).

### Dark mode
- Modes: system (default), light, dark — stored in MMKV; NativeWind `useColorScheme().setColorScheme`.
- Status/navigation bar colours follow the theme (`expo-system-ui`, `expo-status-bar`).
- React Navigation theme derived from the same tokens (a `theme/navigation.ts` bridge) to avoid flashes.

## 4. Component catalogue

| Component | Source | Notes |
|---|---|---|
| Button, IconButton | Reusables | variants: default, secondary, outline, ghost, destructive; sizes with min 48 dp target |
| Input, Textarea, Label | Reusables | |
| **MoneyInput** | custom | big numeric keypad entry, es-ES parsing, cents internally |
| Select | Reusables (`@rn-primitives/select`) | |
| Checkbox, Switch, RadioGroup, ToggleGroup | Reusables | split type selector = ToggleGroup |
| Dialog, AlertDialog | Reusables | destructive confirmations, reason prompts |
| **BottomSheet** | `@gorhom/bottom-sheet` (verify Reanimated 4 support in spike; fallback Reusables Dialog styled as sheet) | expense form sections, filters |
| Card | Reusables | |
| Tabs | Reusables | in-screen tabs; app tabs = Expo Router Tabs |
| **Toast** | `sonner-native` | Reusables has no toast |
| Avatar, AvatarStack | Reusables + custom | member initials fallback, deterministic colour |
| Badge | Reusables | status: abierto/cerrado/liquidado, "editado", "pendiente sync" |
| **Form fields** | custom `FormField` on RHF `Controller` | label, description, error, a11y wiring |
| **DatePicker / Calendar** | `@react-native-community/datetimepicker` (native Android dialog) for MVP; `react-native-calendars` if a calendar view is needed later | |
| Skeleton | Reusables | |
| EmptyState | custom | icon + text + action |
| ListRow / ExpenseRow | custom | |
| SplitEditor | custom | equal/weights/percentages/exact with live total check |
| Popover, Tooltip, DropdownMenu | Reusables | |

**Complementary libraries**

| Need | Library |
|---|---|
| Virtualised lists | `@shopify/flash-list` (v2, New Arch) |
| Icons | `lucide-react-native` (shadcn default) + `react-native-svg` |
| Animations / gestures | `react-native-reanimated` 4 + `react-native-gesture-handler` |
| Charts | `react-native-gifted-charts` (the category pie chart in Insights) |
| Bottom sheets | `@gorhom/bottom-sheet` |
| Toasts | `sonner-native` |
| Storage | `react-native-mmkv`, `expo-secure-store` |
| Haptics | `expo-haptics` |

## 5. Conventions for copied components
- Live in `src/components/ui/`, added only via the Reusables CLI, committed as-is in a first commit, then modified in a second commit (diffs stay reviewable).
- Header comment: `// Source: react-native-reusables <component> @ <version/date>. Local changes: …`.
- Never import RN primitives directly in features when a `ui/` component exists.
- Variants via `class-variance-authority` (`cva`) and `cn()` (`clsx` + `tailwind-merge`), as in shadcn.
- No hard-coded colours in features — only token classes (`bg-primary`, `text-negative`). ESLint rule (`no-restricted-syntax` / tailwind plugin) flags arbitrary colour values.
- Updating upstream: `reusables-cli add <comp> --overwrite` on a branch, re-apply local changes, check the gallery.

## 6. Accessibility
- Touch targets ≥ 48×48 dp (`min-h-12 min-w-12`, `hitSlop` on icons).
- Every icon-only button has `accessibilityLabel`; roles/states come from `@rn-primitives`.
- Contrast ≥ 4.5:1 for text, 3:1 for large text/UI — checked for both themes when tokens change.
- Font scaling: no `allowFontScaling={false}`; layouts tested at 200 % (wrap instead of truncate amounts; `MoneyText` never truncates).
- Amounts announced as currency (`accessibilityLabel="Debes doce euros con cincuenta"` built with `Intl` + i18n).
- Focus order and TalkBack tested on the main flows (expense form, settle up, quick splits).
- Reduced motion respected.

## 7. Keeping the UI consistent
- **Internal component gallery** at `app/dev/gallery.tsx` (only in development builds): every `ui/` component with all variants, light/dark toggle, font-scale preview. Cheaper than Storybook for RN and always in sync with the real app. Storybook for React Native is not worth it at this team size.
- Screenshot snapshots of the gallery (Maestro `takeScreenshot`) in the nightly E2E to spot regressions.
- PR checklist: tokens only, a11y labels, dark mode checked, font scale checked.
