import { displayMoney } from '@/lib/money';
import type { QuickResultOk } from './compute';

/** Localised fragments of the share text; defaults are the Spanish ones from docs/03 §6. */
export interface ShareTextLabels {
  total: string;
  paidBy: string;
  each: string;
  payments: string;
  noPayments: string;
  paid: string;
}

export const DEFAULT_SHARE_LABELS: ShareTextLabels = {
  total: 'Total',
  paidBy: 'Pagado por',
  each: 'Lo que le toca a cada uno',
  payments: 'Quién paga a quién',
  noPayments: 'Están a mano, nadie debe nada',
  paid: 'pagado',
};

/**
 * Build the WhatsApp-ready summary (docs/03 §6), e.g.
 *   🧾 *Cena viernes*
 *   Total: 87,50 €
 *   Pagado por: Carlos
 *
 *   👥 *Lo que le toca a cada uno*
 *   • Ana: 21,88 €
 *   • Bea: 21,88 €
 *   …
 *
 *   💸 *Quién paga a quién*
 *   • Ana → Carlos: 21,88 €
 *   • Bea → Carlos: 21,88 € ✅ pagado
 * `*text*` is WhatsApp bold. The "paid by" line and the payments section are omitted when
 * nobody paid (split without payer); then people in `paidIds` get the ✅ on their share.
 * With several payers, the "paid by" line also shows how much each one paid.
 */
export function buildShareText(
  title: string,
  result: QuickResultOk,
  labels: ShareTextLabels = DEFAULT_SHARE_LABELS,
  locale = 'es-ES',
  paidIds: readonly string[] = [],
): string {
  const money = (cents: number) => displayMoney(cents, locale);
  const tick = (id: string) => (paidIds.includes(id) ? ` ✅ ${labels.paid}` : '');

  const lines = [`🧾 *${title.trim()}*`, `${labels.total}: ${money(result.totalCents)}`];

  if (result.balances) {
    const payers = result.balances.filter((b) => b.paidCents > 0);
    const paidBy =
      payers.length === 1
        ? (payers[0]?.name ?? '')
        : payers.map((p) => `${p.name} (${money(p.paidCents)})`).join(', ');
    lines.push(`${labels.paidBy}: ${paidBy}`);
  }

  lines.push('', `👥 *${labels.each}*`);
  for (const p of result.perPerson) {
    lines.push(`• ${p.name}: ${money(p.amountCents)}${result.balances ? '' : tick(p.id)}`);
  }

  if (result.balances) {
    lines.push('', `💸 *${labels.payments}*`);
    if (result.transfers.length === 0) {
      lines.push(`✅ ${labels.noPayments}`);
    } else {
      for (const t of result.transfers) {
        lines.push(`• ${t.fromName} → ${t.toName}: ${money(t.amountCents)}${tick(t.fromId)}`);
      }
    }
  }

  return lines.join('\n');
}
