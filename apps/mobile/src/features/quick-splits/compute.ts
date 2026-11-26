import {
  computeBalances,
  resolveShares,
  settle,
  type LedgerExpense,
  type ResolveSharesInput,
  type Share,
} from '@split-ranch/domain';
import type { QuickEvent, QuickParticipant } from './types';

/**
 * Build @split-ranch/domain inputs from a Quick split event and run
 * resolveShares -> computeBalances -> settle. No money arithmetic happens here beyond
 * checking that several payers add up to the amount they paid.
 */

export type IncompleteReason =
  | 'no_participants'
  | 'no_amount'
  | 'no_included'
  | 'no_expenses'
  | 'payers_mismatch';

/**
 * Synthetic ledger id for "several payers": the total is booked as paid by this pot and each
 * payer pays their part into it, so the pot nets to zero and every person gets paid = what
 * they put in, owed = their share. It never appears in results.
 */
const POT_ID = '__pot__';

export interface PersonAmount {
  id: string;
  name: string;
  amountCents: number;
}

export interface PersonBalance {
  id: string;
  name: string;
  paidCents: number;
  owedCents: number;
  netCents: number;
}

export interface NamedTransfer {
  fromId: string;
  fromName: string;
  toId: string;
  toName: string;
  amountCents: number;
}

export interface QuickResultOk {
  status: 'ok';
  totalCents: number;
  /** What each person's share costs, canonical order (excluded people are omitted in mode 1). */
  perPerson: PersonAmount[];
  /** Paid / owed / net; null in "split a total" mode without a payer. */
  balances: PersonBalance[] | null;
  transfers: NamedTransfer[];
  /** Itemised expenses skipped because they are incomplete (e.g. nobody selected). */
  skippedExpenseIds: string[];
}

export type QuickResult = { status: 'incomplete'; reason: IncompleteReason } | QuickResultOk;

/** Build the single ledger expense of mode 1 ("split a total"). */
export function buildTotalExpense(event: QuickEvent): ResolveSharesInput | IncompleteReason {
  if (event.participants.length === 0) return 'no_participants';
  const amount = event.total.amountCents;
  if (amount === null || amount <= 0) return 'no_amount';
  const included = event.participants.filter((p) => !event.total.excludedIds.includes(p.id));
  const first = included[0];
  if (!first) return 'no_included';

  const weighted = included.some((p) => (event.total.weights[p.id] ?? 1) !== 1);
  const payerId =
    event.total.payerId !== null && event.participants.some((p) => p.id === event.total.payerId)
      ? event.total.payerId
      : first.id; // the payer does not affect shares for equal/weights splits
  return {
    amountCents: amount,
    payerId,
    splitType: weighted ? 'weights' : 'equal',
    participants: included.map((p) =>
      weighted ? { id: p.id, weight: event.total.weights[p.id] ?? 1 } : { id: p.id },
    ),
  };
}

interface PayerPart {
  id: string;
  amountCents: number;
}

/**
 * What several payers put in: existing participants with an amount > 0, in canonical order.
 * Null when nobody paid or the parts do not add up to `amountCents`.
 */
function payerParts(
  participants: readonly QuickParticipant[],
  amounts: Readonly<Record<string, number>>,
  amountCents: number,
): PayerPart[] | null {
  const parts = participants
    .map((p) => ({ id: p.id, amountCents: amounts[p.id] ?? 0 }))
    .filter((p) => p.amountCents > 0);
  const sum = parts.reduce((acc, p) => acc + p.amountCents, 0);
  return parts.length > 0 && sum === amountCents ? parts : null;
}

/** Ledger rows of one expense: a plain row for one payer, or the pot rows for several. */
function ledgerRows(amountCents: number, shares: readonly Share[], payer: string | PayerPart[]): LedgerExpense[] {
  if (typeof payer === 'string') return [{ payerId: payer, amountCents, shares }];
  return [
    { payerId: POT_ID, amountCents, shares },
    ...payer.map((p) => ({
      payerId: p.id,
      amountCents: p.amountCents,
      shares: [{ id: POT_ID, amountCents: p.amountCents }],
    })),
  ];
}

