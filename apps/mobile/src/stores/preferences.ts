import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { zustandStorage } from '@/lib/storage';

export type ThemePreference = 'system' | 'light' | 'dark';
export type LanguagePreference = 'system' | 'es' | 'en';

interface PreferencesState {
  theme: ThemePreference;
  language: LanguagePreference;
  /** The group shown in the app; null or a group the user left = their first group. */
  activeGroupId: string | null;
  setTheme: (theme: ThemePreference) => void;
  setLanguage: (language: LanguagePreference) => void;
  setActiveGroupId: (groupId: string | null) => void;
}

/** Device-local UI preferences, persisted in MMKV. */
export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      theme: 'system',
      language: 'system',
      activeGroupId: null,
      setTheme: (theme) => set({ theme }),
      setLanguage: (language) => set({ language }),
      setActiveGroupId: (activeGroupId) => set({ activeGroupId }),
    }),
    {
      name: 'preferences',
      storage: createJSONStorage(() => zustandStorage),
      version: 2,
      // v1 had no active group: start with "first group".
      migrate: (persisted) => ({ activeGroupId: null, ...(persisted as object) }) as PreferencesState,
    },
  ),
);
