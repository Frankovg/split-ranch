import * as SystemUI from 'expo-system-ui';
import { colorScheme as nwColorScheme, useColorScheme } from 'nativewind';
import * as React from 'react';
import { usePreferencesStore } from '@/stores/preferences';
import { tokenColor, type ColorScheme } from './tokens';

/** Resolved scheme ('light' | 'dark') currently applied by NativeWind. */
export function useAppColorScheme(): ColorScheme {
  const { colorScheme } = useColorScheme();
  return colorScheme === 'dark' ? 'dark' : 'light';
}

/**
 * Applies the persisted theme preference (system/light/dark) to NativeWind and
 * keeps the Android root view background in sync to avoid flashes.
 */
export function ThemeSync() {
  const pref = usePreferencesStore((s) => s.theme);
  const scheme = useAppColorScheme();

  React.useEffect(() => {
    nwColorScheme.set(pref);
  }, [pref]);

  React.useEffect(() => {
    void SystemUI.setBackgroundColorAsync(tokenColor(scheme, 'background'));
  }, [scheme]);

  return null;
}