/** Build the ledger of mode 2 ("itemised"): one equal split per valid expense. */
export function buildItemisedLedger(event: QuickEvent): {
  ledger: LedgerExpense[];
  totalCents: number;
  skippedExpenseIds: string[];
} {
  const order = event.participants.map((p) => p.id);
  const ledger: LedgerExpense[] = [];
  const skippedExpenseIds: string[] = [];
  let totalCents = 0;
  for (const e of event.expenses) {
    // Keep participants in canonical order and drop ids that no longer exist.
    const ids = order.filter((id) => e.participantIds.includes(id));
    const payer = e.payerAmounts
      ? payerParts(event.participants, e.payerAmounts, e.amountCents)
      : order.includes(e.payerId)
        ? e.payerId
        : null;
    if (e.amountCents <= 0 || ids.length === 0 || payer === null) {
      skippedExpenseIds.push(e.id);
      continue;
    }
    const shares = resolveShares({
      amountCents: e.amountCents,
      payerId: typeof payer === 'string' ? payer : (payer[0]?.id ?? ''),
      splitType: 'equal',
      participants: ids.map((id) => ({ id })),
    });
    ledger.push(...ledgerRows(e.amountCents, shares, payer));
    totalCents += e.amountCents;
  }
  return { ledger, totalCents, skippedExpenseIds };
}

function nameLookup(participants: readonly QuickParticipant[]): (id: string) => string {
  const names = new Map(participants.map((p) => [p.id, p.name]));
  return (id) => names.get(id) ?? '?';
}

export function computeQuickResult(event: QuickEvent): QuickResult {
  if (event.participants.length === 0) return { status: 'incomplete', reason: 'no_participants' };
  const order = event.participants.map((p) => p.id);
  const name = nameLookup(event.participants);

  let ledger: LedgerExpense[];
  let hasPayer: boolean;
  let skippedExpenseIds: string[] = [];
  let shown: (id: string) => boolean;
  let totalCents: number;

  if (event.mode === 'total') {
    const input = buildTotalExpense(event);
    if (typeof input === 'string') return { status: 'incomplete', reason: input };
    const shares = resolveShares(input);
    if (event.total.payerAmounts) {
      const parts = payerParts(event.participants, event.total.payerAmounts, input.amountCents);
      if (!parts) return { status: 'incomplete', reason: 'payers_mismatch' };
      ledger = ledgerRows(input.amountCents, shares, parts);
      hasPayer = true;
    } else {
      ledger = ledgerRows(input.amountCents, shares, input.payerId);
      hasPayer = input.payerId === event.total.payerId;
    }
    totalCents = input.amountCents;
    const included = new Set(input.participants.map((p) => p.id));
    shown = (id) => included.has(id);
  } else {
    const built = buildItemisedLedger(event);
    skippedExpenseIds = built.skippedExpenseIds;
    if (built.ledger.length === 0) return { status: 'incomplete', reason: 'no_expenses' };
    ledger = built.ledger;
    hasPayer = true;
    totalCents = built.totalCents;
    shown = () => true;
  }

  const balances = computeBalances(order, ledger).filter((b) => b.id !== POT_ID);
  const perPerson: PersonAmount[] = balances
    .filter((b) => shown(b.id))
    .map((b) => ({ id: b.id, name: name(b.id), amountCents: b.owedCents }));

  if (!hasPayer) {
    return { status: 'ok', totalCents, perPerson, balances: null, transfers: [], skippedExpenseIds };
  }

  const transfers: NamedTransfer[] = settle(balances).map((t) => ({
    fromId: t.fromId,
    fromName: name(t.fromId),
    toId: t.toId,
    toName: name(t.toId),
    amountCents: t.amountCents,
  }));
  return {
    status: 'ok',
    totalCents,
    perPerson,
    balances: balances.map((b) => ({ ...b, name: name(b.id) })),
    transfers,
    skippedExpenseIds,
  };
}
