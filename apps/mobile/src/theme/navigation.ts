import { DarkTheme, DefaultTheme, type Theme } from 'expo-router';
import { Platform } from 'react-native';
import { tokenColor, type ColorScheme } from './tokens';

/** Brand font family; mirrors `fontFamily.sans` in tailwind.config.js. */
export const FONT_FAMILY = Platform.select({ ios: 'Readex Pro', default: 'ReadexPro' });

const FONTS: Theme['fonts'] = {
  regular: { fontFamily: FONT_FAMILY, fontWeight: '400' },
  medium: { fontFamily: FONT_FAMILY, fontWeight: '500' },
  bold: { fontFamily: FONT_FAMILY, fontWeight: '600' },
  heavy: { fontFamily: FONT_FAMILY, fontWeight: '700' },
};

function build(scheme: ColorScheme, base: Theme): Theme {
  return {
    ...base,
    colors: {
      background: tokenColor(scheme, 'background'),
      border: tokenColor(scheme, 'border'),
      // Headers and the tab bar sit on the page background, as in the portfolio navbar.
      card: tokenColor(scheme, 'background'),
      notification: tokenColor(scheme, 'destructive'),
      primary: tokenColor(scheme, 'primary'),
      text: tokenColor(scheme, 'foreground'),
    },
    fonts: FONTS,
  };
}

/** React Navigation themes derived from the same tokens as NativeWind, to avoid flashes. */
export const NAV_THEME: Record<ColorScheme, Theme> = {
  light: build('light', DefaultTheme),
  dark: build('dark', DarkTheme),
};
