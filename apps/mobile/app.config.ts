import { readFileSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import type { ExpoConfig } from 'expo/config';

// The user-facing version lives in package.json and is bumped by hand for a release. The
// build number (versionCode) is separate and auto-incremented by EAS (eas.json `autoIncrement`).
const { version } = JSON.parse(readFileSync(join(__dirname, 'package.json'), 'utf8')) as { version: string };

// Readex Pro (the brand typeface) files, resolved through the package so the path
// works whether pnpm links it under this app or hoists it to the workspace root.
const READEX_DIR = relative(
  __dirname,
  dirname(require.resolve('@expo-google-fonts/readex-pro/package.json')),
);
const READEX_WEIGHTS = [
  { weight: 400, file: '400Regular/ReadexPro_400Regular.ttf' },
  { weight: 500, file: '500Medium/ReadexPro_500Medium.ttf' },
  { weight: 600, file: '600SemiBold/ReadexPro_600SemiBold.ttf' },
  { weight: 700, file: '700Bold/ReadexPro_700Bold.ttf' },
].map((w) => ({ ...w, path: join(READEX_DIR, w.file).split(sep).join('/') }));

// Static app config. EXPO_PUBLIC_* variables are read at bundle time from process.env,
// so they do not need to be forwarded through `extra`.
const config: ExpoConfig = {
  name: 'Splitranch',
  slug: 'split-ranch',
  scheme: 'splitranch',
  version,
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'automatic',
  // EAS Update (OTA): JS/asset-only changes ship with `eas update --channel <channel>`.
  // The fingerprint policy hashes the native project, so any native change (new native
  // module, SDK upgrade, plugin or permission change) yields a new runtime version and
  // needs a new build; updates never reach an incompatible binary.
  runtimeVersion: { policy: 'fingerprint' },
  updates: {
    url: 'https://u.expo.dev/e64b0d63-66af-4d98-b1a0-992d6059e0a9',
  },
  android: {
    package: 'com.splitranch.app',
    // Firebase app registration for FCM (public identifiers only; safe to commit).
    googleServicesFile: './google-services.json',
    adaptiveIcon: {
      backgroundColor: '#178264',
      foregroundImage: './assets/android-icon-foreground.png',
      backgroundImage: './assets/android-icon-background.png',
      monochromeImage: './assets/android-icon-monochrome.png',
    },
    predictiveBackGestureEnabled: false,
  },
  ios: {
    bundleIdentifier: 'com.splitranch.app',
    supportsTablet: false,
  },
  web: {
    favicon: './assets/favicon.png',
  },
  plugins: [
    'expo-router',
    'expo-localization',
    'expo-secure-store',
    '@react-native-community/datetimepicker',
    [
      'expo-font',
      {
        // Android: one family with a definition per weight (fontFamily 'ReadexPro' +
        // fontWeight). iOS: the files are listed and resolved by family name 'Readex Pro'.
        android: {
          fonts: [
            {
              fontFamily: 'ReadexPro',
              fontDefinitions: READEX_WEIGHTS.map(({ path, weight }) => ({ path, weight })),
            },
          ],
        },
        ios: { fonts: READEX_WEIGHTS.map(({ path }) => path) },
      },
    ],
    [
      'expo-splash-screen',
      {
        image: './assets/splash-icon.png',
        imageWidth: 160,
        // Mirrors the light/dark `background` tokens (src/theme/tokens.ts).
        backgroundColor: '#F6F8F7',
        dark: { backgroundColor: '#121212' },
      },
    ],
    'expo-status-bar',
    [
      'expo-notifications',
      {
        // Android status-bar icon: 96x96, white on transparent.
        icon: './assets/notification-icon.png',
        color: '#178264',
        // Channel for FCM messages that arrive without one (channels: src/features/notifications).
        defaultChannel: 'expenses',
      },
    ],
    // Sentry: native crash reporting and source map upload on release builds (EU region).
    // Org, project and auth token come from the SENTRY_ORG / SENTRY_PROJECT /
    // SENTRY_AUTH_TOKEN env vars (EAS environment variables), never from this file, so the
    // native fingerprint does not depend on them. Without a token, set
    // SENTRY_DISABLE_AUTO_UPLOAD=true for local release builds.
    ['@sentry/react-native/expo', { url: 'https://de.sentry.io/' }],
    // Google sign-in (react-native-nitro-google-signin) needs no config plugin on Android:
    // the native module is autolinked and the web client id is passed at runtime via
    // EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID. Its plugin only adds the iOS URL scheme and throws
    // without `iosUrlScheme`, so add it as
    // ['react-native-nitro-google-signin', { iosUrlScheme: 'com.googleusercontent.apps.<ios-client-id>' }]
    // when iOS is built.
  ],
  experiments: {
    typedRoutes: true,
    // Automatic memoization (babel-preset-expo runs babel-plugin-react-compiler on app code).
    reactCompiler: true,
  },
  extra: {
    eas: {
      // Public EAS project identifier (not a secret).
      projectId: 'e64b0d63-66af-4d98-b1a0-992d6059e0a9',
    },
  },
};

export default config;
