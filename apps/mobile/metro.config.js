// Metro config for the pnpm monorepo. Expo's default config already detects the
// workspace root (watchFolders + nodeModulesPaths), so the TS source of
// @split-ranch/domain is resolved and transpiled like app code.
const { getDefaultConfig } = require('expo/metro-config');
const { withNativeWind } = require('nativewind/metro');

const config = getDefaultConfig(__dirname);

module.exports = withNativeWind(config, { input: './global.css', inlineRem: 16 });
