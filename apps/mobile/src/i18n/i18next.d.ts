import 'i18next';
import type es from './es';

// Typed translation keys: t('quick.title') is checked at compile time.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: typeof es };
  }
}
