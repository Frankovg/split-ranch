import fc from 'fast-check';
import { describe, expect, it } from 'vitest';

import { allocate, computeBalances, resolveShares, settle } from '../src';

const ratiosArb = fc
  .array(fc.integer({ min: 0, max: 10_000 }), { minLength: 1, maxLength: 12 })
  .filter((r) => r.some((x) => x > 0));
const totalArb = fc.integer({ min: -1_000_000_000, max: 1_000_000_000 });

describe('allocate properties', () => {
  it('parts always sum to the total', () => {
    fc.assert(
      fc.property(totalArb, ratiosArb, (t, r) => {
        expect(allocate(t, r).reduce((a, b) => a + b, 0)).toBe(t);
      }),
    );
  });

  it('each part is floor or ceil of the exact share', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 1_000_000_000 }), ratiosArb, (t, r) => {
        const sum = BigInt(r.reduce((a, b) => a + b, 0));
        allocate(t, r).forEach((part, i) => {
          const floor = (BigInt(t) * BigInt(r[i]!)) / sum;
          expect(BigInt(part) === floor || BigInt(part) === floor + 1n).toBe(true);
        });
      }),
    );
  });

  it('zero ratios get zero', () => {
    fc.assert(
      fc.property(totalArb, ratiosArb, (t, r) => {
        allocate(t, r).forEach((part, i) => {
          if (r[i] === 0) expect(part).toBe(0);
        });
      }),
    );
  });

  it('is sign-symmetric', () => {
    fc.assert(
      fc.property(totalArb, ratiosArb, (t, r) => {
        expect(allocate(-t, r)).toEqual(allocate(t, r).map((x) => (x === 0 ? 0 : -x)));
      }),
    );
  });

  it('is invariant to scaling the ratios', () => {
    fc.assert(
      fc.property(totalArb, ratiosArb, fc.integer({ min: 1, max: 50 }), (t, r, k) => {
        expect(allocate(t, r.map((x) => x * k))).toEqual(allocate(t, r));
      }),
    );
  });
});

const idsArb = fc.uniqueArray(fc.string({ minLength: 1, maxLength: 4 }), { minLength: 2, maxLength: 8 });

describe('settle properties', () => {
  it('settles every net to zero with at most n-1 transfers', () => {
    fc.assert(
      fc.property(
        idsArb,
        fc.array(fc.record({ payer: fc.nat(), amount: fc.integer({ min: 1, max: 1_000_000 }) }), {
          minLength: 1,
          maxLength: 30,
        }),
        (ids, raw) => {
          const expenses = raw.map(({ payer, amount }) => {
            const payerId = ids[payer % ids.length]!;
            const shares = resolveShares({
              amountCents: amount,
              payerId,
              splitType: 'equal',
              participants: ids.map((id) => ({ id })),
            });
            return { payerId, amountCents: amount, shares };
          });
          const balances = computeBalances(ids, expenses);
          expect(balances.reduce((a, b) => a + b.netCents, 0)).toBe(0);

          const transfers = settle(balances);
          const remaining = new Map(balances.map((b) => [b.id, b.netCents]));
          for (const t of transfers) {
            expect(t.amountCents).toBeGreaterThan(0);
            remaining.set(t.fromId, remaining.get(t.fromId)! + t.amountCents);
            remaining.set(t.toId, remaining.get(t.toId)! - t.amountCents);
          }
          for (const v of remaining.values()) expect(v).toBe(0);
          const nonZero = balances.filter((b) => b.netCents !== 0).length;
          expect(transfers.length).toBeLessThanOrEqual(Math.max(0, nonZero - 1));
          expect(settle(balances)).toEqual(transfers);
        },
      ),
    );
  });
});
