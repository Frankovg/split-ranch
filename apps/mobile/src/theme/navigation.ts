import { DarkTheme, DefaultTheme, type Theme } from 'expo-router';
import { tokenColor, type ColorScheme } from './tokens';

function build(scheme: ColorScheme, base: Theme): Theme {
  return {
    ...base,
    colors: {
      background: tokenColor(scheme, 'background'),
      border: tokenColor(scheme, 'border'),
      card: tokenColor(scheme, 'card'),
      notification: tokenColor(scheme, 'destructive'),
      primary: tokenColor(scheme, 'primary'),
      text: tokenColor(scheme, 'foreground'),
    },
  };
}

/** React Navigation themes derived from the same tokens as NativeWind, to avoid flashes. */
export const NAV_THEME: Record<ColorScheme, Theme> = {
  light: build('light', DefaultTheme),
  dark: build('dark', DarkTheme),
};
