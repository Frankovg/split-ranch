import { DomainError } from './errors';
import type { Share } from './split';

export interface LedgerExpense {
  payerId: string;
  amountCents: number;
  shares: readonly Share[];
  /** Personal expenses are excluded from balances and settlement. */
  personal?: boolean;
}

export interface Balance {
  id: string;
  paidCents: number;
  owedCents: number;
  netCents: number;
}

export interface Transfer {
  fromId: string;
  toId: string;
  amountCents: number;
}

/**
 * Compute paid / owed / net per member. `memberOrder` is the canonical order and
 * defines the output order; ids found in expenses but not in `memberOrder` are appended.
 */
export function computeBalances(memberOrder: readonly string[], expenses: readonly LedgerExpense[]): Balance[] {
  const order = [...memberOrder];
  const paid = new Map<string, number>();
  const owed = new Map<string, number>();
  const touch = (id: string) => {
    if (!paid.has(id)) {
      paid.set(id, 0);
      owed.set(id, 0);
      if (!order.includes(id)) order.push(id);
    }
  };
  memberOrder.forEach(touch);

  for (const e of expenses) {
    if (e.personal) continue;
    const sharesSum = e.shares.reduce((a, s) => a + s.amountCents, 0);
    if (sharesSum !== e.amountCents) {
      throw new DomainError('split_mismatch', `shares sum ${sharesSum} != amount ${e.amountCents}`);
    }
    touch(e.payerId);
    paid.set(e.payerId, paid.get(e.payerId)! + e.amountCents);
    for (const s of e.shares) {
      touch(s.id);
      owed.set(s.id, owed.get(s.id)! + s.amountCents);
    }
  }

  return order.map((id) => {
    const p = paid.get(id)!;
    const o = owed.get(id)!;
    return { id, paidCents: p, owedCents: o, netCents: p - o };
  });
}

/**
 * Deterministic greedy settlement: repeatedly match the largest creditor with the
 * largest debtor (ties -> earlier in input order). At most n-1 transfers, no cent lost.
 * Mirrors `split_ranch.domain.settle.settle` (Python).
 */
export function settle(nets: readonly { id: string; netCents: number }[]): Transfer[] {
  const total = nets.reduce((a, n) => a + n.netCents, 0);
  if (total !== 0) {
    throw new DomainError('unbalanced_nets', `nets must sum to 0, got ${total}`);
  }
  const remaining = nets.map((n) => ({ id: n.id, value: n.netCents }));
  const transfers: Transfer[] = [];

  const pick = (sign: 1 | -1) => {
    let best: { id: string; value: number } | undefined;
    for (const r of remaining) {
      if (Math.sign(r.value) !== sign) continue;
      if (!best || Math.abs(r.value) > Math.abs(best.value)) best = r;
    }
    return best;
  };

  for (;;) {
    const creditor = pick(1);
    const debtor = pick(-1);
    if (!creditor || !debtor) break;
    const amount = Math.min(creditor.value, -debtor.value);
    transfers.push({ fromId: debtor.id, toId: creditor.id, amountCents: amount });
    creditor.value -= amount;
    debtor.value += amount;
  }
  return transfers;
}
