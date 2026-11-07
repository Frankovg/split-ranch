import type { TFunction } from 'i18next';
import { moneyParts } from './index';

/**
 * Screen-reader text for an amount, e.g. "12 euros con 50 céntimos" / "menos 3 euros".
 * TalkBack reads "12,50 €" inconsistently across voices, so amounts are spelled out.
 */
export function spokenMoney(cents: number, t: TFunction): string {
  const p = moneyParts(cents);
  const text =
    p.cents === 0
      ? t('money.spokenWhole', { euros: p.euros })
      : t('money.spoken', { euros: p.euros, cents: p.cents });
  return p.negative ? t('money.minus', { amount: text }) : text;
}
