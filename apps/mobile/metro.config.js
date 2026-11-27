// Metro config for the pnpm monorepo. Expo's default config already detects the
// workspace root (watchFolders + nodeModulesPaths), so the TS source of
// @split-ranch/domain is resolved and transpiled like app code.
// getSentryExpoConfig wraps Expo's default config and adds Sentry debug IDs to the
// bundle and its source maps, so uploaded maps match the code that crashed.
const { getSentryExpoConfig } = require('@sentry/react-native/metro');
const { withNativeWind } = require('nativewind/metro');

const config = getSentryExpoConfig(__dirname);

module.exports = withNativeWind(config, { input: './global.css', inlineRem: 16 });
