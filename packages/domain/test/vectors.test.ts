import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { allocate, computeBalances, DomainError, resolveShares, settle, type SplitType } from '../src';

// Shared parity vectors, also executed by the Python test suite.
const vectorsDir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'domain-vectors');
const load = <T>(file: string): T[] => JSON.parse(readFileSync(join(vectorsDir, file), 'utf8')) as T[];

function expectDomainError(fn: () => unknown, code: string) {
  try {
    fn();
  } catch (e) {
    expect(e).toBeInstanceOf(DomainError);
    expect((e as DomainError).code).toBe(code);
    return;
  }
  throw new Error(`expected DomainError ${code}`);
}

interface AllocateVector {
  name: string;
  total: number;
  ratios: number[];
  expected?: number[];
  error?: string;
}

describe('allocate vectors', () => {
  for (const v of load<AllocateVector>('allocate.json')) {
    it(v.name, () => {
      if (v.error) expectDomainError(() => allocate(v.total, v.ratios), v.error);
      else expect(allocate(v.total, v.ratios)).toEqual(v.expected);
    });
  }
});

interface ResolveVector {
  name: string;
  input: {
    amount_cents: number;
    payer_id: string;
    split_type: SplitType;
    participants: { id: string; weight?: number; basis_points?: number; exact_cents?: number }[];
  };
  expected?: { id: string; amount_cents: number }[];
  error?: string;
}

describe('resolveShares vectors', () => {
  for (const v of load<ResolveVector>('resolve_shares.json')) {
    it(v.name, () => {
      const run = () =>
        resolveShares({
          amountCents: v.input.amount_cents,
          payerId: v.input.payer_id,
          splitType: v.input.split_type,
          participants: v.input.participants.map((p) => ({
            id: p.id,
            weight: p.weight,
            basisPoints: p.basis_points,
            exactCents: p.exact_cents,
          })),
        });
      if (v.error) expectDomainError(run, v.error);
      else expect(run()).toEqual(v.expected!.map((s) => ({ id: s.id, amountCents: s.amount_cents })));
    });
  }
});

interface BalancesVector {
  name: string;
  member_order: string[];
  expenses: {
    payer_id: string;
    amount_cents: number;
    personal?: boolean;
    shares: { id: string; amount_cents: number }[];
  }[];
  expected?: { id: string; paid_cents: number; owed_cents: number; net_cents: number }[];
  error?: string;
}

describe('computeBalances vectors', () => {
  for (const v of load<BalancesVector>('balances.json')) {
    it(v.name, () => {
      const run = () =>
        computeBalances(
          v.member_order,
          v.expenses.map((e) => ({
            payerId: e.payer_id,
            amountCents: e.amount_cents,
            personal: e.personal,
            shares: e.shares.map((s) => ({ id: s.id, amountCents: s.amount_cents })),
          })),
        );
      if (v.error) expectDomainError(run, v.error);
      else
        expect(run()).toEqual(
          v.expected!.map((b) => ({
            id: b.id,
            paidCents: b.paid_cents,
            owedCents: b.owed_cents,
            netCents: b.net_cents,
          })),
        );
    });
  }
});

interface SettleVector {
  name: string;
  nets: { id: string; net_cents: number }[];
  expected?: { from_id: string; to_id: string; amount_cents: number }[];
  error?: string;
}

describe('settle vectors', () => {
  for (const v of load<SettleVector>('settle.json')) {
    it(v.name, () => {
      const run = () => settle(v.nets.map((n) => ({ id: n.id, netCents: n.net_cents })));
      if (v.error) expectDomainError(run, v.error);
      else
        expect(run()).toEqual(
          v.expected!.map((t) => ({ fromId: t.from_id, toId: t.to_id, amountCents: t.amount_cents })),
        );
    });
  }
});
