import type { ExpoConfig } from 'expo/config';

// Static app config. EXPO_PUBLIC_* variables are read at bundle time from process.env,
// so they do not need to be forwarded through `extra`.
const config: ExpoConfig = {
  name: 'Split Ranch',
  slug: 'split-ranch',
  scheme: 'splitranch',
  version: '0.1.0',
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'automatic',
  android: {
    package: 'com.splitranch.app',
    adaptiveIcon: {
      backgroundColor: '#AE4728',
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
    'expo-font',
    [
      'expo-splash-screen',
      {
        image: './assets/splash-icon.png',
        imageWidth: 160,
        backgroundColor: '#FCFAF8',
        dark: { backgroundColor: '#15110F' },
      },
    ],
    // Google Sign-In config plugin. Without Firebase, no options are required on Android;
    // the web client id is passed at runtime via EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID.
    '@react-native-google-signin/google-signin',
  ],
  experiments: {
    typedRoutes: true,
  },
  extra: {
    eas: {
      // Public EAS project identifier (not a secret).
      projectId: 'e64b0d63-66af-4d98-b1a0-992d6059e0a9',
    },
  },
};

export default config;
