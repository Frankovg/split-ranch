import { useEffect } from 'react';
import i18n, { resolveLanguage } from '@/i18n';
import { usePreferencesStore } from '@/stores/preferences';

/** Applies the persisted language preference to i18next. */
export function LanguageSync() {
  const pref = usePreferencesStore((s) => s.language);
  useEffect(() => {
    const lang = resolveLanguage(pref);
    if (i18n.language !== lang) void i18n.changeLanguage(lang);
  }, [pref]);
  return null;
}
