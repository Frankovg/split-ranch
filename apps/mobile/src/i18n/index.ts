import { getLocales } from 'expo-localization';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { moneyLocale } from '@/lib/money';
import type { LanguagePreference } from '@/stores/preferences';
import en from './en';
import es from './es';

export const SUPPORTED_LANGUAGES = ['es', 'en'] as const;
export type AppLanguage = (typeof SUPPORTED_LANGUAGES)[number];

/** Resolve the effective language: explicit preference, else device language, else Spanish. */
export function resolveLanguage(pref: LanguagePreference): AppLanguage {
  if (pref !== 'system') return pref;
  const device = getLocales()[0]?.languageCode ?? 'es';
  return device === 'en' ? 'en' : 'es';
}

void i18n.use(initReactI18next).init({
  resources: { es: { translation: es }, en: { translation: en } },
  lng: resolveLanguage('system'),
  fallbackLng: 'es',
  interpolation: { escapeValue: false }, // React already escapes
  returnNull: false,
});

/** Intl locale for money in the current language (es-ES / en-IE, always EUR). */
export function currentMoneyLocale(): string {
  return moneyLocale(i18n.language);
}

export default i18n;
