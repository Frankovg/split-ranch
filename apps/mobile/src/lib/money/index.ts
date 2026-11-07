/**
 * Money helpers for the app. All arithmetic lives in @split-ranch/domain;
 * this module only re-exports it and adds presentation helpers.
 */
export {
  allocate,
  computeBalances,
  DomainError,
  formatAmount,
  formatMoney,
  MAX_AMOUNT_CENTS,
  parseMoney,
  resolveShares,
  settle,
  type Balance,
  type LedgerExpense,
  type Share,
  type Transfer,
} from '@split-ranch/domain';

import { formatMoney } from '@split-ranch/domain';

/** Map an app language to the Intl locale used for euro amounts. */
export function moneyLocale(language: string): string {
  return language.startsWith('en') ? 'en-IE' : 'es-ES';
}

/**
 * Format cents as currency for display. Replaces the narrow/no-break spaces Intl
 * inserts so text copied or shared (e.g. to WhatsApp) uses plain spaces.
 */
export function displayMoney(cents: number, locale = 'es-ES'): string {
  return plainSpaces(formatMoney(cents, locale));
}

/** Split cents into whole euros and remaining cents (absolute values), for spoken labels. */
export function moneyParts(cents: number): { negative: boolean; euros: number; cents: number } {
  const abs = Math.abs(cents);
  return { negative: cents < 0, euros: Math.floor(abs / 100), cents: abs % 100 };
}

// NBSP (U+00A0) and narrow NBSP (U+202F) that Intl inserts; built from char codes to keep the source ASCII.
const INTL_SPACES = new RegExp(`[${String.fromCharCode(0xa0, 0x202f)}]`, 'g');

/** Replace the no-break spaces Intl inserts with `replacement` (plain space by default). */
export function plainSpaces(text: string, replacement = ' '): string {
  return text.replace(INTL_SPACES, replacement);
}
