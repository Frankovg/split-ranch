import {
  computeBalances,
  resolveShares,
  settle,
  type LedgerExpense,
  type ResolveSharesInput,
} from '@split-ranch/domain';
import type { QuickEvent, QuickParticipant } from './types';

/**
 * Build @split-ranch/domain inputs from a Quick split event and run
 * resolveShares -> computeBalances -> settle. No money arithmetic happens here.
 */

export type IncompleteReason = 'no_participants' | 'no_amount' | 'no_included' | 'no_expenses';

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

/** Build the ledger of mode 2 ("itemised"): one equal split per valid expense. */
export function buildItemisedLedger(event: QuickEvent): {
  inputs: ResolveSharesInput[];
  skippedExpenseIds: string[];
} {
  const order = event.participants.map((p) => p.id);
  const inputs: ResolveSharesInput[] = [];
  const skippedExpenseIds: string[] = [];
  for (const e of event.expenses) {
    // Keep participants in canonical order and drop ids that no longer exist.
    const ids = order.filter((id) => e.participantIds.includes(id));
    if (e.amountCents <= 0 || ids.length === 0 || !order.includes(e.payerId)) {
      skippedExpenseIds.push(e.id);
      continue;
    }
    inputs.push({
      amountCents: e.amountCents,
      payerId: e.payerId,
      splitType: 'equal',
      participants: ids.map((id) => ({ id })),
    });
  }
  return { inputs, skippedExpenseIds };
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

  if (event.mode === 'total') {
    const input = buildTotalExpense(event);
    if (typeof input === 'string') return { status: 'incomplete', reason: input };
    ledger = [{ payerId: input.payerId, amountCents: input.amountCents, shares: resolveShares(input) }];
    hasPayer = input.payerId === event.total.payerId;
    const included = new Set(input.participants.map((p) => p.id));
    shown = (id) => included.has(id);
  } else {
    const built = buildItemisedLedger(event);
    skippedExpenseIds = built.skippedExpenseIds;
    if (built.inputs.length === 0) return { status: 'incomplete', reason: 'no_expenses' };
    ledger = built.inputs.map((input) => ({
      payerId: input.payerId,
      amountCents: input.amountCents,
      shares: resolveShares(input),
    }));
    hasPayer = true;
    shown = () => true;
  }

  const balances = computeBalances(order, ledger);
  const totalCents = ledger.reduce((acc, e) => acc + e.amountCents, 0);
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
