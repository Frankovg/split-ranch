import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { zustandStorage } from '@/lib/storage';

export type ThemePreference = 'system' | 'light' | 'dark';
export type LanguagePreference = 'system' | 'es' | 'en';

interface PreferencesState {
  theme: ThemePreference;
  language: LanguagePreference;
  setTheme: (theme: ThemePreference) => void;
  setLanguage: (language: LanguagePreference) => void;
}

/** Device-local UI preferences, persisted in MMKV. */
export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      theme: 'system',
      language: 'system',
      setTheme: (theme) => set({ theme }),
      setLanguage: (language) => set({ language }),
    }),
    {
      name: 'preferences',
      storage: createJSONStorage(() => zustandStorage),
      version: 3,
      // v2 persisted an "active group"; the group now comes from the route, so it is dropped.
      migrate: (persisted) => {
        const { activeGroupId: _dropped, ...rest } = persisted as Record<string, unknown>;
        return rest as unknown as PreferencesState;
      },
    },
  ),
);
