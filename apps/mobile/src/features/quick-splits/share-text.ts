import { displayMoney, formatAmount, plainSpaces } from '@/lib/money';
import type { QuickResultOk } from './compute';

/** Localised fragments of the share text; defaults are the Spanish ones from docs/03 §6. */
export interface ShareTextLabels {
  each: string;
  payments: string;
  noPayments: string;
  footer: string;
}

export const DEFAULT_SHARE_LABELS: ShareTextLabels = {
  each: 'Cada uno',
  payments: 'Pagos',
  noPayments: 'nadie debe nada',
  footer: 'Hecho con Split Ranch',
};

/**
 * Build the WhatsApp-ready summary (docs/03 §6), e.g.
 *   🧾 Cena viernes — 87,50 €
 *   Cada uno: Ana 21,88 · Bea 21,88 · Carlos 21,87 · Dani 21,87
 *   Pagos: Ana → Carlos 21,88 €; Bea → Carlos 21,88 €; Dani → Carlos 21,87 €
 *   Hecho con Split Ranch
 * The "Pagos" line is omitted when nobody paid (split without payer).
 */
export function buildShareText(
  title: string,
  result: QuickResultOk,
  labels: ShareTextLabels = DEFAULT_SHARE_LABELS,
  locale = 'es-ES',
): string {
  const amount = (cents: number) => plainSpaces(formatAmount(cents, locale));
  const lines = [`🧾 ${title.trim()} — ${displayMoney(result.totalCents, locale)}`];
  lines.push(`${labels.each}: ${result.perPerson.map((p) => `${p.name} ${amount(p.amountCents)}`).join(' · ')}`);
  if (result.balances) {
    const payments =
      result.transfers.length === 0
        ? labels.noPayments
        : result.transfers
            .map((t) => `${t.fromName} → ${t.toName} ${displayMoney(t.amountCents, locale)}`)
            .join('; ');
    lines.push(`${labels.payments}: ${payments}`);
  }
  lines.push(labels.footer);
  return lines.join('\n');
}
