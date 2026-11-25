/**
 * Partial payments on the settle-up screen: a suggestion is paid in full by default, and the
 * caller can lower the amount to pay part of it now and keep owing the rest.
 */

export type PartialAmountError = 'empty' | 'tooMuch';

export type PartialAmountCheck =
  | { ok: true; amountCents: number; remainingCents: number }
  | { ok: false; error: PartialAmountError };

/**
 * Validates the amount typed for a suggestion that owes `owedCents`.
 * `null` (empty or unparseable) and zero are `empty`; more than what is owed is `tooMuch`,
 * since overpaying would flip the debt instead of reducing it.
 */
export function checkPartialAmount(amountCents: number | null, owedCents: number): PartialAmountCheck {
  if (amountCents === null || amountCents <= 0) return { ok: false, error: 'empty' };
  if (amountCents > owedCents) return { ok: false, error: 'tooMuch' };
  return { ok: true, amountCents, remainingCents: owedCents - amountCents };
}

/** Half of what is owed, rounded down to the cent (a quick shortcut while editing). */
export function halfOf(owedCents: number): number {
  return Math.floor(owedCents / 2);
}
