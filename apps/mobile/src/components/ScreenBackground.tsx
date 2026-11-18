import { Image, StyleSheet, type ImageSourcePropType } from 'react-native';
import { useAppColorScheme } from '@/theme/ThemeSync';

/* eslint-disable @typescript-eslint/no-require-imports */
const BACKDROPS: Record<'light' | 'dark', ImageSourcePropType> = {
  light: require('../../assets/backdrop-light.png') as ImageSourcePropType,
  dark: require('../../assets/backdrop-dark.png') as ImageSourcePropType,
};
/* eslint-enable @typescript-eslint/no-require-imports */

/**
 * Brand backdrop: a diagonal gradient (surface → background → accent), the static
 * version of the portfolio's animated page background. Render it first inside a
 * container whose own background is the page background.
 *
 * It is a pre-rendered, dithered image (scripts/generate-backdrop.mjs) instead of a live
 * gradient: the colours are only a few 8-bit levels apart and neither react-native-svg
 * nor the native gradient dither on Android, so a live gradient shows hard bands.
 * It is stretched to fill the screen.
 */
export function ScreenBackground() {
  const scheme = useAppColorScheme();
  return (
    <Image
      source={BACKDROPS[scheme]}
      resizeMode='stretch'
      fadeDuration={0}
      pointerEvents='none'
      style={StyleSheet.absoluteFill}
    />
  );
}
